#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest.py — 歷史回測：對「單日急跌/跌破均線/RSI超賣/z-score偏離/創新高新低」這一整套
條件分類法，逐一算出每個條件的歷史觸發次數與forward報酬/勝率，可同時對多個窗口
（例如60/180/360日）評估同一組觸發日。

條件分類法（(0)~(13b)編號沿用GoogleSheet.Banks `投資決策分層.md`既有慣例，這份文件
2026年8月透過大量手動回測建立，這支模組是把那套方法論收進skill、變成可重跑工具）：

  (0)      基準（全樣本）
  (1)      單日跌幅 ≤ crash_threshold
  (2)/(2a)/(2b)   (1) 且 <MA_short（組合/剛跌破事件/純狀態）
  (3)/(3a)/(3b)   (1) 且 <MA_mid
  (4)/(4a)/(4b)   (1) 且 <MA_long
  (5)/(5a)/(5b)   (1) 且 RSI<rsi低門檻（組合/剛跌破事件/純狀態）
  (6)/(6a)/(6b)   (1) 且 RSI<rsi高門檻
  (7a)/(7b)       創 high_low_windows[0] 日新高/新低
  (8a)/(8b)       創 high_low_windows[1] 日新高/新低
  (9a)/(9b)       創 newlow_windows[0]/[1] 日新低（解決「箱型下緣過時」問題的短窗口）
  (10a)/(10b)~(13a)/(13b)  z-score(MA_N,STD_N) < z_thresholds[0]/[1]，N依z_periods依序編號10~13

只依賴 pandas，不依賴price_loader/indicators以外的任何本skill模組之外的東西——
close 序列（還原股價）由呼叫端自己準備（用price_loader.fetch_fugle_adjusted或
fetch_yahoo_adjusted都可以），這裡純粹是回測邏輯。
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

import pandas as pd

from indicators import calc_ma, calc_std, calc_rsi


def _stat(fwd: pd.Series, mask: pd.Series, valid: pd.Series, n_years: float) -> dict:
    m = mask.fillna(False) & valid
    n = int(m.sum())
    if n == 0:
        return {"n": 0, "per_year": 0.0, "avg": None, "win": None}
    return {
        "n": n,
        "per_year": round(n / n_years, 2),
        "avg": round(float(fwd[m].mean()), 4),
        "win": round(float((fwd[m] > 0).mean() * 100), 2),
    }


def backtest_conditions(
    close: pd.Series,
    ma_state_periods=(30, 120, 360),
    rsi_period: int = 14,
    rsi_thresholds=(20, 30),
    z_periods=(20, 60, 120, 240),
    z_thresholds=(-1, -2),
    newlow_windows=(60, 90),
    high_low_windows=(120, 360),
    crash_threshold: float = -3.0,
    horizons=(60, 180, 360),
) -> list[dict]:
    """回傳每個條件在每個horizon下的統計，一個條件一個dict：
    {"key": "(3b)", "label": "純<MA120（狀態）", "n":.., "per_year":..,
     "horizons": {60: {"n":,"avg":,"win":}, 180: {...}, 360: {...}}}"""
    daily_ret = close.pct_change() * 100
    rsi = calc_rsi(close, rsi_period)
    n_years = (close.index.max() - close.index.min()).days / 365.25

    ma = {n: calc_ma(close, n) for n in set(ma_state_periods)}
    down = daily_ret <= crash_threshold

    masks: dict[str, tuple[str, pd.Series]] = {}
    masks["(0)"] = ("基準(全樣本)", pd.Series(True, index=close.index))
    masks["(1)"] = (f"單日≤{crash_threshold:g}%", down)

    combo_num = 2
    for i, period in enumerate(ma_state_periods):
        label_period = f"MA{period}"
        m = ma[period]
        cross = (close < m) & (close.shift(1) >= m.shift(1))
        masks[f"({combo_num})"] = (f"單日≤{crash_threshold:g}% 且 <{label_period}", down & (close < m))
        masks[f"({combo_num}a)"] = (f"剛跌破{label_period}（事件）", cross)
        masks[f"({combo_num}b)"] = (f"純<{label_period}（狀態）", close < m)
        combo_num += 1

    rsi_num = combo_num
    for thresh in rsi_thresholds:
        cross = (rsi < thresh) & (rsi.shift(1) >= thresh)
        masks[f"({rsi_num})"] = (f"RSI<{thresh} 且 單日≤{crash_threshold:g}%", down & (rsi < thresh))
        masks[f"({rsi_num}a)"] = (f"剛跌破RSI{thresh}（事件）", cross)
        masks[f"({rsi_num}b)"] = (f"純RSI<{thresh}（狀態）", rsi < thresh)
        rsi_num += 1

    hl_num = rsi_num
    for window in high_low_windows:
        roll_max = close.rolling(window).max()
        roll_min = close.rolling(window).min()
        masks[f"({hl_num}a)"] = (f"創{window}日新高", close >= roll_max)
        masks[f"({hl_num}b)"] = (f"創{window}日新低", close <= roll_min)
        hl_num += 1

    nl_num = hl_num
    for window in newlow_windows:
        roll_min = close.rolling(window).min()
        suffix = "a" if window == newlow_windows[0] else "b"
        masks[f"({nl_num}{suffix})"] = (f"創{window}日新低", close <= roll_min)
    nl_num += 1

    z_num = nl_num
    for period in z_periods:
        m = ma[period] if period in ma else calc_ma(close, period)
        std = calc_std(close, period)
        z = (close - m) / std
        for thresh, suffix in zip(z_thresholds, "ab"):
            masks[f"({z_num}{suffix})"] = (f"z(MA{period},STD{period})<{thresh}σ", z < thresh)
        z_num += 1

    results = []
    for key, (label, mask) in masks.items():
        row = {"key": key, "label": label, "horizons": {}}
        n_total = None
        for h in horizons:
            fwd = (close.shift(-h) / close - 1) * 100
            valid = fwd.notna()
            s = _stat(fwd, mask, valid, n_years)
            row["horizons"][h] = s
            if n_total is None:
                n_total = s["n"]
                row["n"] = s["n"]
                row["per_year"] = s["per_year"]
        results.append(row)
    return results
