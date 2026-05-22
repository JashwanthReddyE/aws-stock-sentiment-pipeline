resource "random_id" "suffix" {
  byte_length = 3
}

resource "aws_s3_bucket" "bronze" {
  bucket        = "${var.project}-bronze-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket" "silver" {
  bucket        = "${var.project}-silver-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket" "gold" {
  bucket        = "${var.project}-gold-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket" "athena_results" {
  bucket        = "${var.project}-athena-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_bucket" "deploy" {
  bucket        = "${var.project}-deploy-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.tags
}

resource "aws_s3_object" "ingest_zip" {
  bucket      = aws_s3_bucket.deploy.id
  key         = "ingest.zip"
  source      = "${path.module}/build/ingest.zip"
  source_hash = filebase64sha256("${path.module}/build/ingest.zip")
}

resource "aws_s3_object" "enrich_zip" {
  bucket      = aws_s3_bucket.deploy.id
  key         = "enrich.zip"
  source      = "${path.module}/build/enrich.zip"
  source_hash = filebase64sha256("${path.module}/build/enrich.zip")
}

resource "aws_s3_object" "forecast_zip" {
  bucket      = aws_s3_bucket.deploy.id
  key         = "forecast.zip"
  source      = "${path.module}/build/forecast.zip"
  source_hash = filebase64sha256("${path.module}/build/forecast.zip")
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter {}
    expiration { days = 7 }
  }
}

resource "aws_s3_bucket_notification" "bronze_to_enrich" {
  bucket = aws_s3_bucket.bronze.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.enrich.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.allow_bronze_invoke]
}
