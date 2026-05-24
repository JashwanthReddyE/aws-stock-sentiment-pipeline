"""Smoke test the enrich Lambda's Bedrock parsing + Parquet write."""
import json
import os
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

import boto3
import pandas as pd
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "enrich"))


@mock_aws
def test_enrich_processes_object(monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="bronze")
    s3.create_bucket(Bucket="silver")

    raw = {
        "ticker": "AAPL",
        "ingested_at": "2026-05-21T13:30:00+00:00",
        "run_id": "20260521T133000Z",
        "prices": [{"timestamp": "2026-05-21T13:30", "Open": 1, "High": 2, "Low": 0.5, "Close": 1.5, "Volume": 100}],
        "news": [{"headline": "Apple beats earnings", "summary": "Strong iPhone sales", "url": "https://x/1", "source": "wsj", "datetime": 1716300000}],
        "errors": {"prices": None, "news": None},
    }
    s3.put_object(Bucket="bronze", Key="dt=2026-05-21/hh=13/AAPL_20260521T133000Z.json", Body=json.dumps(raw))

    monkeypatch.setenv("BRONZE_BUCKET", "bronze")
    monkeypatch.setenv("SILVER_BUCKET", "silver")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")

    import handler

    fake_bedrock_resp = {
        "body": MagicMock(read=lambda: json.dumps({
            "content": [{"text": '{"sentiment": 0.7, "confidence": 0.9, "reason": "earnings beat"}'}]
        }).encode())
    }
    with patch.object(handler, "bedrock", MagicMock(invoke_model=MagicMock(return_value=fake_bedrock_resp))):
        event = {"Records": [{"s3": {"bucket": {"name": "bronze"}, "object": {"key": "dt=2026-05-21/hh=13/AAPL_20260521T133000Z.json"}}}]}
        result = handler.lambda_handler(event, None)

    assert result["processed"][0]["sentiment_rows"] == 1
    assert result["processed"][0]["price_rows"] == 1

    sentiment_obj = s3.list_objects_v2(Bucket="silver", Prefix="sentiment/")
    assert sentiment_obj["KeyCount"] == 1
    df = pd.read_parquet(BytesIO(s3.get_object(Bucket="silver", Key=sentiment_obj["Contents"][0]["Key"])["Body"].read()))
    assert df["sentiment"].iloc[0] == 0.7
    assert df["ticker"].iloc[0] == "AAPL"
