#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
indicators.py — 純技術指標計算函式（無 I/O，輸入輸出都是 pandas Series）。

所有函式吃「還原股價」的日收盤價序列（pd.Series，index 為交易日，由小到大排序），
不吃原始未還原價——除權息缺口沒處理過會讓 MA/STD/RSI/MACD 全部失真，這是本技能存在
的理由，資料還原邏輯在 price_loader.py，這裡只做純數學。
"""
import pandas as pd


def calc_ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def calc_std(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).std()


def calc_bbands(close: pd.Series, period: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林通道：中軌=MA_N，上/下軌=中軌±k倍STD_N（k預設2，業界慣例）。"""
    ma = calc_ma(close, period)
    std = calc_std(close, period)
    return pd.DataFrame({
        "mid": ma,
        "upper": ma + k * std,
        "lower": ma - k * std,
        "std": std,
    })


def calc_zscore(close: pd.Series, period: int) -> pd.Series:
    """z = (現價-MA_N)/STD_N，等同「現價在布林通道裡的標準差座標」——
    z<-2 代表跌破布林下軌以下更多（<-2σ），z>+2 代表突破上軌以上更多（>+2σ）。"""
    ma = calc_ma(close, period)
    std = calc_std(close, period)
    return (close - ma) / std


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder 1978 原始定義，用 EWM(alpha=1/period, adjust=False) 逼近遞迴平滑，
    跟券商/App顯示的RSI(14)口徑一致（不是簡單移動平均版本）。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """標準 MACD：DIF = EMA_fast - EMA_slow，MACD訊號線 = DIF 的 EMA_signal，
    柱狀圖(histogram) = DIF - 訊號線。EMA 用 adjust=False（遞迴版本，業界標準）。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    macd_signal = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - macd_signal
    return pd.DataFrame({"dif": dif, "signal": macd_signal, "hist": hist})


def calc_all(close: pd.Series, ma_periods=(20, 60, 120, 240), rsi_period=14,
             macd=(12, 26, 9), bband_period=20, bband_k=2.0) -> dict:
    """一次算好全部指標的最新一筆數值（latest snapshot），適合寫進報表/試算表的單列。
    回傳 dict，NaN（暖機不足）一律轉成 None。"""
    def last(s):
        v = s.iloc[-1] if len(s) else float("nan")
        return None if pd.isna(v) else float(v)

    out = {}
    for n in ma_periods:
        ma = calc_ma(close, n)
        std = calc_std(close, n)
        z = (close - ma) / std
        out[f"MA{n}"] = last(ma)
        out[f"STD{n}"] = last(std)
        out[f"zscore_MA{n}"] = last(z)

    bb = calc_bbands(close, bband_period, bband_k)
    out[f"BB{bband_period}_upper"] = last(bb["upper"])
    out[f"BB{bband_period}_mid"] = last(bb["mid"])
    out[f"BB{bband_period}_lower"] = last(bb["lower"])

    out[f"RSI{rsi_period}"] = last(calc_rsi(close, rsi_period))

    fast, slow, signal = macd
    m = calc_macd(close, fast, slow, signal)
    out["MACD_dif"] = last(m["dif"])
    out["MACD_signal"] = last(m["signal"])
    out["MACD_hist"] = last(m["hist"])

    out["close"] = last(close)
    return out
