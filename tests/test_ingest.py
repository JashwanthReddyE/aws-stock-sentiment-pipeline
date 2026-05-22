"""Smoke test the ingest Lambda's S3 writes via moto."""
import json
import os
import sys
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "ingest"))


@mock_aws
def test_ingest_writes_object(monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="bronze")

    monkeypatch.setenv("BRONZE_BUCKET", "bronze")
    monkeypatch.setenv("TICKERS", "AAPL")
    monkeypatch.setenv("FINNHUB_API_KEY", "test")

    import handler

    with patch.object(handler, "_finnhub_news", return_value=[{"headline": "x", "summary": "y", "url": "u", "source": "f", "datetime": 1716300000}]):
        out = handler.lambda_handler({}, None)

    assert out["tickers"][0]["ticker"] == "AAPL"
    assert out["tickers"][0]["news"] == 1
    listing = s3.list_objects_v2(Bucket="bronze")
    assert listing["KeyCount"] == 1
    body = json.loads(s3.get_object(Bucket="bronze", Key=listing["Contents"][0]["Key"])["Body"].read())
    assert body["ticker"] == "AAPL"
    assert len(body["news"]) == 1
