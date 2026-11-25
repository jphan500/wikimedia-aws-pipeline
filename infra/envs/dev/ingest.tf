variable "user_agent" {
  type    = string
  default = "wikimedia-aws-pipeline/0.1 (https://github.com/jphan500/wikimedia-aws-pipeline)"
}

variable "ingest_enabled" {
  type    = bool
  default = false
}

# Provisioned 1/1 stays inside DynamoDB's always-free capacity
resource "aws_dynamodb_table" "checkpoints" {
  name           = "${var.project}-checkpoints"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "stream"

  attribute {
    name = "stream"
    type = "S"
  }
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${var.project}-ingest"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest" {
  name               = "${var.project}-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "ingest" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/wikimedia_recentchange/*"]
  }
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.checkpoints.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "ingest"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

data "archive_file" "ingest" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/ingest"
  output_path = "${path.module}/.build/ingest.zip"
}

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project}-ingest"
  role             = aws_iam_role.ingest.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.ingest.output_path
  source_code_hash = data.archive_file.ingest.output_base64sha256
  timeout          = 120
  memory_size      = 256

  environment {
    variables = {
      LAKE_BUCKET      = aws_s3_bucket.lake.bucket
      CHECKPOINT_TABLE = aws_dynamodb_table.checkpoints.name
      USER_AGENT       = var.user_agent
      MAX_SECONDS      = "90"
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest]
}

resource "aws_cloudwatch_event_rule" "ingest_schedule" {
  name                = "${var.project}-ingest-schedule"
  schedule_expression = "rate(5 minutes)"
  state               = var.ingest_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "ingest" {
  rule = aws_cloudwatch_event_rule.ingest_schedule.name
  arn  = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_schedule.arn
}