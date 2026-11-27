variable "target_wiki" {
  type    = string
  default = "enwiki"
}

variable "sdk_pandas_layer_arn" {
  type    = string
  default = "arn:aws:lambda:us-east-2:336392948345:layer:AWSSDKPandas-Python312:32"
}

resource "aws_sqs_queue" "process_dlq" {
  name                      = "${var.project}-process-dlq"
  message_retention_seconds = 1209600
}

resource "aws_cloudwatch_log_group" "process" {
  name              = "/aws/lambda/${var.project}-process"
  retention_in_days = 14
}

resource "aws_iam_role" "process" {
  name               = "${var.project}-process"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "process" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/wikimedia_recentchange/*"]
  }
  statement {
    actions = ["s3:PutObject"]
    resources = [
      "${aws_s3_bucket.lake.arn}/silver/recentchange/*",
      "${aws_s3_bucket.lake.arn}/quarantine/recentchange/*",
    ]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.process_dlq.arn]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.process.arn}:*"]
  }
}

resource "aws_iam_role_policy" "process" {
  name   = "process"
  role   = aws_iam_role.process.id
  policy = data.aws_iam_policy_document.process.json
}

data "archive_file" "process" {
  type        = "zip"
  source_dir  = "${path.module}/../../../src/process"
  output_path = "${path.module}/.build/process.zip"
}

resource "aws_lambda_function" "process" {
  function_name    = "${var.project}-process"
  role             = aws_iam_role.process.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.process.output_path
  source_code_hash = data.archive_file.process.output_base64sha256
  timeout          = 60
  memory_size      = 512
  layers           = [var.sdk_pandas_layer_arn]

  environment {
    variables = {
      LAKE_BUCKET = aws_s3_bucket.lake.bucket
      TARGET_WIKI = var.target_wiki
    }
  }

  depends_on = [aws_cloudwatch_log_group.process]
}

# Failed invocations: retry twice, then park the event in the dead-letter queue
resource "aws_lambda_function_event_invoke_config" "process" {
  function_name          = aws_lambda_function.process.function_name
  maximum_retry_attempts = 2

  destination_config {
    on_failure {
      destination = aws_sqs_queue.process_dlq.arn
    }
  }
}

resource "aws_lambda_permission" "s3_invoke_process" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.process.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.lake.arn
  source_account = data.aws_caller_identity.current.account_id
}

# DANGER: the prefix filter below must stay. Without it, the Lambda's own outputs
# (silver/, quarantine/) would trigger it again in an infinite, billable loop.
resource "aws_s3_bucket_notification" "lake" {
  bucket = aws_s3_bucket.lake.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.process.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/wikimedia_recentchange/"
    filter_suffix       = ".jsonl.gz"
  }

  depends_on = [aws_lambda_permission.s3_invoke_process]
}