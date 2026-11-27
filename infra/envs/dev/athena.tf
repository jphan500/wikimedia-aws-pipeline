# athena.tf: an Athena workgroup with cost guardrails. Queries that would scan
# more than 1 GB fail instead of costing money, and results land in a short-lived prefix.

resource "aws_athena_workgroup" "wiki" {
  name          = var.project
  force_destroy = true

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 GB

    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}