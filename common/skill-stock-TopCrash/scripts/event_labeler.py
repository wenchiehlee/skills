#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
event_labeler.py — 依日期查具名崩盤事件標籤，兩層優先序：

  1. 呼叫端傳入的 named_events 清單（優先，通常是手動整理過、信心較高的大事件）
  2. 呼叫端傳入的細粒度事件 CSV（欄位：事件名稱,開始日期,結束日期；同一天命中多筆
     時取「窗口最短」的那筆，代表最貼近的事件）
  3. 都沒命中 → 「其他」

兩個來源都是可選的（都不給就永遠回傳「其他」，crash_detector 會退化成純日期去重）。
"""
from __future__ import annotations  # Python 3.8相容：本檔案有list[dict]/X|None這類PEP585/604語法，3.8需要這行才能import

import pandas as pd


def build_event_labeler(named_events: list[dict] | None = None, events_csv: str | None = None):
    """named_events: [{"name": str, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, ...]
    events_csv: CSV路徑，需含「事件名稱」「開始日期」「結束日期」三欄。
    回傳: get_event_label(dt) -> str"""
    named_events = named_events or []

    csv_df = None
    if events_csv:
        csv_df = pd.read_csv(events_csv, parse_dates=["開始日期", "結束日期"])
        csv_df = csv_df.dropna(subset=["事件名稱", "開始日期", "結束日期"])
        csv_df["duration"] = (csv_df["結束日期"] - csv_df["開始日期"]).dt.days

    def get_event_label(dt) -> str:
        s = pd.Timestamp(dt).strftime("%Y-%m-%d")
        for ev in named_events:
            if ev["start"] <= s <= ev["end"]:
                return ev["name"].replace("\n", " ")

        if csv_df is not None:
            ts = pd.Timestamp(dt)
            matched = csv_df[(csv_df["開始日期"] <= ts) & (csv_df["結束日期"] >= ts)]
            if not matched.empty:
                return matched.sort_values("duration").iloc[0]["事件名稱"]

        return "其他"

    return get_event_label
