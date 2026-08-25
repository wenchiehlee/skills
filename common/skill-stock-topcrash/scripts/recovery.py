#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recovery.py — 崩盤事件的「恢復天數」與「恢復形態（V/U修復）」計算。

方法：以崩盤日往前 lookback_days 天內的最高收盤價當「崩盤前參考價」，往後找第一個
收盤價回到（大於等於）這個參考價的交易日，兩者間的日曆天數就是恢復天數；
≤45天算V修復（快速反彈），否則算U修復（緩慢/長期修復），找不到（資料截至今天都還沒
回到參考價）算「未恢復」。

45天門檻是既有崩盤事件表沿用的既定分類標準（見GoogleSheet.Banks的「崩盤Top50」分頁
欄位「恢復形態(≤45天=V)」），不是本模組自己發明的。

用「崩盤前N日內最高收盤價」當參考、不是精確的「崩盤前一天收盤價」，是因為很多崩盤
是連續多天累積跌出來的（例如11天窗口的-11%），用單一前一天的價格容易低估真正的
「崩盤前高點」。這個方法在GoogleSheet.Banks用5筆已知案例（COVID/Fed升息/日圓崩盤/
台灣COVID/Trump關稅）驗證過，4/5完全對得上既有資料，僅1筆（Fed升息2022，一段長達
478天的緩慢修復期）有明顯落差，原因未查出，數字可用但精確度要打折——這是已知限制，
不是bug。
"""
import pandas as pd


def calc_recovery(close: pd.Series, crash_date, lookback_days: int = 120,
                   v_threshold_days: int = 45) -> dict:
    """close: 完整收盤價序列（index=Timestamp，涵蓋崩盤日之後的資料愈長愈好，不夠長
    會導致「未恢復」判定不準確——沒恢復到底是真的還沒恢復、還是資料本來就只到這裡，
    呼叫端要自己注意資料涵蓋範圍）。
    回傳: {"recovery_days": int|None, "recovery_type": "V修復"|"U修復"|"未恢復",
           "reference_price": float}"""
    crash_date = pd.Timestamp(crash_date)
    pre_window = close[(close.index < crash_date) & (close.index >= crash_date - pd.Timedelta(days=lookback_days))]
    if pre_window.empty:
        return {"recovery_days": None, "recovery_type": "未恢復", "reference_price": None}

    ref = float(pre_window.max())
    after = close[close.index > crash_date]
    recovered = after[after >= ref]

    if recovered.empty:
        return {"recovery_days": None, "recovery_type": "未恢復", "reference_price": ref}

    recovery_date = recovered.index[0]
    days = (recovery_date - crash_date).days
    rtype = "V修復" if days <= v_threshold_days else "U修復"
    return {"recovery_days": days, "recovery_type": rtype, "reference_price": ref}
