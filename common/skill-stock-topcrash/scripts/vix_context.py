#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vix_context.py — 崩盤事件的VIX/CNN恐慌貪婪指數情境標註。

分級門檻是從既有崩盤事件表（人工維護）裡的label反推校準出來的，不是官方公告的門檻，
但跟業界慣用的VIX regime（<15低波動/15-20正常/20-30警戒/30-40高度恐慌/>=40極端）
以及CNN Fear&Greed標準5分級（0-24/25-44/45-55/56-75/76-100）大致吻合。
"""
import pandas as pd


def load_vix_csv(path: str):
    """讀VIX合併CSV（欄位：Date, US_VIX, Taiwan_VIX, CNN_FG），回傳三個以日期為index的
    Series，供 get_vix_context() 用 .asof() 查詢。"""
    df = pd.read_csv(path, parse_dates=["Date"]).sort_values("Date").set_index("Date")
    return (
        df["US_VIX"].dropna(),
        df["Taiwan_VIX"].dropna(),
        df["CNN_FG"].dropna(),
    )


def label_vix(v: float) -> str:
    if v < 15:
        return "非理性繁榮"
    if v < 20:
        return "正常"
    if v < 30:
        return "警戒"
    if v < 40:
        return "高度恐慌"
    return "非理性恐慌"


def label_cnn(v: float) -> str:
    if v < 25:
        return "極度恐慌"
    if v < 45:
        return "恐慌"
    if v < 56:
        return "中性"
    if v < 76:
        return "貪婪"
    return "極度貪婪"


def _fmt_vix(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):.1f} ({label_vix(float(v))})"


def _fmt_cnn(v):
    if v is None or pd.isna(v):
        return "-"
    return f"{int(round(float(v)))} ({label_cnn(float(v))})"


def get_vix_context(dt, us_vix: pd.Series, tw_vix: pd.Series, cnn_fg: pd.Series) -> dict:
    """回傳崩盤日 dt 前5/3/1日與當日的US VIX、台灣VIX，跟當日CNN恐慌貪婪指數，
    每個數值都已格式化成「數字 (標籤)」字串，跟原本崩盤Top50分頁的欄位格式一致。"""
    dt = pd.Timestamp(dt)
    out = {}
    for days_before, suffix in [(5, "5d"), (3, "3d"), (1, "1d"), (0, "0d")]:
        target = dt - pd.Timedelta(days=days_before)
        out[f"us_vix_{suffix}"] = _fmt_vix(us_vix.asof(target))
        out[f"tw_vix_{suffix}"] = _fmt_vix(tw_vix.asof(target))
    out["cnn_fg"] = _fmt_cnn(cnn_fg.asof(dt))
    return out
