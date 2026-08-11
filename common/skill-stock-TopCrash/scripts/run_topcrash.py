#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_topcrash.py — CLI 進入點：抓一段年份範圍內某指數/股票的「崩盤 Top N」清單，
含 1/3/5/7/9/11日跌幅、事件標籤、VIX/CNN情境、恢復天數與形態(V/U修復)，輸出CSV。

輸出CSV欄位（跟GoogleSheet.Banks「崩盤Top50」分頁一致的表格結構）：
  排名, 最壞日期, 單日跌幅%, 3日跌幅%, 5日跌幅%, 7日跌幅%, 9日跌幅%, 11日跌幅%,
  最大跌幅%, 跌幅類型, 當日收盤, 事件,
  前5日 US VIX, 前3日 US VIX, 前1日 US VIX, US VIX,
  前5日 台灣VIX, 前3日 台灣VIX, 前1日 台灣VIX, 台灣VIX, CNN恐慌,
  恢復天數, 恢復形態(≤45天=V)

用法：

  # TAIEX（yfinance ^TWII）近10年崩盤Top50，門檻-3%
  python run_topcrash.py --symbol ^TWII --start 2016-01-01 --end 2026-08-10 \
    --top-n 50 --min-drop -3.0 --output crash_top50.csv

  # 加上VIX情境跟具名事件標籤
  python run_topcrash.py --symbol ^TWII --years 10 --output out.csv \
    --vix-csv raw_vix_merged.csv --events-csv raw_event_historical_crashes.csv \
    --named-events-json named_events.json

named_events.json 格式：
  [{"name": "全球COVID 2020/2", "start": "2020-01-30", "end": "2021-06-30"}, ...]
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from crash_detector import find_top_crashes, DROP_WINDOWS
from event_labeler import build_event_labeler
from vix_context import load_vix_csv, get_vix_context
from recovery import calc_recovery

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_close_series(symbol: str, start: str, end: str) -> pd.Series:
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    df = df.dropna().squeeze()
    df.index = pd.to_datetime(df.index)
    return df


def build_row(rank: int, entry: dict, vix_ctx: dict | None, rec: dict) -> dict:
    row = {
        "排名": rank,
        "最壞日期": entry["date"].strftime("%Y-%m-%d"),
    }
    for n in DROP_WINDOWS:
        label = {1: "單日跌幅%", 3: "3日跌幅%", 5: "5日跌幅%", 7: "7日跌幅%", 9: "9日跌幅%", 11: "11日跌幅%"}[n]
        row[label] = round(entry[f"d{n}"], 2)
    row["最大跌幅%"] = round(entry["worst"], 2)
    row["跌幅類型"] = entry["worst_type"]
    row["當日收盤"] = round(entry["close"], 0)
    row["事件"] = entry["event"]

    if vix_ctx:
        row["前5日 US VIX"] = vix_ctx["us_vix_5d"]
        row["前3日 US VIX"] = vix_ctx["us_vix_3d"]
        row["前1日 US VIX"] = vix_ctx["us_vix_1d"]
        row["US VIX"] = vix_ctx["us_vix_0d"]
        row["前5日 台灣VIX"] = vix_ctx["tw_vix_5d"]
        row["前3日 台灣VIX"] = vix_ctx["tw_vix_3d"]
        row["前1日 台灣VIX"] = vix_ctx["tw_vix_1d"]
        row["台灣VIX"] = vix_ctx["tw_vix_0d"]
        row["CNN恐慌"] = vix_ctx["cnn_fg"]

    row["恢復天數"] = rec["recovery_days"] if rec["recovery_days"] is not None else "未恢復"
    row["恢復形態(≤45天=V)"] = rec["recovery_type"]
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="^TWII", help="yfinance ticker，預設台灣加權指數^TWII")
    parser.add_argument("--start", help="開始日期 YYYY-MM-DD（跟--years擇一）")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m-%d"), help="結束日期 YYYY-MM-DD，預設今天")
    parser.add_argument("--years", type=int, help="改用「回溯N年」代替 --start")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--min-drop", type=float, default=-3.0, help="最壞跌幅門檻%%，低於此值才列入（預設-3.0）")
    parser.add_argument("--dedup-days", type=int, default=10, help="未命名事件的去重視窗（交易日約略值，實際用日曆天數比對）")
    parser.add_argument("--events-csv", help="細粒度事件CSV路徑（欄位：事件名稱,開始日期,結束日期）")
    parser.add_argument("--named-events-json", help="具名大事件JSON路徑（優先於events-csv）")
    parser.add_argument("--vix-csv", help="VIX/CNN合併CSV路徑（欄位：Date,US_VIX,Taiwan_VIX,CNN_FG），不給就不輸出VIX情境欄位")
    parser.add_argument("--recovery-lookback-days", type=int, default=120, help="恢復天數計算用的「崩盤前參考價」回溯視窗（日曆天）")
    parser.add_argument("--output", required=True, help="輸出CSV路徑")
    args = parser.parse_args()

    if not args.start and not args.years:
        parser.error("必須指定 --start 或 --years 其中一個")
    start = args.start or (date.today() - timedelta(days=365 * args.years)).strftime("%Y-%m-%d")

    print(f"下載 {args.symbol} {start}~{args.end}...")
    close = load_close_series(args.symbol, start, args.end)
    print(f"  → {len(close)} 筆，{close.index[0].date()} ~ {close.index[-1].date()}")

    named_events = None
    if args.named_events_json:
        named_events = json.loads(Path(args.named_events_json).read_text(encoding="utf-8"))
    label_fn = build_event_labeler(named_events=named_events, events_csv=args.events_csv)

    print(f"偵測崩盤事件（門檻{args.min_drop}%，Top{args.top_n}）...")
    crashes = find_top_crashes(close, min_drop=args.min_drop, top_n=args.top_n,
                                dedup_days=args.dedup_days, event_label_fn=label_fn)
    print(f"  → 找到 {len(crashes)} 筆")

    us_vix = tw_vix = cnn_fg = None
    if args.vix_csv:
        us_vix, tw_vix, cnn_fg = load_vix_csv(args.vix_csv)

    rows = []
    for rank, entry in enumerate(crashes, 1):
        vix_ctx = get_vix_context(entry["date"], us_vix, tw_vix, cnn_fg) if args.vix_csv else None
        rec = calc_recovery(close, entry["date"], lookback_days=args.recovery_lookback_days)
        rows.append(build_row(rank, entry, vix_ctx, rec))

    out_df = pd.DataFrame(rows)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 已寫出 {len(out_df)} 列到 {out_path}")


if __name__ == "__main__":
    main()
