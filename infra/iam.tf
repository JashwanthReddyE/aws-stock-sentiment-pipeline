data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name               = "${var.project}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    sid = "S3DataLake"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads",
      "s3:ListMultipartUploadParts",
      "s3:AbortMultipartUpload",
    ]
    resources = [
      aws_s3_bucket.bronze.arn,
      "${aws_s3_bucket.bronze.arn}/*",
      aws_s3_bucket.silver.arn,
      "${aws_s3_bucket.silver.arn}/*",
      aws_s3_bucket.gold.arn,
      "${aws_s3_bucket.gold.arn}/*",
      aws_s3_bucket.athena_results.arn,
      "${aws_s3_bucket.athena_results.arn}/*",
    ]
  }

  statement {
    sid     = "BedrockInvoke"
    actions = ["bedrock:InvokeModel"]
    # Cross-region inference profiles route to multiple regions, so we need to grant
    # access to the inference profile AND the underlying foundation models in each region.
    resources = [
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
    ]
  }

  statement {
    sid = "AthenaGlueQuery"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:StopQueryExecution",
      "glue:GetTable",
      "glue:GetDatabase",
      "glue:GetPartitions",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_inline" {
  name   = "${var.project}-lambda-inline"
  role   = aws_iam_role.lambda_role.id
  policy = data.aws_iam_policy_document.lambda_inline.json
}
