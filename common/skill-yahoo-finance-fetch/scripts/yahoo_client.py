#!/usr/bin/env python3
"""Small wrapper around yfinance analyst analysis methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import yfinance as yf


SECTION_METHODS: List[Tuple[str, str]] = [
    ("收益預估", "get_revenue_estimate"),
    ("盈利預估", "get_earnings_estimate"),
    ("盈利記錄", "get_earnings_history"),
    ("每股盈利走勢", "get_eps_trend"),
    ("每股盈利修改", "get_eps_revisions"),
    ("預計增長", "get_growth_estimates"),
]

METRIC_ZH = {
    "avg": "平均值",
    "low": "最低值",
    "high": "最高值",
    "numberOfAnalysts": "分析師數量",
    "yearAgoEps": "去年EPS",
    "growth": "成長率",
    "epsEstimate": "EPS預估",
    "epsActual": "EPS實際",
    "epsDifference": "EPS差異",
    "surprisePercent": "驚喜百分比",
    "current": "目前",
    "7daysAgo": "7天前",
    "30daysAgo": "30天前",
    "60daysAgo": "60天前",
    "90daysAgo": "90天前",
    "upLast7days": "近7天上修",
    "upLast30days": "近30天上修",
    "downLast7days": "近7天下修",
    "downLast30days": "近30天下修",
    "stockTrend": "公司成長",
    "industryTrend": "產業成長",
    "sectorTrend": "板塊成長",
    "indexTrend": "指數成長",
}


@dataclass
class YahooTable:
    section: str
    source_method: str
    frame: pd.DataFrame


class YahooFinanceClient:
    def fetch_tables(self, yahoo_symbol: str) -> List[YahooTable]:
        ticker = yf.Ticker(yahoo_symbol)
        tables: List[YahooTable] = []
        for section, method_name in SECTION_METHODS:
            method = getattr(ticker, method_name)
            frame = method()
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                tables.append(YahooTable(section, method_name, frame))
        return tables

    @staticmethod
    def flatten_table(table: YahooTable) -> Iterable[Dict[str, str]]:
        frame = table.frame.copy()
        frame = frame.where(pd.notnull(frame), "")
        for row_key, row in frame.iterrows():
            for col_key, value in row.items():
                if value == "":
                    continue
                period, metric = YahooFinanceClient._period_metric(str(row_key), str(col_key))
                yield {
                    "section": table.section,
                    "source_method": table.source_method,
                    "period": period,
                    "metric": metric,
                    "metric_zh": METRIC_ZH.get(metric, metric),
                    "value": str(value),
                    "unit": YahooFinanceClient._infer_unit(table.section, metric),
                }

    @staticmethod
    def _period_metric(index_value: str, column_value: str) -> Tuple[str, str]:
        period_tokens = {"0q", "+1q", "0y", "+1y", "+5y", "-5y"}
        if column_value in period_tokens or column_value.endswith(("q", "y")):
            return column_value, index_value
        return index_value, column_value

    @staticmethod
    def _infer_unit(section: str, metric: str) -> str:
        if metric in {"numberOfAnalysts", "upLast7days", "upLast30days", "downLast7days", "downLast30days"}:
            return "count"
        if metric == "growth" or metric.endswith("Trend") or "Percent" in metric:
            return "pct"
        if section == "收益預估":
            return "revenue"
        if section in {"盈利預估", "盈利記錄", "每股盈利走勢"}:
            return "eps"
        return ""
