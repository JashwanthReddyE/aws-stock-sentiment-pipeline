# Ingest: every 30 minutes during US market hours (9:30–16:00 ET → 13:30–20:00 UTC, Mon–Fri).
resource "aws_cloudwatch_event_rule" "ingest_schedule" {
  name                = "${var.project}-ingest-schedule"
  description         = "Trigger ingest Lambda every 30 min during market hours"
  schedule_expression = "cron(0/30 13-20 ? * MON-FRI *)"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "ingest_target" {
  rule      = aws_cloudwatch_event_rule.ingest_schedule.name
  target_id = "ingest-lambda"
  arn       = aws_lambda_function.ingest.arn
}

resource "aws_lambda_permission" "allow_eventbridge_ingest" {
  statement_id  = "AllowEventBridgeIngest"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest_schedule.arn
}

# Forecast: daily at 21:00 UTC (17:00 ET, ~1 hour after close).
resource "aws_cloudwatch_event_rule" "forecast_schedule" {
  name                = "${var.project}-forecast-schedule"
  description         = "Daily Prophet forecast + Bedrock market brief"
  schedule_expression = "cron(0 21 ? * MON-FRI *)"
  tags                = local.tags
}

resource "aws_cloudwatch_event_target" "forecast_target" {
  rule      = aws_cloudwatch_event_rule.forecast_schedule.name
  target_id = "forecast-lambda"
  arn       = aws_lambda_function.forecast.arn
}

resource "aws_lambda_permission" "allow_eventbridge_forecast" {
  statement_id  = "AllowEventBridgeForecast"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.forecast.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.forecast_schedule.arn
}
