terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "stock-sentiment"
}

variable "tickers" {
  type    = list(string)
  default = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META", "SHOP.TO", "RY.TO", "TD.TO"]
}

variable "finnhub_api_key" {
  type      = string
  sensitive = true
}

variable "alpha_vantage_api_key" {
  type        = string
  sensitive   = true
  description = "Alpha Vantage free-tier API key — used by forecast Lambda for daily price history"
}

variable "bedrock_model_id" {
  type        = string
  description = "Bedrock inference profile ID — Claude Haiku 4.5 requires the cross-region 'us.' prefix"
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

locals {
  tags = {
    Project   = var.project
    ManagedBy = "terraform"
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

output "bronze_bucket" { value = aws_s3_bucket.bronze.id }
output "silver_bucket" { value = aws_s3_bucket.silver.id }
output "gold_bucket"   { value = aws_s3_bucket.gold.id }
output "athena_database" { value = aws_glue_catalog_database.lake.name }
