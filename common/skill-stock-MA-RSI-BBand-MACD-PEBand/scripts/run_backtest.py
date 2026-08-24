#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_backtest.py — CLI 進入點：對一批股票跑 backtest.py 的(0)~(13b)條件分類法歷史回測，
每個horizon（預設60/180/360日）各輸出一張CSV（長格式：一列=一檔股票一個條件）。

用法：

  # Fugle為主要來源（預設），2016年至今，60/180/360日窗口
  python run_backtest.py --symbols 3045 2480 2412 --fugle-env-prefix USER1_ \
    --start 2016-01-01 --output-dir output/

  # 只用yfinance（不需要Fugle憑證）
  python run_backtest.py --source yahoo --symbols 3045.TW 2480.TWO 2412.TW \
    --start 2016-01-01 --output-dir output/

  # 自訂RSI週期（例如跟「股票決策摘要」P欄RSI(20)對齊）
  python run_backtest.py --symbols 0052 --fugle-env-prefix USER1_ --rsi-period 20 \
    --start 2016-01-01 --output-dir output/

輸出：<output-dir>/backtest_<symbol>.csv，欄位：key,label,n,per_year,horizon,n_h,avg,win
（n/per_year是條件本身的全樣本觸發次數；n_h/avg/win是該horizon下的forward報酬統計，
avg/win為None代表該horizon下這個條件從沒觸發過或全部落在資料尾端無法算forward報酬）。
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from price_loader import login_fugle, fetch_fugle_adjusted, fetch_fugle_market_adjustment_events, fetch_yahoo_adjusted
from backtest import backtest_conditions

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=True)
except ImportError:
    pass


def rows_from_results(symbol: str, results: list[dict]) -> list[dict]:
    rows = []
    for r in results:
        for h, s in r["horizons"].items():
            rows.append({
                "symbol": symbol, "key": r["key"], "label": r["label"],
                "n": r["n"], "per_year": r["per_year"],
                "horizon": h, "n_h": s["n"], "avg": s["avg"], "win": s["win"],
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="+", help="直接指定代號清單（Fugle來源用純代號，yahoo來源要用yfinance ticker）")
    parser.add_argument("--list", help="從CSV讀取代號清單（欄位：代號/symbol/stock_code，可選yahoo_symbol）")
    parser.add_argument("--source", choices=["fugle", "yahoo"], default="fugle")
    parser.add_argument("--fugle-env-prefix", default="")
    parser.add_argument("--start", required=True, help="回測起始日 YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--crash-threshold", type=float, default=-3.0)
    parser.add_argument("--horizons", default="60,180,360")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    if not args.symbols and not args.list:
        parser.error("必須指定 --symbols 或 --list 其中一個")
    horizons = [int(h) for h in args.horizons.split(",")]

    if args.list:
        df = pd.read_csv(args.list, dtype=str)
        code_col = next((c for c in ["代號", "symbol", "stock_code"] if c in df.columns), None)
        symbols = [str(v).strip() for v in df[code_col] if str(v).strip()]
    else:
        symbols = args.symbols

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.source == "fugle":
        sdk, acc = login_fugle(args.fugle_env_prefix)
        rc = sdk.marketdata.rest_client
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").date()
        print(f"抓取還原調整事件（除息+減資/分割），{start_dt}~{end_dt}...")
        events = fetch_fugle_market_adjustment_events(rc, start_dt, end_dt)

    for symbol in symbols:
        print(f"\n=== {symbol} ===")
        if args.source == "fugle":
            close = fetch_fugle_adjusted(rc, symbol, market_events=events,
                                          start_date=start_dt, end_date=end_dt)
        else:
            close = fetch_yahoo_adjusted(symbol, period="max")
        close = close[(close.index >= args.start) & (close.index <= args.end)]
        if close.empty:
            print(f"⚠️ 無資料，略過")
            continue
        print(f"  {len(close)}筆日線，{close.index[0].date()}~{close.index[-1].date()}")

        results = backtest_conditions(close, rsi_period=args.rsi_period,
                                       crash_threshold=args.crash_threshold, horizons=tuple(horizons))
        rows = rows_from_results(symbol, results)
        out_df = pd.DataFrame(rows)
        out_path = out_dir / f"backtest_{symbol.replace('.', '_')}.csv"
        out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 已寫出 {out_path}")


if __name__ == "__main__":
    main()
