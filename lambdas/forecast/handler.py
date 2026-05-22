"""Forecast Lambda: daily price forecast (Alpha Vantage) + sentiment from Athena + Bedrock brief → gold/.

Yahoo Finance blocks AWS IPs (so no yfinance). Finnhub free tier returns zeros for /quote
and walls off /stock/candle entirely. Alpha Vantage's TIME_SERIES_DAILY is free
(25 calls/day) and works for both US and TSX symbols — exactly what this daily-run
forecast needs.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from io import BytesIO

from urllib.request import Request, urlopen
from urllib.parse import urlencode

import boto3
import numpy as np
import pandas as pd

s3 = boto3.client("s3")
athena = boto3.client("athena")
bedrock = boto3.client("bedrock-runtime")

GOLD_BUCKET = os.environ["GOLD_BUCKET"]
SILVER_BUCKET = os.environ["SILVER_BUCKET"]
ATHENA_DATABASE = os.environ["ATHENA_DATABASE"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT"]
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
TICKERS = [t.strip() for t in os.environ["TICKERS"].split(",") if t.strip()]
ALPHA_VANTAGE_API_KEY = os.environ["ALPHA_VANTAGE_API_KEY"]
FORECAST_DAYS = 5

# Alpha Vantage uses .TRT for Toronto-listed symbols
ALPHA_VANTAGE_SYMBOL_MAP = {
    "SHOP.TO": "SHOP.TRT",
    "RY.TO":   "RY.TRT",
    "TD.TO":   "TD.TRT",
}


def _athena_query(sql: str) -> pd.DataFrame:
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )["QueryExecutionId"]
    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if state != "SUCCEEDED":
        reason = status.get("StateChangeReason", "(no reason returned)")
        raise RuntimeError(f"Athena query {qid} ended in state {state}: {reason}")

    rows, headers = [], []
    for i, page in enumerate(athena.get_paginator("get_query_results").paginate(QueryExecutionId=qid)):
        for j, row in enumerate(page["ResultSet"]["Rows"]):
            vals = [c.get("VarCharValue") for c in row["Data"]]
            if i == 0 and j == 0:
                headers = vals
            else:
                rows.append(vals)
    return pd.DataFrame(rows, columns=headers)


def _get_prices(ticker: str) -> pd.DataFrame:
    """Pull last 60 days of daily OHLCV from Alpha Vantage.

    Returns columns: ds (date string), open, high, low, close, volume.
    The forecast model uses 'close' as y; the silver-write step uses all columns.
    """
    symbol = ALPHA_VANTAGE_SYMBOL_MAP.get(ticker, ticker)
    qs = urlencode({
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": ALPHA_VANTAGE_API_KEY,
    })
    req = Request(
        f"https://www.alphavantage.co/query?{qs}",
        headers={"User-Agent": "stock-sentiment/1.0"},
    )
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    series = data.get("Time Series (Daily)")
    if not series:
        # AV returns 200 OK with a Note/Information field on rate-limit, Error Message on bad symbol
        msg = data.get("Note") or data.get("Information") or data.get("Error Message") or "no data"
        print(f"Alpha Vantage {ticker} ({symbol}): {msg}")
        return pd.DataFrame()

    rows = sorted(series.items())[-60:]
    df = pd.DataFrame([{
        "ds": d,
        "open":   float(v["1. open"]),
        "high":   float(v["2. high"]),
        "low":    float(v["3. low"]),
        "close":  float(v["4. close"]),
        "volume": int(v["5. volume"]),
    } for d, v in rows])
    return df.dropna(subset=["close"])


def _write_prices_to_silver(ticker: str, prices: pd.DataFrame, today: str) -> None:
    """Persist OHLCV bars to silver/prices/ so the dashboard's Live Prices tab has data."""
    if prices.empty:
        return
    df = prices.copy()
    df["ticker"] = ticker
    # Market-close timestamp (20:00 UTC = 4pm ET) so dashboard's interval filter is well-defined
    df["timestamp"] = df["ds"] + "T20:00:00+00:00"
    df = df[["ticker", "timestamp", "open", "high", "low", "close", "volume"]]
    buf = BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    key = f"prices/dt={today}/{ticker.replace('.', '_')}_daily.parquet"
    s3.put_object(Bucket=SILVER_BUCKET, Key=key, Body=buf.getvalue())


def _get_sentiment(ticker: str) -> pd.DataFrame:
    """Pull average daily sentiment from Athena silver layer."""
    try:
        sql = f"""
        SELECT
            substr(ingested_at, 1, 10) AS ds,
            avg(sentiment) AS sentiment
        FROM sentiment
        WHERE ticker = '{ticker}'
        GROUP BY substr(ingested_at, 1, 10)
        ORDER BY ds
        """
        df = _athena_query(sql)
        if df.empty:
            return pd.DataFrame()
        df["sentiment"] = df["sentiment"].astype(float)
        return df
    except Exception as exc:
        print(f"sentiment query failed for {ticker}: {exc}")
        return pd.DataFrame()


def _forecast_ticker(ticker: str, prices: pd.DataFrame) -> pd.DataFrame | None:
    """Weighted linear regression: 60-day price trend + sentiment multiplier → 5-day forecast."""
    if prices.empty or len(prices) < 5:
        return None

    sentiment = _get_sentiment(ticker)

    # Merge sentiment into prices
    df = prices.copy()
    if not sentiment.empty:
        df = df.merge(sentiment, on="ds", how="left")
        df["sentiment"] = df["sentiment"].fillna(0.0)
    else:
        df["sentiment"] = 0.0

    df = df.sort_values("ds").reset_index(drop=True)

    # Exponential-weighted linear trend on close prices
    x = np.arange(len(df))
    weights = np.exp(x / len(df))
    coeffs = np.polyfit(x, df["close"].values, deg=1, w=weights)
    slope, intercept = coeffs

    # Sentiment nudges the slope
    recent_sentiment = df["sentiment"].tail(7).mean()
    sentiment_boost = recent_sentiment * slope * 0.5

    # Project forward 5 business days
    last_x = len(df) - 1
    last_date = pd.to_datetime(df["ds"].iloc[-1])
    rows = []
    for i in range(1, FORECAST_DAYS + 1):
        future_x = last_x + i
        yhat = slope * future_x + intercept + sentiment_boost * i
        uncertainty = abs(yhat) * 0.015 * i
        future_date = last_date + pd.tseries.offsets.BDay(i)
        rows.append({
            "ticker": ticker,
            "ds": str(future_date.date()),
            "yhat": round(float(yhat), 4),
            "yhat_lower": round(float(yhat - uncertainty), 4),
            "yhat_upper": round(float(yhat + uncertainty), 4),
            "last_close": round(float(df["close"].iloc[-1]), 4),
            "sentiment_7d_avg": round(float(recent_sentiment), 4),
        })
    return pd.DataFrame(rows)


def _market_brief(forecasts: pd.DataFrame, today: str) -> str:
    fc_str = forecasts.to_string(index=False, max_rows=60)
    prompt = (
        f"You are a financial analyst. Today is {today}. "
        "Below is a 5-day price forecast for a watchlist of US and Canadian stocks. "
        "The 'sentiment_7d_avg' column reflects average news sentiment over the last 7 days "
        "(-1 = very bearish, 0 = neutral, +1 = very bullish).\n\n"
        "Write a concise 3-paragraph market brief for a retail investor:\n"
        "Paragraph 1: Overall tone of the watchlist — bullish, bearish, or mixed?\n"
        "Paragraph 2: 2-3 specific tickers worth watching and why (use forecast + sentiment).\n"
        "Paragraph 3: One honest caveat about the forecast's limitations.\n"
        "Plain prose only. No bullet points. No financial advice disclaimers.\n\n"
        f"Forecast data:\n{fc_str}"
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    resp = bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())["content"][0]["text"].strip()


def lambda_handler(event, context):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_forecasts: list[pd.DataFrame] = []

    for i, ticker in enumerate(TICKERS):
        # Alpha Vantage free tier rate-limits to 1 req/sec
        if i > 0:
            time.sleep(1.2)
        try:
            prices = _get_prices(ticker)
            _write_prices_to_silver(ticker, prices, today)
            fc = _forecast_ticker(ticker, prices)
            if fc is not None:
                all_forecasts.append(fc)
                print(f"forecast OK: {ticker}")
        except Exception as exc:
            print(f"forecast failed for {ticker}: {exc}")

    if not all_forecasts:
        return {"status": "no_data", "date": today}

    forecasts = pd.concat(all_forecasts, ignore_index=True)

    # Write forecast Parquet
    fc_key = f"forecasts/dt={today}/forecasts.parquet"
    buf = BytesIO()
    forecasts.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    s3.put_object(Bucket=GOLD_BUCKET, Key=fc_key, Body=buf.getvalue())

    # Generate AI market brief
    brief = _market_brief(forecasts, today)
    brief_key = f"briefs/dt={today}/brief.json"
    s3.put_object(
        Bucket=GOLD_BUCKET,
        Key=brief_key,
        Body=json.dumps({"date": today, "brief": brief}).encode(),
        ContentType="application/json",
    )

    return {
        "status": "ok",
        "date": today,
        "tickers_forecasted": len(all_forecasts),
        "forecast_key": fc_key,
        "brief_key": brief_key,
    }
