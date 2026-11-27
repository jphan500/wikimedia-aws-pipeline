# catalog.tf: the Glue Data Catalog. It tells Athena what the files in S3 look like.
# Schemas are written here in code (no crawlers). Partition projection lets Athena
# compute dt=/hr= folder paths from a pattern instead of storing every partition.

variable "projection_start_date" {
  type        = string
  default     = "2026-11-20"
  description = "Earliest dt Athena will look for. Set a little before the first data landed."
}

locals {
  # Glue/Athena database names can't contain hyphens
  db_name = replace(var.project, "-", "_")

  # "00,01,...,23"
  hours = join(",", [for h in range(24) : format("%02d", h)])

  # MUST match src/process/writer.py (a test enforces this)
  silver_columns = [
    { name = "event_id", type = "string" },
    { name = "event_ts", type = "timestamp" },
    { name = "rc_id", type = "bigint" },
    { name = "wiki", type = "string" },
    { name = "type", type = "string" },
    { name = "namespace", type = "int" },
    { name = "title", type = "string" },
    { name = "user", type = "string" },
    { name = "is_bot", type = "boolean" },
    { name = "is_minor", type = "boolean" },
    { name = "length_old", type = "bigint" },
    { name = "length_new", type = "bigint" },
    { name = "byte_delta", type = "bigint" },
    { name = "revision_old", type = "bigint" },
    { name = "revision_new", type = "bigint" },
    { name = "comment", type = "string" },
    { name = "_source_key", type = "string" },
  ]

  projection = {
    "projection.enabled"          = "true"
    "projection.dt.type"          = "date"
    "projection.dt.format"        = "yyyy-MM-dd"
    "projection.dt.range"         = "${var.projection_start_date},NOW"
    "projection.dt.interval"      = "1"
    "projection.dt.interval.unit" = "DAYS"
    "projection.hr.type"          = "enum"
    "projection.hr.values"        = local.hours
  }
}

resource "aws_glue_catalog_database" "wiki" {
  name = local.db_name
}

# Silver: cleaned English edits, Parquet
resource "aws_glue_catalog_table" "silver" {
  name          = "silver_recentchange"
  database_name = aws_glue_catalog_database.wiki.name
  table_type    = "EXTERNAL_TABLE"

  parameters = merge(local.projection, {
    EXTERNAL                    = "TRUE"
    classification              = "parquet"
    "storage.location.template" = "s3://${aws_s3_bucket.lake.bucket}/silver/recentchange/dt=$${dt}/hr=$${hr}/"
  })

  partition_keys {
    name = "dt"
    type = "string"
  }
  partition_keys {
    name = "hr"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/silver/recentchange/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.silver_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}

# Quarantine: rejected records as gzipped JSON lines, with the error code and original line
resource "aws_glue_catalog_table" "quarantine" {
  name          = "quarantine_recentchange"
  database_name = aws_glue_catalog_database.wiki.name
  table_type    = "EXTERNAL_TABLE"

  parameters = merge(local.projection, {
    EXTERNAL                    = "TRUE"
    classification              = "json"
    "storage.location.template" = "s3://${aws_s3_bucket.lake.bucket}/quarantine/recentchange/dt=$${dt}/hr=$${hr}/"
  })

  partition_keys {
    name = "dt"
    type = "string"
  }
  partition_keys {
    name = "hr"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/quarantine/recentchange/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "_error"
      type = "string"
    }
    columns {
      name = "_raw"
      type = "string"
    }
  }
}