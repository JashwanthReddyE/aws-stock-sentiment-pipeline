"""Ingest Lambda: pulls latest company news (Finnhub) per ticker → bronze/.

Price ingestion has been moved to the forecast Lambda (Alpha Vantage daily bars).
Finnhub free tier returns zeros for /quote and walls off /stock/candle entirely,
so this Lambda focuses on what Finnhub free tier actually delivers: news.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import boto3

s3 = boto3.client("s3")

BRONZE_BUCKET = os.environ["BRONZE_BUCKET"]
TICKERS = [t.strip() for t in os.environ["TICKERS"].split(",") if t.strip()]
FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_news(ticker: str, lookback_hours: int = 24) -> list[dict]:
    """Finnhub uses base symbol (no exchange suffix). For .TO map to TSX symbol if known."""
    symbol = ticker.split(".")[0]
    to_ts = int(time.time())
    from_ts = to_ts - lookback_hours * 3600
    qs = urlencode({
        "symbol": symbol,
        "from": datetime.fromtimestamp(from_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "to": datetime.fromtimestamp(to_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "token": FINNHUB_API_KEY,
    })
    req = Request(f"{FINNHUB_BASE}/company-news?{qs}", headers={"User-Agent": "stock-sentiment/1.0"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _put(bucket: str, key: str, payload: dict) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, default=str).encode(),
        ContentType="application/json",
    )


def lambda_handler(event, context):
    now = datetime.now(timezone.utc)
    dt_part = now.strftime("%Y-%m-%d")
    hh_part = now.strftime("%H")
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    summary = {"ingested_at": now.isoformat(), "tickers": []}

    for ticker in TICKERS:
        try:
            news = _finnhub_news(ticker)
        except Exception as exc:
            news, news_err = [], str(exc)
        else:
            news_err = None

        payload = {
            "ticker": ticker,
            "ingested_at": now.isoformat(),
            "run_id": run_id,
            "news": news,
            "errors": {"news": news_err},
        }
        key = f"dt={dt_part}/hh={hh_part}/{ticker.replace('.', '_')}_{run_id}.json"
        _put(BRONZE_BUCKET, key, payload)
        summary["tickers"].append({
            "ticker": ticker,
            "news": len(news),
            "key": key,
        })

    return summary
