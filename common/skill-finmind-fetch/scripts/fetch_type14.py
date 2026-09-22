#!/usr/bin/env python3
"""Build GoodInfo-compatible Type 14 weekly margin CSV from Type 13 daily data."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from fetch_to_csv import fetch_data, process_stock_data
from token_env import TokenRotator

load_dotenv()

OUTPUT_COLUMNS = [
    "stock_code", "company_name", "期別", "收盤_價格_元", "漲跌_價格_元", "漲跌_pct", "成交_張數",
    "融資_買進_張", "融資_賣出_張", "融資_現償_張", "融資_增減_張", "融資_餘額_張", "融資_使用率_pct",
    "融券_買進_張", "融券_賣出_張", "融券_現償_張", "融券_增減_張", "融券_餘額_張", "融券_使用率_pct",
    "資券互抵_張", "資券當沖_pct", "券資比_pct", "現股當沖_pct", "file_type", "source_file",
    "download_success", "download_timestamp", "process_timestamp", "stage1_process_timestamp",
]
FLOW_COLUMNS = [
    "融資_買進_張", "融資_賣出_張", "融資_現償_張", "融資_增減_張",
    "融券_買進_張", "融券_賣出_張", "融券_現償_張", "融券_增減_張", "資券互抵_張",
]
LAST_COLUMNS = ["收盤_價格_元", "融資_餘額_張", "融資_使用率_pct", "融券_餘額_張", "融券_使用率_pct", "資券當沖_pct", "現股當沖_pct", "券資比_pct"]


def parse_daily_date(value):
    value = str(value).strip().lstrip("'")
    for fmt in ("%y/%m/%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return pd.NaT


def week_label(dt):
    iso = dt.isocalendar()
    return f"{iso.year % 100:02d}W{iso.week:02d}"


def numeric(df, columns):
    for column in columns:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")


def aggregate_weekly(daily, stock_code, company_name):
    required = {"期別", "收盤_價格_元"}
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f"daily CSV missing columns: {sorted(missing)}")
    daily = daily.copy()
    daily["_date"] = pd.to_datetime(daily["期別"].map(parse_daily_date), errors="coerce")
    daily = daily.dropna(subset=["_date"]).sort_values("_date")
    if stock_code:
        daily = daily[daily["stock_code"].astype(str).str.zfill(4) == str(stock_code).zfill(4)]
    if daily.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    numeric(daily, [c for c in daily.columns if c not in {"stock_code", "company_name", "期別", "_date", "_week"}])
    daily["_week"] = daily["_date"] - pd.to_timedelta(daily["_date"].dt.weekday, unit="D")
    rows = []
    previous_close = None
    timestamp = datetime.now().isoformat(timespec="seconds")
    for week_start, group in daily.groupby("_week", sort=True):
        group = group.sort_values("_date")
        last = group.iloc[-1]
        close = last.get("收盤_價格_元")
        change = close - previous_close if pd.notna(close) and previous_close is not None else np.nan
        change_pct = change / previous_close * 100 if pd.notna(change) and previous_close not in (None, 0) else np.nan
        row = {
            "stock_code": str(stock_code or last.get("stock_code", "")).zfill(4),
            "company_name": company_name or last.get("company_name", ""),
            "期別": week_label(week_start),
            "收盤_價格_元": close,
            "漲跌_價格_元": change,
            "漲跌_pct": round(change_pct, 2) if pd.notna(change_pct) else np.nan,
            # Type 14 reports aggregate volume in lots, like Type 13.
            "成交_張數": round(group["成交_張數"].sum()) if "成交_張數" in group else np.nan,
            "file_type": "ShowMarginChartWeek",
            "source_file": f"FinMind_API_TaiwanStockMarginPurchaseShortSale_{str(stock_code).zfill(4)}",
            "download_success": True,
            "download_timestamp": timestamp,
            "process_timestamp": timestamp,
            "stage1_process_timestamp": timestamp,
        }
        for column in FLOW_COLUMNS:
            row[column] = group[column].sum(min_count=1) if column in group else np.nan
        for column in LAST_COLUMNS:
            if column in group:
                row[column] = last[column]
        rows.append(row)
        if pd.notna(close):
            previous_close = close
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def fetch_daily(stock_id, start_date, end_date, token, company_name):
    price = fetch_data("TaiwanStockPrice", data_id=stock_id, start_date=start_date, end_date=end_date, token=token)
    margin = fetch_data("TaiwanStockMarginPurchaseShortSale", data_id=stock_id, start_date=start_date, end_date=end_date, token=token)
    if price.empty or margin.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return process_stock_data(stock_id, price, margin, company_name)


def main():
    parser = argparse.ArgumentParser(description="Build FinMind/GoodInfo-compatible Type 14 weekly margin CSV.")
    parser.add_argument("--stock-id", default="2330")
    parser.add_argument("--company-name", default="台積電")
    parser.add_argument("--daily-csv", help="Existing Type 13 daily CSV; avoids refetching daily data.")
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default=(datetime.now() + timedelta(hours=8)).strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="financial/type14/raw_margin_weekly_2330.csv")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    if args.daily_csv:
        daily = pd.read_csv(args.daily_csv, dtype={"stock_code": str})
    else:
        daily = fetch_daily(args.stock_id, args.start_date, args.end_date, TokenRotator(args.token), args.company_name)
    weekly = aggregate_weekly(daily, args.stock_id, args.company_name)
    if weekly.empty:
        raise SystemExit("No daily data available for Type 14")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"Wrote {len(weekly)} weekly rows to {args.output}")


if __name__ == "__main__":
    main()
