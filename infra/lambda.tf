# Lambda zips are pre-built by build-lambdas.ps1 and uploaded to S3 (see s3.tf).
# Using S3-based deployment to bypass the 70MB direct-upload limit (S3 limit is 250MB).

resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project}-ingest"
  s3_bucket        = aws_s3_bucket.deploy.id
  s3_key           = aws_s3_object.ingest_zip.key
  source_code_hash = aws_s3_object.ingest_zip.source_hash
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      BRONZE_BUCKET   = aws_s3_bucket.bronze.id
      TICKERS         = join(",", var.tickers)
      FINNHUB_API_KEY = var.finnhub_api_key
    }
  }

  tags = local.tags
}

resource "aws_lambda_function" "enrich" {
  function_name    = "${var.project}-enrich"
  s3_bucket        = aws_s3_bucket.deploy.id
  s3_key           = aws_s3_object.enrich_zip.key
  source_code_hash = aws_s3_object.enrich_zip.source_hash
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 1024

  environment {
    variables = {
      SILVER_BUCKET    = aws_s3_bucket.silver.id
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }

  tags = local.tags
}

resource "aws_lambda_function" "forecast" {
  function_name    = "${var.project}-forecast"
  s3_bucket        = aws_s3_bucket.deploy.id
  s3_key           = aws_s3_object.forecast_zip.key
  source_code_hash = aws_s3_object.forecast_zip.source_hash
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 900
  memory_size      = 2048

  environment {
    variables = {
      GOLD_BUCKET           = aws_s3_bucket.gold.id
      SILVER_BUCKET         = aws_s3_bucket.silver.id
      ATHENA_DATABASE       = aws_glue_catalog_database.lake.name
      ATHENA_OUTPUT         = "s3://${aws_s3_bucket.athena_results.id}/"
      BEDROCK_MODEL_ID      = var.bedrock_model_id
      TICKERS               = join(",", var.tickers)
      ALPHA_VANTAGE_API_KEY = var.alpha_vantage_api_key
    }
  }

  tags = local.tags
}

resource "aws_lambda_permission" "allow_bronze_invoke" {
  statement_id  = "AllowBronzeS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.enrich.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.bronze.arn
}
