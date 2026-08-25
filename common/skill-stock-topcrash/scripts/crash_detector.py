#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crash_detector.py — 純邏輯：從一段日收盤價序列裡找出「崩盤 Top N」。

判定方式：對每個交易日算 1/3/5/7/9/11 日報酬（今天相對N個交易日前），取六者最小值當
「這天最壞的表現」，全樣本依最壞表現排序（最負的排最前），依序選入，遇到同一具名事件
只取最壞的一筆、未命名事件用日期間隔去重，直到湊滿 top_n 筆或沒有更負的候選為止。
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

from datetime import date

import pandas as pd

DROP_WINDOWS = [1, 3, 5, 7, 9, 11]
WINDOW_LABELS = {1: "單日", 3: "3日", 5: "5日", 7: "7日", 9: "9日", 11: "11日"}


def find_top_crashes(close: pd.Series, min_drop: float = -3.0, top_n: int = 50,
                      dedup_days: int = 10, event_label_fn=None) -> list[dict]:
    """close: pd.Series，index為交易日(Timestamp)，由舊到新排序，值為收盤價。
    event_label_fn: 可選，函式 dt(Timestamp) -> str，回傳具名事件標籤；
                     沒給的話全部視為獨立事件（只用日期間隔去重，不用事件名稱去重）。
    回傳: [{date, close, d1..d11, worst, worst_type, event}, ...]，依worst由小到大排序
    （最負最前），最多 top_n 筆。"""
    drops = {n: close.pct_change(n) * 100 for n in DROP_WINDOWS}
    combined = pd.DataFrame(drops).dropna()
    combined["worst"] = combined.min(axis=1)
    combined["worst_type"] = combined[DROP_WINDOWS].idxmin(axis=1).map(WINDOW_LABELS)

    ranked = combined.sort_values("worst")
    selected = []
    used_dates: list[pd.Timestamp] = []
    used_events: set[str] = set()

    for dt, row in ranked.iterrows():
        if row["worst"] >= min_drop:
            break
        label = event_label_fn(dt) if event_label_fn else None
        if label and label != "其他":
            if label in used_events:
                continue
            used_events.add(label)
        else:
            if any(abs((dt - u).days) <= dedup_days for u in used_dates):
                continue
        selected.append((dt, row, label or "其他"))
        used_dates.append(dt)
        if len(selected) >= top_n:
            break

    out = []
    for dt, row, label in selected:
        entry = {
            "date": dt,
            "close": float(close.asof(dt)),
            "worst": float(row["worst"]),
            "worst_type": row["worst_type"],
            "event": label,
        }
        for n in DROP_WINDOWS:
            entry[f"d{n}"] = float(row[n])
        out.append(entry)
    return out
