#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
indicators.py — 純技術指標計算函式（無 I/O，輸入輸出都是 pandas Series）。

所有函式吃「還原股價」的日收盤價序列（pd.Series，index 為交易日，由小到大排序），
不吃原始未還原價——除權息缺口沒處理過會讓 MA/STD/RSI/MACD 全部失真，這是本技能存在
的理由，資料還原邏輯在 price_loader.py，這裡只做純數學。
"""
from __future__ import annotations

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


def calc_rsi_state(close: pd.Series, period: int = 14) -> dict:
    """回傳 Wilder RSI 遞迴平滑在「最後一筆收盤價當下」的內部狀態：
    {last_close, avg_gain, avg_loss}。

    用途：RSI是遞迴定義（今天的平滑值 = 昨天的平滑值*(n-1)/n + 今天漲跌*1/n），
    只給「現價」這一個數字沒辦法重算，但只要知道「上一個收盤價」跟「上一個收盤價當下
    的avg_gain/avg_loss」，往後一天的RSI就能用一條試算表公式即時算出來（不用等腳本重跑）：

      gain_today  = MAX(現價-上一收盤價, 0)
      loss_today  = MAX(上一收盤價-現價, 0)
      avg_gain_today = avg_gain * (period-1)/period + gain_today/period
      avg_loss_today = avg_loss * (period-1)/period + loss_today/period
      RSI = 100 - 100/(1 + avg_gain_today/avg_loss_today)

    這三個值只需要腳本每天算一次（用「到昨天收盤為止」的序列），試算表公式再用當天
    即時報價（現價欄）跟這三個值算出「即時RSI」，達到RSI隨報價變動即時更新，不必每次
    報價跳動都重新登入API重算整條序列。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    def last(s):
        v = s.iloc[-1] if len(s) else float("nan")
        return None if pd.isna(v) else float(v)

    return {
        "last_close": last(close),
        "avg_gain": last(avg_gain),
        "avg_loss": last(avg_loss),
    }


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """標準 MACD：DIF = EMA_fast - EMA_slow，MACD訊號線 = DIF 的 EMA_signal，
    柱狀圖(histogram) = DIF - 訊號線。EMA 用 adjust=False（遞迴版本，業界標準）。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    macd_signal = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - macd_signal
    return pd.DataFrame({"dif": dif, "signal": macd_signal, "hist": hist})


def calc_pe_band_series(
    close: pd.Series, eps: float | pd.Series, period: int = 240, min_periods: int | None = None,
) -> pd.DataFrame:
    """`calc_pe_band()` 的向量化版本：回傳整段每日 PE band 序列，不是只回最新一筆快照。

    給需要畫多年時間序列圖（而非單日技術指標寬表）的呼叫端使用，例如
    `skill-stock-dynamic-valuation-box`。口徑跟 `calc_pe_band()` 完全一致
    （PE_t = close_t / EPS_t，滾動窗 μ/σ、μ±1σ/±2σ 及對應價格帶），差別只在
    這裡對每一天都算一次，而不是只算最後一天。

    本函式對 close 的還原/未還原狀態沒有立場——呼叫端決定要傳哪一種收盤價序列
    （例如 valuation-box 刻意傳未還原收盤價，理由見它自己的 SKILL.md）；這裡只
    負責 PE_t = close_t / EPS_t 之後的純數學，不重新抓取或調整價格本身。

    回傳 DataFrame（index 與 close 對齊），欄位：eps, pe, pe_mean, pe_std,
    price_m2, price_m1, price_mean, price_p1, price_p2。資料不足時回傳空 DataFrame。
    """
    close = close.dropna().astype(float)
    if close.empty or period <= 1:
        return pd.DataFrame()

    if isinstance(eps, pd.Series):
        eps_series = eps.dropna().astype(float).sort_index()
        if eps_series.empty:
            return pd.DataFrame()
        aligned_eps = (
            eps_series.reindex(eps_series.index.union(close.index))
            .sort_index()
            .ffill()
            .reindex(close.index)
        )
    else:
        try:
            latest_eps = float(eps)
        except (TypeError, ValueError):
            return pd.DataFrame()
        if latest_eps <= 0:
            return pd.DataFrame()
        aligned_eps = pd.Series(latest_eps, index=close.index)

    pe = close / aligned_eps
    mp = min_periods if min_periods is not None else min(period, 120)
    pe_mean = pe.rolling(period, min_periods=mp).mean()
    pe_std = pe.rolling(period, min_periods=mp).std(ddof=1)

    out = pd.DataFrame({"eps": aligned_eps, "pe": pe, "pe_mean": pe_mean, "pe_std": pe_std})
    for sigma, name in ((-2, "m2"), (-1, "m1"), (0, "mean"), (1, "p1"), (2, "p2")):
        out[f"price_{name}"] = (pe_mean + sigma * pe_std) * aligned_eps
    return out


def calc_pe_band(close: pd.Series, eps: float | pd.Series, period: int = 240) -> dict:
    """用 common market PE band 口徑計算估值帶。

    PE 分布 = daily close / EPS。EPS 可為固定數字（例如最新 forward EPS consensus），
    也可為日期索引 Series（例如 daily consensus EPS），會用交易日向前填補後對齊價格。
    回傳最新 PE、樣本平均 μ、樣本標準差 σ、μ±1σ/±2σ 的 PE 倍數與用同一 EPS 換算的價格帶。
    """
    close = close.dropna().astype(float)
    if close.empty or period <= 1:
        return {}

    if isinstance(eps, pd.Series):
        eps_series = eps.dropna().astype(float).sort_index()
        if eps_series.empty:
            return {}
        aligned_eps = (
            eps_series.reindex(eps_series.index.union(close.index))
            .sort_index()
            .ffill()
            .reindex(close.index)
        )
        pe = (close / aligned_eps).dropna()
        latest_eps = aligned_eps.reindex(pe.index).iloc[-1] if not pe.empty else None
    else:
        try:
            latest_eps = float(eps)
        except (TypeError, ValueError):
            return {}
        if latest_eps <= 0:
            return {}
        pe = close / latest_eps

    window = pe.tail(period).dropna()
    if len(window) < 2 or latest_eps is None or pd.isna(latest_eps) or latest_eps <= 0:
        return {}

    mean = float(window.mean())
    std = float(window.std(ddof=1))
    latest_pe = float(pe.iloc[-1])
    bands = {
        "PE_eps": float(latest_eps),
        "PE_current": latest_pe,
        "PE_mean": mean,
        "PE_std": std,
        "PE_minus_2std": mean - 2 * std,
        "PE_minus_1std": mean - std,
        "PE_plus_1std": mean + std,
        "PE_plus_2std": mean + 2 * std,
    }
    bands["PEBand_price_minus_2std"] = bands["PE_minus_2std"] * float(latest_eps)
    bands["PEBand_price_minus_1std"] = bands["PE_minus_1std"] * float(latest_eps)
    bands["PEBand_price_mean"] = bands["PE_mean"] * float(latest_eps)
    bands["PEBand_price_plus_1std"] = bands["PE_plus_1std"] * float(latest_eps)
    bands["PEBand_price_plus_2std"] = bands["PE_plus_2std"] * float(latest_eps)
    return bands


def classify_pe_band(pe_current: float | None, mean: float | None, std: float | None) -> int | None:
    """把「現在PE相對μ/σ落在哪一段」轉成離散band標籤（0~5，共6段）：

      0：PE < μ-2σ（極便宜，跌出正常估值帶下緣以下）
      1：μ-2σ <= PE < μ-1σ
      2：μ-1σ <= PE < μ
      3：μ   <= PE < μ+1σ
      4：μ+1σ <= PE < μ+2σ
      5：PE >= μ+2σ（極貴，漲出正常估值帶上緣以上）

    刻意保留0/5這兩個「超出±2σ」的極端標籤而不是夾到1/4——2σ以外在常態假設下只有約
    5%機率，直接夾進最近的一端會把「這次真的很極端」跟「剛好卡在帶緣」混在一起，
    對機械化的估值判斷來說資訊量差很多（[[project-strategy-framework]]機率思維的
    校準桶概念在這裡也適用：極端桶不該被併回鄰近桶）。

    std<=0（樣本太少或PE序列退化成常數）或任一輸入是None/NaN時回傳None，呼叫端
    自行決定顯示成"-"還是其他預設值，不在這裡幫呼叫端做決定。"""
    if pe_current is None or mean is None or std is None:
        return None
    if any(pd.isna(v) for v in (pe_current, mean, std)) or std <= 0:
        return None
    z = (pe_current - mean) / std
    if z < -2:
        return 0
    if z < -1:
        return 1
    if z < 0:
        return 2
    if z < 1:
        return 3
    if z < 2:
        return 4
    return 5


def calc_all(close: pd.Series, ma_periods=(20, 60, 120, 240), rsi_period=14,
             macd=(12, 26, 9), bband_period=20, bband_k=2.0,
             pe_eps: float | pd.Series | None = None, pe_period: int = 240) -> dict:
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

    if pe_eps is not None:
        pe = calc_pe_band(close, pe_eps, pe_period)
        out.update(pe)
        out["PE_band"] = classify_pe_band(pe.get("PE_current"), pe.get("PE_mean"), pe.get("PE_std"))

    out["close"] = last(close)
    return out
