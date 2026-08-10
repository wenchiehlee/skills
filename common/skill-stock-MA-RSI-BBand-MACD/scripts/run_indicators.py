#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_indicators.py — CLI 進入點：算一批股票的 MA/STD/布林通道(BBand)/RSI(14)/MACD，
輸出一個 CSV（每檔一列的最新快照），資料來源是還原股價（Fugle為主，yfinance僅供verify）。

輸出 CSV 欄位（每個 --ma-period 各一組 MA{n}/STD{n}/zscore_MA{n}，外加固定欄位）：
  symbol, close,
  MA20, STD20, zscore_MA20, MA60, STD60, zscore_MA60, MA120, STD120, zscore_MA120,
  MA240, STD240, zscore_MA240,
  BB20_upper, BB20_mid, BB20_lower,
  RSI14,
  MACD_dif, MACD_signal, MACD_hist

用法：

  # 直接指定代號（Fugle symbol，台股不用加交易所後綴）
  python run_indicators.py --symbols 0050 0052 2330 --fugle-env-prefix USER1_ --output out.csv

  # 從 CSV 讀名單（至少要有一欄「代號」或「symbol」；有「yahoo_symbol」欄才能用 --verify）
  python run_indicators.py --list StockID.csv --fugle-env-prefix USER1_ --output out.csv

  # 交叉比對 yfinance，額外印出差異報告（不影響輸出CSV，CSV永遠是Fugle版本）
  python run_indicators.py --symbols 0050 0052 --fugle-env-prefix USER1_ --output out.csv --verify
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_SCRIPTS_DIR))

from price_loader import (
    login_fugle,
    fetch_fugle_adjusted,
    fetch_fugle_market_adjustment_events,
    fetch_yahoo_adjusted,
)
from indicators import calc_all

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import find_dotenv, load_dotenv
    # usecwd=True：找目前工作目錄（消費端repo根目錄）的.env，不是這支腳本自己所在的
    # skills/.../scripts/ 目錄——預設的find_dotenv()是以呼叫端檔案位置回溯搜尋，
    # 對「腳本住在另一個repo（skills登錄庫），從consumer repo執行」這種情境會找錯地方。
    load_dotenv(dotenv_path=find_dotenv(usecwd=True), override=True)
except ImportError:
    pass

MA_PERIODS = (20, 60, 120, 240)
FIELD_ORDER = ["symbol", "close"]
for n in MA_PERIODS:
    FIELD_ORDER += [f"MA{n}", f"STD{n}", f"zscore_MA{n}"]
FIELD_ORDER += ["BB20_upper", "BB20_mid", "BB20_lower", "RSI14",
                "MACD_dif", "MACD_signal", "MACD_hist"]


def load_symbol_list(args) -> list[dict]:
    """回傳 [{"symbol": "2330", "yahoo_symbol": "2330.TW"}, ...]。
    --list CSV 欄位容錯：「代號」或「symbol」/「stock_code」皆可；yahoo對照欄
    容錯：「yahoo_symbol」，沒有這欄時 --verify 會對該代號略過。"""
    if args.symbols:
        return [{"symbol": s.strip().zfill(4) if s.strip().isdigit() else s.strip(),
                  "yahoo_symbol": None} for s in args.symbols]

    df = pd.read_csv(args.list, dtype=str)
    code_col = next((c for c in ["代號", "symbol", "stock_code"] if c in df.columns), None)
    if code_col is None:
        raise SystemExit(f"--list {args.list} 找不到代號欄位（代號/symbol/stock_code）")
    yahoo_col = next((c for c in ["yahoo_symbol"] if c in df.columns), None)

    out = []
    for _, row in df.iterrows():
        code = str(row[code_col]).strip()
        if not code:
            continue
        out.append({
            "symbol": code.zfill(4) if code.isdigit() else code,
            "yahoo_symbol": (str(row[yahoo_col]).strip() if yahoo_col and pd.notna(row.get(yahoo_col)) else None),
        })
    return out


def build_row(symbol: str, close: pd.Series) -> dict:
    if close.empty or len(close) < 20:
        return {"symbol": symbol, "close": None}
    row = calc_all(close, ma_periods=MA_PERIODS, rsi_period=14, macd=(12, 26, 9),
                    bband_period=20, bband_k=2.0)
    row["symbol"] = symbol
    return row


def print_verify_report(fugle_rows: dict, yahoo_rows: dict):
    print("\n=== --verify 交叉比對（Fugle vs yfinance，RSI14 / zscore_MA240）===")
    print(f"{'代號':8s}{'Fugle RSI':>10s}{'Yahoo RSI':>10s}{'  ':2s}{'Fugle z(MA240)':>16s}{'Yahoo z(MA240)':>16s}")
    for symbol, f in fugle_rows.items():
        y = yahoo_rows.get(symbol)
        if not y or f.get("close") is None or y.get("close") is None:
            print(f"{symbol:8s}  （其中一邊沒資料，略過）")
            continue
        f_rsi, y_rsi = f.get("RSI14"), y.get("RSI14")
        f_z, y_z = f.get("zscore_MA240"), y.get("zscore_MA240")
        rsi_diff = abs(f_rsi - y_rsi) if (f_rsi is not None and y_rsi is not None) else None
        flag = " ⚠️差異>3" if rsi_diff is not None and rsi_diff > 3 else ""
        f_rsi_s = f"{f_rsi:.2f}" if f_rsi is not None else "-"
        y_rsi_s = f"{y_rsi:.2f}" if y_rsi is not None else "-"
        f_z_s = f"{f_z:.2f}" if f_z is not None else "-"
        y_z_s = f"{y_z:.2f}" if y_z is not None else "-"
        print(f"{symbol:8s}{f_rsi_s:>10s}{y_rsi_s:>10s}{'  ':2s}{f_z_s:>16s}{y_z_s:>16s}{flag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="+", help="直接指定代號清單（跟--list擇一）")
    parser.add_argument("--list", help="從CSV讀取代號清單（跟--symbols擇一）")
    parser.add_argument("--fugle-env-prefix", default="", help="TaishinSDK登入用的環境變數前綴，例如 USER1_（對應 FUGLE_USER1_PERSONAL_ID 等）")
    parser.add_argument("--years", type=int, default=2, help="還原股價回溯年數（預設2年，足夠算MA240/RSI14/MACD）")
    parser.add_argument("--output", required=True, help="輸出CSV路徑")
    parser.add_argument("--verify", action="store_true", help="額外抓yfinance版本做交叉比對並印出報告（不影響輸出CSV，CSV永遠是Fugle版本）；只對有yahoo_symbol對照的代號生效")
    args = parser.parse_args()

    if not args.symbols and not args.list:
        parser.error("必須指定 --symbols 或 --list 其中一個")

    targets = load_symbol_list(args)
    print(f"共 {len(targets)} 檔代號，回溯 {args.years} 年，來源：Fugle API")

    sdk, acc = login_fugle(args.fugle_env_prefix)
    rc = sdk.marketdata.rest_client

    from datetime import datetime, timedelta
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365 * args.years + 30)
    print(f"抓取還原調整事件（除息+減資/分割），{start_date}~{end_date}...")
    market_events = fetch_fugle_market_adjustment_events(rc, start_date, end_date)

    fugle_rows = {}
    for t in targets:
        symbol = t["symbol"]
        close = fetch_fugle_adjusted(rc, symbol, years=args.years, market_events=market_events)
        row = build_row(symbol, close)
        fugle_rows[symbol] = row
        n_events = len(market_events.get(symbol, []))
        status = f"{len(close)}筆日線，{n_events}筆除權息/分割事件" if not close.empty else "⚠️ 無資料"
        print(f"  {symbol}: {status}")

    out_df = pd.DataFrame([fugle_rows[t["symbol"]] for t in targets])[FIELD_ORDER]
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 已寫出 {len(out_df)} 列到 {out_path}")

    if args.verify:
        verifiable = [t for t in targets if t.get("yahoo_symbol")]
        if not verifiable:
            print("\n⚠️ --verify 需要 --list CSV 裡有 yahoo_symbol 欄位，本次沒有可比對的代號，略過。")
        else:
            print(f"\n--verify：額外抓 yfinance 版本比對 {len(verifiable)} 檔...")
            yahoo_rows = {}
            for t in verifiable:
                close = fetch_yahoo_adjusted(t["yahoo_symbol"], period=f"{args.years}y")
                yahoo_rows[t["symbol"]] = build_row(t["symbol"], close)
            print_verify_report({k: v for k, v in fugle_rows.items() if k in yahoo_rows}, yahoo_rows)


if __name__ == "__main__":
    main()
