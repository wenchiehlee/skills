#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_indicators.py — CLI 進入點：算一批股票的 MA/STD/布林通道(BBand)/RSI(14)/MACD，
可選 EPS 檔計算 common market PE band，輸出一個 CSV（每檔一列的最新快照）。

**資料來源可選**（`--source`），因為不是每個consumer repo都有Fugle/TaishinSDK憑證：

  - `--source fugle`（預設）：Fugle API為主要來源（還原股價，見price_loader.py），
    需要 `--fugle-env-prefix` 對應的TaishinSDK憑證。可以加 `--verify` 額外抓yfinance
    版本做交叉比對（只印報告，不影響輸出CSV），適合像GoogleSheet.Banks這種本來就有
    Fugle憑證、想要雙來源互相驗證的repo。
  - `--source yahoo`：yfinance auto_adjust=True 為主要來源，**不需要任何Fugle憑證**，
    適合沒有台新/複委託帳號的repo。這個模式下 `--symbols`/`--list` 裡的代號要直接是
    yfinance ticker格式（例如`0050.TW`、`2330.TW`），不會自動補後綴；`--list` CSV如果
    有 `yahoo_symbol` 欄，會優先用那一欄。`--verify` 在這個模式下沒有意義（沒有第二個
    來源可以比對），會被忽略並印警告。已知限制：yfinance對部分台股ETF分割事件還原
    不完整（見SKILL.md），選這個模式前要清楚這個風險。

輸出 CSV 欄位（每個 --ma-period 各一組 MA{n}/STD{n}/zscore_MA{n}，外加固定欄位）：
  symbol, close,
  MA20, STD20, zscore_MA20, MA60, STD60, zscore_MA60, MA120, STD120, zscore_MA120,
  MA240, STD240, zscore_MA240,
  BB20_upper, BB20_mid, BB20_lower,
  RSI14,
  MACD_dif, MACD_signal, MACD_hist

若提供 `--pe-eps-file`，額外輸出 common market PE band 欄位。單一 EPS scope
維持舊欄位相容並加上 scope metadata；多 EPS scope 則輸出各 scope 前綴欄位。
支援三種 EPS scope：
  trailing_eps：已實現最近四季 EPS（TTM EPS）
  forward_eps：單一模型/單一 publisher/內部模型 forward EPS
  forward_consensus_eps：可比較來源聚合後的 forward consensus EPS

用法：

  # Fugle為主（預設），直接指定代號（Fugle symbol，台股不用加交易所後綴）
  python run_indicators.py --symbols 0050 0052 2330 --fugle-env-prefix USER1_ --output out.csv

  # 從 CSV 讀名單（至少要有一欄「代號」或「symbol」；有「yahoo_symbol」欄才能用 --verify）
  python run_indicators.py --list StockID.csv --fugle-env-prefix USER1_ --output out.csv

  # 交叉比對 yfinance，額外印出差異報告（不影響輸出CSV，CSV永遠是主要來源版本）
  python run_indicators.py --symbols 0050 0052 --fugle-env-prefix USER1_ --output out.csv --verify

  # 只用yfinance（不需要Fugle憑證），代號要直接是yfinance ticker
  python run_indicators.py --source yahoo --symbols 0050.TW 2330.TW --output out.csv
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

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
from indicators import calc_all, calc_pe_band

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
PE_SCOPE_CHOICES = ("trailing_eps", "forward_eps", "forward_consensus_eps")
PE_BAND_VALUE_FIELDS = [
    "PE_eps", "PE_current", "PE_mean", "PE_std",
    "PE_minus_2std", "PE_minus_1std", "PE_plus_1std", "PE_plus_2std",
    "PEBand_price_minus_2std", "PEBand_price_minus_1std", "PEBand_price_mean",
    "PEBand_price_plus_1std", "PEBand_price_plus_2std",
]
PE_FIELD_ORDER = ["PE_eps_scope", "PE_eps_horizon", "PE_eps_source"] + PE_BAND_VALUE_FIELDS


def normalize_pe_scope(raw: str) -> str:
    value = raw.strip().lower().replace("-", "_")
    aliases = {
        "ttm": "trailing_eps",
        "ttm_eps": "trailing_eps",
        "trailing": "trailing_eps",
        "forward": "forward_eps",
        "fwd": "forward_eps",
        "fwd_eps": "forward_eps",
        "consensus": "forward_consensus_eps",
        "consensus_eps": "forward_consensus_eps",
        "forward_consensus": "forward_consensus_eps",
        "fwd_consensus": "forward_consensus_eps",
    }
    value = aliases.get(value, value)
    if value not in PE_SCOPE_CHOICES:
        raise SystemExit(f"不支援的 PE EPS scope：{raw}（允許：{', '.join(PE_SCOPE_CHOICES)}）")
    return value


def parse_pe_eps_columns(spec: str | None, eps_column: str, eps_scope: str) -> list[tuple[str, str]]:
    """回傳 [(scope, column), ...]。

    --pe-eps-columns 支援 `scope=column` 逗號清單；未提供時使用單一
    --pe-eps-column + --pe-eps-scope，維持舊 CLI 相容。
    """
    if not spec:
        return [(normalize_pe_scope(eps_scope), eps_column)]
    mappings = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            scope, column = item.split("=", 1)
        else:
            scope, column = item, item
        mappings.append((normalize_pe_scope(scope), column.strip()))
    if not mappings:
        raise SystemExit("--pe-eps-columns 不可為空")
    return mappings


def load_pe_eps_inputs(path: str | None, eps_mappings: list[tuple[str, str]], args) -> dict:
    """讀取 PEBand EPS 輸入。

    CSV 至少需要 symbol/stock_code/代號 其中一欄，以及 mappings 指定的 EPS 欄。
    標準 PE band 需要 date/asof_date/forecast_asof_date 欄，建立 dated EPS Series
    並在交易日向前填補。沒有日期欄時預設報錯；只有明確加
    --pe-allow-static-eps-band 時，才允許用最後一筆 EPS 作為非標準 fallback。
    """
    if not path:
        return {}
    df = pd.read_csv(path, dtype=str)
    code_col = next((c for c in ["代號", "symbol", "stock_code"] if c in df.columns), None)
    if code_col is None:
        raise SystemExit(f"--pe-eps-file {path} 找不到代號欄位（代號/symbol/stock_code）")
    missing = [column for _, column in eps_mappings if column not in df.columns]
    if missing:
        raise SystemExit(f"--pe-eps-file {path} 找不到 EPS 欄位：{', '.join(missing)}")

    date_col = next((c for c in ["date", "asof_date", "forecast_asof_date"] if c in df.columns), None)
    if date_col is None and not getattr(args, "pe_allow_static_eps_band", False):
        raise SystemExit(
            "標準 PE band 需要 dated EPS series：--pe-eps-file 必須包含 "
            "date/asof_date/forecast_asof_date。若要用最新 EPS 除整段價格作為非標準 fallback，"
            "請顯式加 --pe-allow-static-eps-band。"
        )
    out = {}
    for _, column in eps_mappings:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for raw_symbol, g in df.groupby(code_col, dropna=True):
        symbol = str(raw_symbol).strip()
        if not symbol:
            continue
        symbol = symbol.zfill(4) if symbol.isdigit() else symbol
        scoped = {}
        for scope, column in eps_mappings:
            valid = g.dropna(subset=[column]).copy()
            if valid.empty:
                continue
            if date_col:
                valid[date_col] = pd.to_datetime(valid[date_col], errors="coerce")
                valid = valid.dropna(subset=[date_col]).sort_values(date_col)
                if valid.empty:
                    continue
                eps_value = pd.Series(valid[column].astype(float).values, index=valid[date_col])
            else:
                eps_value = float(valid[column].iloc[-1])
            scoped[scope] = {"eps": eps_value, "column": column}
        if scoped:
            out[symbol] = scoped
    return out


def build_pe_field_order(scopes: list[str], single_scope_mode: bool) -> list[str]:
    if single_scope_mode:
        return PE_FIELD_ORDER
    fields = []
    for scope in scopes:
        fields.extend([f"{scope}_{name}" for name in PE_FIELD_ORDER])
    return fields


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


def lookup_pe_input(pe_inputs: dict, symbol: str):
    """PE EPS lookup with tolerance for Yahoo tickers like 2330.TW vs local code 2330."""
    if symbol in pe_inputs:
        return pe_inputs[symbol]
    base = symbol.split(".")[0]
    candidates = [base, base.zfill(4) if base.isdigit() else base]
    for key in candidates:
        if key in pe_inputs:
            return pe_inputs[key]
    return None


def add_pe_band_fields(row: dict, close: pd.Series, scoped_pe_inputs, args, single_scope_mode: bool) -> None:
    if not scoped_pe_inputs:
        return
    for scope, payload in scoped_pe_inputs.items():
        bands = calc_pe_band(close, payload["eps"], args.pe_period)
        if not bands:
            continue
        bands = {
            "PE_eps_scope": scope,
            "PE_eps_horizon": args.pe_eps_horizon,
            "PE_eps_source": args.pe_eps_source,
            **bands,
        }
        if single_scope_mode:
            row.update(bands)
        else:
            row.update({f"{scope}_{key}": value for key, value in bands.items()})


def build_row(symbol: str, close: pd.Series, scoped_pe_inputs=None, args=None, single_scope_mode: bool = True) -> dict:
    if close.empty or len(close) < 20:
        return {"symbol": symbol, "close": None}
    row = calc_all(close, ma_periods=MA_PERIODS, rsi_period=14, macd=(12, 26, 9),
                    bband_period=20, bband_k=2.0)
    if args is not None:
        add_pe_band_fields(row, close, scoped_pe_inputs, args, single_scope_mode)
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


def run_fugle_source(args, targets, pe_inputs, single_scope_mode):
    sdk, acc = login_fugle(args.fugle_env_prefix)
    rc = sdk.marketdata.rest_client

    from datetime import datetime, timedelta
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365 * args.years + 30)
    print(f"抓取還原調整事件（除息+減資/分割），{start_date}~{end_date}...")
    market_events = fetch_fugle_market_adjustment_events(rc, start_date, end_date)

    rows = {}
    for t in targets:
        symbol = t["symbol"]
        close = fetch_fugle_adjusted(rc, symbol, years=args.years, market_events=market_events)
        rows[symbol] = build_row(symbol, close, lookup_pe_input(pe_inputs, symbol), args, single_scope_mode)
        n_events = len(market_events.get(symbol, []))
        status = f"{len(close)}筆日線，{n_events}筆除權息/分割事件" if not close.empty else "⚠️ 無資料"
        print(f"  {symbol}: {status}")
    return rows


def run_yahoo_source(args, targets, pe_inputs, single_scope_mode):
    """代號直接當yfinance ticker用（--list有yahoo_symbol欄的話優先用那一欄）。"""
    rows = {}
    for t in targets:
        symbol = t["symbol"]
        yahoo_ticker = t.get("yahoo_symbol") or symbol
        close = fetch_yahoo_adjusted(yahoo_ticker, period=f"{args.years}y")
        rows[symbol] = build_row(symbol, close, lookup_pe_input(pe_inputs, symbol), args, single_scope_mode)
        status = f"{len(close)}筆日線" if not close.empty else "⚠️ 無資料"
        print(f"  {symbol}（{yahoo_ticker}）: {status}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="+", help="直接指定代號清單（跟--list擇一）")
    parser.add_argument("--list", help="從CSV讀取代號清單（跟--symbols擇一）")
    parser.add_argument("--source", choices=["fugle", "yahoo"], default="fugle",
                         help="主要資料來源（預設fugle）。fugle需要--fugle-env-prefix對應的TaishinSDK憑證；"
                              "yahoo不需要任何憑證，但代號要直接是yfinance ticker格式（例如0050.TW）")
    parser.add_argument("--fugle-env-prefix", default="", help="TaishinSDK登入用的環境變數前綴，例如 USER1_（對應 FUGLE_USER1_PERSONAL_ID 等），只有 --source fugle 才需要")
    parser.add_argument("--years", type=int, default=2, help="還原股價回溯年數（預設2年，足夠算MA240/RSI14/MACD）")
    parser.add_argument("--output", required=True, help="輸出CSV路徑")
    parser.add_argument("--verify", action="store_true", help="只在--source fugle時有效：額外抓yfinance版本做交叉比對並印出報告（不影響輸出CSV）；只對有yahoo_symbol對照的代號生效")
    parser.add_argument("--pe-eps-file", help="可選：EPS CSV，用於計算 common market PE band。欄位需含代號/symbol/stock_code與EPS欄；可選date/asof_date/forecast_asof_date")
    parser.add_argument("--pe-eps-column", default="eps", help="單一 EPS scope 模式：--pe-eps-file 內的EPS欄名（預設eps）")
    parser.add_argument("--pe-eps-scope", default="forward_consensus_eps", choices=PE_SCOPE_CHOICES, help="單一 EPS scope 模式：EPS 定義（預設forward_consensus_eps）")
    parser.add_argument("--pe-eps-columns", help="多 EPS scope 模式：逗號清單，例如 trailing_eps=eps_ttm,forward_eps=eps_2027e,forward_consensus_eps=consensus_eps_2027e")
    parser.add_argument("--pe-eps-horizon", default="", help="可選：EPS horizon/period metadata，例如 TTM、FY2027E、NTM")
    parser.add_argument("--pe-eps-source", default="", help="可選：EPS source metadata，例如 company_report、internal_model、yahoo_consensus")
    parser.add_argument("--pe-allow-static-eps-band", action="store_true", help="非標準fallback：允許沒有date欄的EPS檔，用最後一筆EPS除整段價格；標準PEBand不建議使用")
    parser.add_argument("--pe-period", type=int, default=1200, help="PE band 樣本視窗交易日數（預設1200，約5年；60=短期季度regime，240=1Y，720=3Y）")
    args = parser.parse_args()

    if not args.symbols and not args.list:
        parser.error("必須指定 --symbols 或 --list 其中一個")
    if args.verify and args.source != "fugle":
        print("⚠️ --verify 只在 --source fugle 時有效（需要跟另一個來源比對），本次忽略。")
        args.verify = False

    targets = load_symbol_list(args)
    eps_mappings = parse_pe_eps_columns(args.pe_eps_columns, args.pe_eps_column, args.pe_eps_scope)
    single_scope_mode = args.pe_eps_columns is None
    pe_inputs = load_pe_eps_inputs(args.pe_eps_file, eps_mappings, args)
    print(f"共 {len(targets)} 檔代號，回溯 {args.years} 年，來源：{'Fugle API' if args.source == 'fugle' else 'yfinance'}")
    if args.pe_eps_file:
        mapping_text = ", ".join(f"{scope}={column}" for scope, column in eps_mappings)
        print(f"PEBand：讀入 {len(pe_inputs)} 檔 EPS，{mapping_text}，視窗 {args.pe_period} 交易日")

    if args.source == "fugle":
        primary_rows = run_fugle_source(args, targets, pe_inputs, single_scope_mode)
    else:
        primary_rows = run_yahoo_source(args, targets, pe_inputs, single_scope_mode)

    pe_scopes = [scope for scope, _ in eps_mappings]
    field_order = FIELD_ORDER + (build_pe_field_order(pe_scopes, single_scope_mode) if args.pe_eps_file else [])
    out_df = pd.DataFrame([primary_rows[t["symbol"]] for t in targets]).reindex(columns=field_order)
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
                yahoo_rows[t["symbol"]] = build_row(t["symbol"], close, lookup_pe_input(pe_inputs, t["symbol"]), args, single_scope_mode)
            print_verify_report({k: v for k, v in primary_rows.items() if k in yahoo_rows}, yahoo_rows)


if __name__ == "__main__":
    main()
