#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
price_loader.py — 雙來源還原股價載入器（Fugle API 主要來源 + yfinance 交叉驗證）。

為什麼要兩個來源：
  - Fugle `historical.candles` 回傳的是「未還原」原始 OHLC，本模組自己用
    `corporate_actions.dividends`（除息）+ `corporate_actions.capital_changes`
    （減資/分割）兩個「全市場」端點抓事件，再依 `referencePrice/previousClose`
    比例對「事件交易日之前」的收盤價做累積回溯調整——這是本技能對「還原股價」的
    權威定義，寫進報表/試算表的一律是這個版本。
  - yfinance `auto_adjust=True` 理論上也會自動還原，但實測發現對台股某些除權息事件
    （尤其 ETF 分割）沒有正確登記（yf.Ticker.splits 缺漏），導致還原序列在缺口附近
    整段錯誤（曾在 0052 的 2025-11 分割上發現：yfinance MA240 誤差達 2 倍以上）。
    保留 yfinance 版本只是拿來做 `--verify` 交叉比對，不是預設輸出來源。

Fugle 端點限制（實測記錄，不是官方文件）：
  - `historical.candles(symbol=, from=, to=)`：單次查詢範圍上限 1 年，Python kwarg
    不能用 `from_=`（那個 key 會被 API 忽略，安靜地退回一個很短的預設區間，不會報錯，
    很容易誤判成「資料真的只有這麼少」）——必須用 `**{"from": ..., "to": ...}` 展開。
  - `corporate_actions.dividends` / `capital_changes`：兩者都是**全市場**端點，
    不接受 `symbol` 篩選參數（dividends 傳了會被忽略、capital_changes 傳了直接 400），
    要自己在本地依 symbol 過濾回傳的 `data` 陣列。

需要 `taishin_sdk`（`pip install taishin_sdk`，內部依賴 `fugle-marketdata`）與有效的
台新複委託/證券帳號憑證才能使用 Fugle 來源；yfinance 來源不需要任何憑證。
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

import base64
import os
import tempfile
import time
from datetime import date, datetime, timedelta

import pandas as pd


# ── Fugle 登入 ────────────────────────────────────────────────────────────────

def login_fugle(env_prefix: str = ""):
    """讀環境變數 FUGLE_{env_prefix}PERSONAL_ID / PASSWORD / CERT_PASS /
    CERT_B64（或 CERT_PATH）登入 TaishinSDK，回傳 (sdk, account)。
    CERT_B64 是憑證檔的 base64（CI/CD 常用，寫成暫存檔後登入）；本機開發可以改用
    CERT_PATH 直接指向 .p12 憑證路徑。"""
    from taishin_sdk import TaishinSDK

    def _env(suffix):
        return os.environ.get(f"FUGLE_{env_prefix}{suffix}", "").strip()

    personal_id = _env("PERSONAL_ID").upper()
    password = _env("PASSWORD")
    cert_pass = _env("CERT_PASS")
    if not (personal_id and password and cert_pass):
        raise EnvironmentError(
            f"缺少環境變數 FUGLE_{env_prefix}PERSONAL_ID / PASSWORD / CERT_PASS"
        )

    cert_b64 = _env("CERT_B64")
    if cert_b64:
        tmp = tempfile.NamedTemporaryFile(suffix=".p12", delete=False)
        tmp.write(base64.b64decode(cert_b64))
        tmp.flush()
        tmp.close()
        cert_path = tmp.name
    else:
        cert_path = _env("CERT_PATH")
        if not cert_path:
            raise EnvironmentError(f"缺少 FUGLE_{env_prefix}CERT_B64 或 FUGLE_{env_prefix}CERT_PATH")

    sdk = TaishinSDK()
    time.sleep(1)
    accounts = sdk.login(personal_id, password, cert_path, cert_pass)
    acc = accounts[0]
    try:
        sdk.register_api_auth(acc)
    except Exception:
        pass
    sdk.init_realtime(acc)  # 沒呼叫這行 sdk.marketdata 不會被初始化
    return sdk, acc


# ── Fugle 還原股價 ────────────────────────────────────────────────────────────

def fetch_fugle_candles(rest_client, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    """單次呼叫上限1年，超過1年自動分段抓再合併。回傳欄位：date(Timestamp), open/high/low/close/volume（未還原）。"""
    rows = []
    cur_end = end_date
    while cur_end > start_date:
        cur_start = max(start_date, cur_end - timedelta(days=364))
        params = {
            "symbol": symbol,
            "from": cur_start.strftime("%Y-%m-%d"),
            "to": cur_end.strftime("%Y-%m-%d"),
        }
        res = rest_client.stock.historical.candles(**params)
        rows.extend(res.get("data", []))
        cur_end = cur_start - timedelta(days=1)
    df = pd.DataFrame(rows).drop_duplicates(subset="date")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def fetch_fugle_market_adjustment_events(rest_client, start_date: date, end_date: date) -> dict:
    """抓「整個市場」的除息(dividends)跟減資/分割(capital_changes)事件，回傳
    {symbol: [(ex_date, factor), ...]}，factor = referencePrice/previousClose
    （<1 代表當天價格被除權息壓低）。

    這兩個端點單次查詢範圍上限3年（比candles的1年限制更寬，但長期回測——例如
    投資決策分層.md用的2016年至今近10年窗口——還是會超過，所以這裡自動分段抓
    （用略小於3年的區塊避免邊界誤差），行為對呼叫端透明，不用自己處理分段。"""
    events: dict[str, list] = {}
    max_span_days = 3 * 365 - 5  # 略小於3年，避免邊界剛好卡在限制上

    cur_start = start_date
    while cur_start < end_date:
        cur_end = min(end_date, cur_start + timedelta(days=max_span_days))

        div = rest_client.stock.corporate_actions.dividends(
            start_date=cur_start.strftime("%Y-%m-%d"),
            end_date=cur_end.strftime("%Y-%m-%d"),
        )
        for d in div.get("data", []):
            prev, ref = d.get("previousClose"), d.get("referencePrice")
            if not prev or not ref:
                continue
            events.setdefault(d["symbol"], []).append((pd.Timestamp(d["date"]), ref / prev))

        cc = rest_client.stock.corporate_actions.capital_changes(
            start_date=cur_start.strftime("%Y-%m-%d"),
            end_date=cur_end.strftime("%Y-%m-%d"),
        )
        for d in cc.get("data", []):
            raw = d.get("raw", {})
            prev, ref = raw.get("previousClose"), raw.get("referencePrice")
            if not prev or not ref:
                continue
            events.setdefault(d["symbol"], []).append((pd.Timestamp(d["resumeDate"]), ref / prev))

        cur_start = cur_end + timedelta(days=1)

    return events


def adjust_close(dates: pd.Series, closes: pd.Series, events_for_symbol: list) -> pd.Series:
    """回溯調整：事件交易日之前的收盤價，全部乘上該事件比例（多筆事件依時間先後累積相乘）。"""
    adj = closes.astype(float).copy()
    for ex_date, factor in sorted(events_for_symbol, key=lambda e: e[0]):
        mask = dates < ex_date
        adj = adj.where(~mask, adj * factor)
    return adj


def fetch_fugle_adjusted(rest_client, symbol: str, years: int = 2,
                          market_events: dict | None = None,
                          start_date: date | None = None, end_date: date | None = None) -> pd.Series:
    """回傳單一代號的還原收盤價序列（pd.Series，index=交易日 Timestamp，由舊到新）。
    market_events 可選——批次處理多檔時，外面先呼叫一次
    fetch_fugle_market_adjustment_events() 傳進來，避免每檔都重打一次全市場端點。
    預設（不給start_date/end_date）是「回溯years年到今天」，用於算當下指標快照；
    長期歷史回測（例如run_backtest.py）要明確給start_date/end_date，不受years限制。"""
    if end_date is None:
        end_date = datetime.now().date()
    if start_date is None:
        start_date = end_date - timedelta(days=365 * years + 30)

    df = fetch_fugle_candles(rest_client, symbol, start_date, end_date)
    if df.empty:
        return pd.Series(dtype=float)

    if market_events is None:
        market_events = fetch_fugle_market_adjustment_events(rest_client, start_date, end_date)

    adj = adjust_close(df["date"], df["close"], market_events.get(symbol, []))
    adj.index = df["date"]
    return adj.sort_index()


# ── yfinance 還原股價（cross-check 用） ───────────────────────────────────────

def fetch_yahoo_adjusted(yahoo_symbol: str, period: str = "2y") -> pd.Series:
    """yfinance auto_adjust=True 版本，只用於 --verify 交叉比對，不是預設寫入來源
    （已知對部分台股ETF分割事件還原不完整，見本檔案頂端說明）。"""
    import yfinance as yf

    hist = yf.download(yahoo_symbol, period=period, auto_adjust=True, progress=False)
    close = hist["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close
