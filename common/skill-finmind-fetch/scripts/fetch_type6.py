#!/usr/bin/env python3
"""Fetch FinMind shareholding data and export a GoodInfo Type 6 (EquityDistribution) CSV.

FinMind's TaiwanStockShareholding only reports foreign-investment ownership
(no government/financial/domestic-institution breakdown), so this adapter can
only fill the aggregate foreign-investment column (僑外投資_合計_pct) plus
price. Every other institutional-holder column GoodInfo tracks has no FinMind
source and is left blank rather than guessed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fetch_to_csv import fetch_data
from price_cache import cached_dataset, cached_price
from token_env import TokenRotator
load_dotenv()

COLUMNS = ["stock_code", "company_name", "年度", "收盤_價格_元", "漲跌_價格_元", "漲跌_pct",
           "政府公營機構_pct", "金融機構_pct", "證券投信_pct",
           "僑外投資_僑外_pct", "僑外投資_證券_pct", "僑外投資_僑外自然人_pct", "僑外投資_合計_pct",
           "本國金融機構_金融機構_pct", "本國金融機構_證券投信_pct", "本國金融機構_合計_pct",
           "本國法人_公司法人_pct", "本國法人_其他法人_pct", "本國法人_合計_pct", "本國自然人_個人_pct",
           "file_type", "source_file", "download_success", "download_timestamp", "process_timestamp", "stage1_process_timestamp"]


def price_by_year(prices):
    px = pd.DataFrame(prices)
    if px.empty:
        return {}
    px["date"] = pd.to_datetime(px["date"], errors="coerce")
    px = px.dropna(subset=["date"]).sort_values("date")
    px["year"] = px.date.dt.year.astype(str)
    return {year: float(g.iloc[-1].close) for year, g in px.groupby("year")}


def build(stock_id, name, shareholding, prices):
    sh = pd.DataFrame(shareholding)
    if sh.empty:
        return pd.DataFrame(columns=COLUMNS)
    sh["date"] = pd.to_datetime(sh["date"], errors="coerce")
    sh = sh.dropna(subset=["date"]).sort_values("date")
    sh["year"] = sh.date.dt.year.astype(str)
    year_end = sh.groupby("year").last()  # last available weekly snapshot per year
    closes = price_by_year(prices)

    rows = []
    timestamp = datetime.now().isoformat(timespec="seconds")
    previous_close = np.nan
    for year, snap in year_end.iterrows():
        close = closes.get(year, np.nan)
        change = close - previous_close if pd.notna(close) and pd.notna(previous_close) else np.nan
        foreign_ratio = snap.get("ForeignInvestmentSharesRatio")
        row = {
            "stock_code": str(stock_id).zfill(4), "company_name": name, "年度": year,
            "收盤_價格_元": close, "漲跌_價格_元": change,
            "漲跌_pct": round(change / previous_close * 100, 2) if pd.notna(change) and previous_close else np.nan,
            "政府公營機構_pct": np.nan, "金融機構_pct": np.nan, "證券投信_pct": np.nan,
            "僑外投資_僑外_pct": np.nan, "僑外投資_證券_pct": np.nan, "僑外投資_僑外自然人_pct": np.nan,
            "僑外投資_合計_pct": round(foreign_ratio, 2) if pd.notna(foreign_ratio) else np.nan,
            "本國金融機構_金融機構_pct": np.nan, "本國金融機構_證券投信_pct": np.nan, "本國金融機構_合計_pct": np.nan,
            "本國法人_公司法人_pct": np.nan, "本國法人_其他法人_pct": np.nan, "本國法人_合計_pct": np.nan,
            "本國自然人_個人_pct": np.nan,
            "file_type": "EquityDistribution",
            "source_file": f"FinMind_API_TaiwanStockShareholding_{str(stock_id).zfill(4)}",
            "download_success": True, "download_timestamp": timestamp,
            "process_timestamp": timestamp, "stage1_process_timestamp": timestamp,
        }
        rows.append(row)
        if pd.notna(close):
            previous_close = close
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--stock-id', default='2330')
    p.add_argument('--company-name', default='台積電')
    p.add_argument('--start-date', default='2018-01-01')
    p.add_argument('--end-date', default=(datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d'))
    p.add_argument('--output', default='financial/type6/raw_equity_distribution_2330.csv')
    p.add_argument('--token', default=None)
    p.add_argument('--price-cache-dir', default=None)
    a = p.parse_args()
    rot = TokenRotator(a.token)
    sh = cached_dataset('TaiwanStockShareholding', a.stock_id, a.start_date, a.end_date, rot, a.price_cache_dir, fetch_data)
    px = cached_price(a.stock_id, a.start_date, a.end_date, rot, a.price_cache_dir, fetch_data)
    out = build(a.stock_id, a.company_name, sh.to_dict('records'), px.to_dict('records'))
    if out.empty:
        raise SystemExit('No shareholding data available')
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.output, index=False, encoding='utf-8-sig')
    print(f'Wrote {len(out)} annual equity distribution rows to {a.output}')


if __name__ == '__main__':
    main()
