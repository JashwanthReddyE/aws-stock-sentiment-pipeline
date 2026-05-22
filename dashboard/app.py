"""Streamlit dashboard for the Stock Sentiment & Forecast pipeline."""
from __future__ import annotations

import json
import os
import time
from io import BytesIO

import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

REGION = os.environ.get("AWS_REGION", "us-east-1")
SILVER_BUCKET = os.environ["SILVER_BUCKET"]
GOLD_BUCKET = os.environ["GOLD_BUCKET"]
ATHENA_DATABASE = os.environ["ATHENA_DATABASE"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT"]

s3 = boto3.client("s3", region_name=REGION)
athena = boto3.client("athena", region_name=REGION)

st.set_page_config(page_title="Stock Sentiment & Forecast", layout="wide", page_icon=":chart_with_upwards_trend:")


@st.cache_data(ttl=300)
def run_query(sql: str) -> pd.DataFrame:
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )["QueryExecutionId"]
    while True:
        state = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query failed: {state}")

    rows, headers = [], []
    for i, page in enumerate(athena.get_paginator("get_query_results").paginate(QueryExecutionId=qid)):
        for j, row in enumerate(page["ResultSet"]["Rows"]):
            vals = [c.get("VarCharValue") for c in row["Data"]]
            if i == 0 and j == 0:
                headers = vals
            else:
                rows.append(vals)
    return pd.DataFrame(rows, columns=headers)


@st.cache_data(ttl=300)
def load_latest_forecast() -> pd.DataFrame:
    resp = s3.list_objects_v2(Bucket=GOLD_BUCKET, Prefix="forecasts/")
    keys = sorted([o["Key"] for o in resp.get("Contents", [])])
    if not keys:
        return pd.DataFrame()
    obj = s3.get_object(Bucket=GOLD_BUCKET, Key=keys[-1])
    return pd.read_parquet(BytesIO(obj["Body"].read()))


@st.cache_data(ttl=300)
def load_latest_brief() -> tuple[str, str]:
    resp = s3.list_objects_v2(Bucket=GOLD_BUCKET, Prefix="briefs/")
    keys = sorted([o["Key"] for o in resp.get("Contents", [])])
    if not keys:
        return "", ""
    obj = s3.get_object(Bucket=GOLD_BUCKET, Key=keys[-1])
    payload = json.loads(obj["Body"].read())
    return payload.get("date", ""), payload.get("brief", "")


st.title(":chart_with_upwards_trend: Stock Sentiment & Forecast Pipeline")
st.caption("AWS · Lambda · S3 · Athena · Bedrock (Claude Haiku) · Prophet")

tab_prices, tab_sentiment, tab_ai = st.tabs(["Live Prices", "Sentiment Heatmap", "AI Forecast & Brief"])

with tab_prices:
    prices = run_query("""
        SELECT ticker, timestamp, close
        FROM prices
        WHERE from_iso8601_timestamp(timestamp) > current_timestamp - interval '60' day
        ORDER BY ticker, timestamp
    """)
    if prices.empty:
        st.info("No price data yet — wait for the ingest Lambda to run.")
    else:
        prices["timestamp"] = pd.to_datetime(prices["timestamp"])
        prices["close"] = prices["close"].astype(float)
        fig = px.line(prices, x="timestamp", y="close", color="ticker", height=600)
        st.plotly_chart(fig, use_container_width=True)

with tab_sentiment:
    sent = run_query("""
        SELECT ticker,
               substr(ingested_at, 1, 13) AS hour,
               avg(sentiment) AS avg_sentiment,
               count(*) AS headlines
        FROM sentiment
        WHERE from_iso8601_timestamp(ingested_at) > current_timestamp - interval '3' day
        GROUP BY ticker, substr(ingested_at, 1, 13)
        ORDER BY hour
    """)
    if sent.empty:
        st.info("No sentiment scores yet — wait for the enrich Lambda to process headlines.")
    else:
        sent["avg_sentiment"] = sent["avg_sentiment"].astype(float)
        pivot = sent.pivot(index="ticker", columns="hour", values="avg_sentiment")
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values, x=pivot.columns, y=pivot.index,
            colorscale="RdYlGn", zmid=0, zmin=-1, zmax=1,
        ))
        fig.update_layout(height=500, title="Average headline sentiment by ticker × hour (UTC)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(sent, use_container_width=True)

with tab_ai:
    col1, col2 = st.columns([2, 3])

    with col1:
        st.subheader("5-Day Forecast (Prophet)")
        fc = load_latest_forecast()
        if fc.empty:
            st.info("No forecast yet — runs daily at 21:00 UTC.")
        else:
            ticker_pick = st.selectbox("Ticker", sorted(fc["ticker"].unique()))
            sub = fc[fc["ticker"] == ticker_pick].copy()
            sub["ds"] = pd.to_datetime(sub["ds"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=sub["ds"], y=sub["yhat"], name="Forecast", line=dict(color="royalblue")))
            fig.add_trace(go.Scatter(
                x=list(sub["ds"]) + list(sub["ds"][::-1]),
                y=list(sub["yhat_upper"]) + list(sub["yhat_lower"][::-1]),
                fill="toself", fillcolor="rgba(65,105,225,0.2)", line=dict(color="rgba(0,0,0,0)"),
                name="95% interval", showlegend=True,
            ))
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Daily AI Market Brief")
        date, brief = load_latest_brief()
        if not brief:
            st.info("No brief yet — runs daily at 21:00 UTC after forecast.")
        else:
            st.caption(f"Generated by Amazon Bedrock · Claude Haiku · {date}")
            # Escape $ so Streamlit's markdown engine doesn't treat them as LaTeX delimiters
            st.markdown(brief.replace("$", "\\$"))
