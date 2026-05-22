resource "aws_glue_catalog_database" "lake" {
  name = replace("${var.project}_lake", "-", "_")
}

resource "aws_iam_role" "glue_crawler" {
  name = "${var.project}-glue-crawler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_crawler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3" {
  name = "${var.project}-glue-s3"
  role = aws_iam_role.glue_crawler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.silver.arn,
        "${aws_s3_bucket.silver.arn}/*",
        aws_s3_bucket.gold.arn,
        "${aws_s3_bucket.gold.arn}/*",
      ]
    }]
  })
}

resource "aws_glue_crawler" "silver" {
  name          = "${var.project}-silver-crawler"
  role          = aws_iam_role.glue_crawler.arn
  database_name = aws_glue_catalog_database.lake.name
  schedule      = "cron(15 21 ? * MON-FRI *)" # 15 min after forecast cron

  # Crawl each top-level prefix separately so we get distinct tables
  # (sentiment, prices, forecasts) instead of one merged table.
  s3_target {
    path = "s3://${aws_s3_bucket.silver.id}/sentiment/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.silver.id}/prices/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.gold.id}/forecasts/"
  }

  tags = local.tags
}
