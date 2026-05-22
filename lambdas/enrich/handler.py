"""Enrich Lambda: S3 PutObject on bronze/ → Bedrock sentiment → Parquet silver/."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import unquote_plus

import boto3
import pandas as pd

from prompts import SENTIMENT_SYSTEM, SENTIMENT_USER_TEMPLATE

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

SILVER_BUCKET = os.environ["SILVER_BUCKET"]
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _score_headline(ticker: str, headline: str, summary: str) -> dict:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "system": SENTIMENT_SYSTEM,
        "messages": [{
            "role": "user",
            "content": [{
                "type": "text",
                "text": SENTIMENT_USER_TEMPLATE.format(
                    ticker=ticker,
                    headline=headline[:300],
                    summary=(summary or "")[:600],
                ),
            }],
        }],
    }
    resp = bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    text = payload["content"][0]["text"]
    match = JSON_RE.search(text)
    if not match:
        return {"sentiment": 0.0, "confidence": 0.0, "reason": "parse_failed"}
    try:
        parsed = json.loads(match.group(0))
        return {
            "sentiment": float(parsed.get("sentiment", 0.0)),
            "confidence": float(parsed.get("confidence", 0.0)),
            "reason": str(parsed.get("reason", ""))[:200],
        }
    except (ValueError, KeyError):
        return {"sentiment": 0.0, "confidence": 0.0, "reason": "parse_failed"}


def _process_object(bucket: str, key: str) -> dict:
    obj = s3.get_object(Bucket=bucket, Key=key)
    raw = json.loads(obj["Body"].read())
    ticker = raw["ticker"]
    ingested_at = raw["ingested_at"]
    dt_part = ingested_at[:10]

    # Sentiment for each headline, dedup by URL. Cap at 20 to stay within Lambda timeout.
    seen_urls: set[str] = set()
    sentiment_rows: list[dict] = []
    MAX_HEADLINES = 20
    for item in raw.get("news", [])[:MAX_HEADLINES]:
        url = item.get("url") or item.get("id") or ""
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        headline = item.get("headline") or ""
        if not headline:
            continue
        score = _score_headline(ticker, headline, item.get("summary", ""))
        sentiment_rows.append({
            "ticker": ticker,
            "ingested_at": ingested_at,
            "headline_at": datetime.fromtimestamp(
                item.get("datetime", 0), tz=timezone.utc
            ).isoformat() if item.get("datetime") else None,
            "headline": headline,
            "url": url,
            "source": item.get("source"),
            "sentiment": score["sentiment"],
            "confidence": score["confidence"],
            "reason": score["reason"],
        })

    # Price rows pass through unchanged but typed.
    price_rows = [{
        "ticker": ticker,
        "timestamp": p["timestamp"],
        "open": float(p["Open"]) if p.get("Open") is not None else None,
        "high": float(p["High"]) if p.get("High") is not None else None,
        "low": float(p["Low"]) if p.get("Low") is not None else None,
        "close": float(p["Close"]) if p.get("Close") is not None else None,
        "volume": int(p["Volume"]) if p.get("Volume") is not None else None,
    } for p in raw.get("prices", [])]

    written = []
    if sentiment_rows:
        sentiment_key = f"sentiment/dt={dt_part}/{ticker.replace('.', '_')}_{raw['run_id']}.parquet"
        _write_parquet(SILVER_BUCKET, sentiment_key, sentiment_rows)
        written.append(sentiment_key)

    if price_rows:
        prices_key = f"prices/dt={dt_part}/{ticker.replace('.', '_')}_{raw['run_id']}.parquet"
        _write_parquet(SILVER_BUCKET, prices_key, price_rows)
        written.append(prices_key)

    return {"ticker": ticker, "sentiment_rows": len(sentiment_rows), "price_rows": len(price_rows), "written": written}


def _write_parquet(bucket: str, key: str, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    buf = BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())


def lambda_handler(event, context):
    out = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        out.append(_process_object(bucket, key))
    return {"processed": out}
