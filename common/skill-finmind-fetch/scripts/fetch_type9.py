#!/usr/bin/env python3
"""Fetch FinMind daily prices and export a GoodInfo Type 9 (StockHisAnaQuar) CSV."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fetch_to_csv import fetch_data
from price_cache import cached_price
from token_env import TokenRotator
load_dotenv()

QUARTER_LABELS = ["第一季", "第二季", "第三季", "第四季"]
COLUMNS = ["stock_code", "company_name", "年度"]
for q in QUARTER_LABELS:
    COLUMNS += [f"{q}_開盤_元", f"{q}_收盤_元", f"{q}_漲跌_元", f"{q}_漲跌_pct"]
COLUMNS += ["file_type", "source_file", "download_success", "download_timestamp", "process_timestamp", "stage1_process_timestamp"]


def build(stock_id, name, prices):
    px = pd.DataFrame(prices)
    if px.empty:
        return pd.DataFrame(columns=COLUMNS)
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px = px.dropna(subset=["date"]).sort_values("date")
    px["year"] = px.date.dt.year
    px["quarter"] = px.date.dt.quarter

    quarters = {}
    for (year, q), g in px.groupby(["year", "quarter"]):
        quarters[(year, q)] = {"open": float(g.iloc[0].open), "close": float(g.iloc[-1].close)}

    rows = []
    timestamp = datetime.now().isoformat(timespec="seconds")
    previous_close = np.nan
    for year in sorted(px.year.unique()):
        row = {"stock_code": str(stock_id).zfill(4), "company_name": name, "年度": str(int(year))}
        for i, label in enumerate(QUARTER_LABELS, start=1):
            data = quarters.get((year, i))
            if data:
                close = data["close"]
                change = close - previous_close if pd.notna(previous_close) else np.nan
                row[f"{label}_開盤_元"] = data["open"]
                row[f"{label}_收盤_元"] = close
                row[f"{label}_漲跌_元"] = change
                row[f"{label}_漲跌_pct"] = round(change / previous_close * 100, 2) if pd.notna(change) and previous_close else np.nan
                previous_close = close
            else:
                row[f"{label}_開盤_元"] = np.nan
                row[f"{label}_收盤_元"] = np.nan
                row[f"{label}_漲跌_元"] = np.nan
                row[f"{label}_漲跌_pct"] = np.nan
        row.update({
            "file_type": "StockHisAnaQuar",
            "source_file": f"FinMind_API_TaiwanStockPrice_{str(stock_id).zfill(4)}",
            "download_success": True,
            "download_timestamp": timestamp,
            "process_timestamp": timestamp,
            "stage1_process_timestamp": timestamp,
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stock-id', default='2330')
    p.add_argument('--company-name', default='台積電')
    p.add_argument('--start-date', default='2018-01-01')
    p.add_argument('--end-date', default=(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d'))
    p.add_argument('--output', default='financial/type9/raw_stock_his_quar_2330.csv')
    p.add_argument('--token', default=None)
    p.add_argument('--price-cache-dir', default=None)
    a = p.parse_args()
    rot = TokenRotator(a.token)
    px = cached_price(a.stock_id, a.start_date, a.end_date, rot, a.price_cache_dir, fetch_data)
    out = build(a.stock_id, a.company_name, px.to_dict('records'))
    if out.empty:
        raise SystemExit('No price data available')
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.output, index=False, encoding='utf-8-sig')
    print(f'Wrote {len(out)} quarterly price rows to {a.output}')


if __name__ == '__main__':
    main()
