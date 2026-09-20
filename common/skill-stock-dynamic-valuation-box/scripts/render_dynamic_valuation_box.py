"""Render Taiwan-stock dynamic valuation-box charts from public daily price/EPS data.

The chart is deliberately no-look-ahead.  Quarterly EPS enters the model only
on a conservative statutory filing deadline, and each day's PE band uses only
the trailing rolling window ending on that day.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
STATUTORY_DEADLINES = {3: (5, 15), 6: (8, 14), 9: (11, 14), 12: (3, 31)}


def _fetch(dataset: str, symbol: str, start: str, end: str) -> list[dict]:
    query = urlencode({"dataset": dataset, "data_id": symbol, "start_date": start, "end_date": end})
    request = Request(f"{FINMIND_URL}?{query}", headers={"User-Agent": "dynamic-valuation-box/1.0"})
    with urlopen(request, timeout=60) as response:
        body = json.load(response)
    if body.get("status") != 200:
        raise RuntimeError(f"{symbol} {dataset}: {body.get('msg', body)}")
    return body.get("data", [])


def _stock_name(symbol: str) -> str:
    """Best-effort Chinese/English name lookup so charts read "2412 中華電"
    instead of a bare code; falls back to the code alone if FinMind has
    nothing (e.g. a delisted or newly listed ticker)."""
    try:
        query = urlencode({"dataset": "TaiwanStockInfo", "data_id": symbol})
        request = Request(f"{FINMIND_URL}?{query}", headers={"User-Agent": "dynamic-valuation-box/1.0"})
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
        rows = body.get("data", [])
        return rows[0]["stock_name"] if rows else ""
    except Exception:
        return ""


def _availability_date(period_end: pd.Timestamp) -> pd.Timestamp:
    """Use conservative statutory filing deadlines, never quarter-end data."""
    month = period_end.month
    if month not in STATUTORY_DEADLINES:
        raise ValueError(f"Unexpected fiscal-quarter end: {period_end.date()}")
    filing_month, filing_day = STATUTORY_DEADLINES[month]
    filing_year = period_end.year + (1 if month == 12 else 0)
    return pd.Timestamp(date(filing_year, filing_month, filing_day))


def _stock_dividend_factors(symbol: str, start: str, end: str) -> list[tuple[pd.Timestamp, float]]:
    """Ex-date + dilution factor (1 + new shares per held share) for every stock-dividend
    (無償配股/盈餘或公積轉增資) event in range.

    Taiwan's par value is NT$10, so TaiwanStockDividend's StockEarningsDistribution
    (NT$ of stock dividend per share) / 10 = new shares received per share held —
    e.g. 6669 distributed 19.83 on 2026-09-02, i.e. 1.98 new shares per share, a
    ~2.98x share-count jump. A cash-only dividend has this field at 0 and is not a
    split-like event, so it's excluded."""
    try:
        rows = _fetch("TaiwanStockDividend", symbol, start, end)
    except Exception:
        return []
    factors = []
    for row in rows:
        ex_date = row.get("StockExDividendTradingDate")
        ratio = row.get("StockEarningsDistribution") or 0
        if ex_date and ratio:
            factors.append((pd.Timestamp(ex_date), 1 + float(ratio) / 10))
    return factors


def _cumulative_factor(dates: pd.Series, factors: list[tuple[pd.Timestamp, float]]) -> pd.Series:
    """For each date, the product of every split factor whose ex-date is later —
    i.e. how much a value anchored at that date needs shrinking to sit on the
    same (latest) share-count basis as everything after the last split."""
    factor = pd.Series(1.0, index=dates.index)
    for ex_date, ratio in sorted(factors, key=lambda item: item[0], reverse=True):
        factor.loc[dates < ex_date] *= ratio
    return factor


# 2026-09-20：6669 在 2026-09-02 配發約2.98倍的股票股利，TaiwanStockPrice的"close"
# 沒有做除權處理，原始序列在那天出現一個假的「單日跌66%」斷崖，任何橫跨這個ex-date的
# 滾動PE窗口都會混到兩種不可比的股本基礎——這是導致外層上緣算出7614卻對著2140收盤價
# 這種荒謬數字的真正原因，不是隨機資料錯誤。
#
# 這裡曾經有一版錯的修法：直接用「交易日」是否早於ex-date去把close跟daily裡的ttm_eps
# 一起除掉同一個factor。問題是分子分母同時除以同一個數，PE比值完全沒變，等於白改——
# 而且ttm_eps的正確調整基準不是「交易日」，是「這筆EPS所屬的財報期別／available_date」
# ：截至2026-09-02當下，最新一次公布的TTM EPS本來就是配股之前的股本算出來的，在配股後
# 的交易日繼續沿用同一個數字（要等下一次季報才會反映新股本），所以只要這筆EPS的
# available_date早於ex-date，不管拿去配對的是配股前或配股後的交易日，都要除以同一個
# factor——而不是看「今天是不是已經過了ex-date」。修法：EPS只用它自己的期別日期算
# factor、股價只用交易日算factor，兩邊分開處理再merge，PE才會是同一個股本基礎上的
# 真實比值。
def _adjust_for_stock_dividends(
    prices: pd.DataFrame, eps: pd.DataFrame, factors: list[tuple[pd.Timestamp, float]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not factors:
        return prices, eps
    prices = prices.copy()
    prices["close"] = prices["close"] / _cumulative_factor(prices.index.to_series(), factors)
    eps = eps.copy()
    eps["ttm_eps"] = eps["ttm_eps"] / _cumulative_factor(eps["available_date"], factors)
    return prices, eps


def _read_forward_eps(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    """Manual consensus/forward EPS estimates, one row per re-estimate, in this
    skill's own normalized shape: symbol, as_of_date, forward_eps. Use this when
    the caller has already reshaped a third-party feed; use --yahoo-consensus-csv
    or --factset-report-csv below to read a raw feed's native shape directly.

    `as_of_date` is the date the estimate was *published/known*, not the target
    fiscal period; merging on it (backward, like the trailing EPS
    available_date merge) is what keeps this no-look-ahead: on any given day we
    only ever see the newest estimate that existed by that day."""
    columns = ["symbol", "as_of_date", "forward_eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    forward = pd.read_csv(path, dtype={"symbol": str, "stock_id": str})
    if "symbol" not in forward.columns and "stock_id" in forward.columns:
        forward = forward.rename(columns={"stock_id": "symbol"})
    required = {"symbol", "as_of_date", "forward_eps"}
    missing = sorted(required - set(forward.columns))
    if missing:
        raise ValueError(f"forward-eps CSV missing columns: {', '.join(missing)}")
    forward = forward.loc[:, columns].copy()
    forward["symbol"] = forward["symbol"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    forward["as_of_date"] = pd.to_datetime(forward["as_of_date"])
    forward["forward_eps"] = pd.to_numeric(forward["forward_eps"], errors="coerce")
    forward = forward.dropna(subset=["symbol", "as_of_date", "forward_eps"]).sort_values("as_of_date")
    return forward[forward["symbol"].isin(set(symbols))]


def _read_yahoo_consensus_eps(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    """Yahoo Finance's own dated consensus feed (e.g. a sibling repo's
    data/reports/raw_yahoo_finance_consensus_daily.csv): one row per
    `forecast_asof_date` per stock_code, with next-FY consensus EPS already in
    `earnings_1y_avg`. Each row is naturally dated by the day the estimate was
    captured, so — unlike a single static snapshot — this is a real forward-EPS
    time series and needs no reshaping to satisfy the as_of_date contract."""
    columns = ["symbol", "as_of_date", "forward_eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, encoding="utf-8", dtype={"stock_code": str})
    required = {"stock_code", "forecast_asof_date", "earnings_1y_avg"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"yahoo-consensus CSV missing columns: {', '.join(missing)}")
    forward = raw.rename(columns={
        "stock_code": "symbol", "forecast_asof_date": "as_of_date", "earnings_1y_avg": "forward_eps",
    })[columns].copy()
    forward["symbol"] = forward["symbol"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    forward["as_of_date"] = pd.to_datetime(forward["as_of_date"], errors="coerce")
    forward["forward_eps"] = pd.to_numeric(forward["forward_eps"], errors="coerce")
    forward = forward.dropna(subset=["symbol", "as_of_date", "forward_eps"]).sort_values("as_of_date")
    return forward[forward["symbol"].isin(set(symbols))]


def _read_factset_eps(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    """FactSet's own dated snapshot feed (e.g. a sibling repo's
    data/reports/raw_factset_detailed_report.csv): one row per `MD日期` report
    per stock, with average consensus EPS columns for several named fiscal
    years (`2025EPS平均值` ... `2028EPS平均值`). FactSet has no single
    "next FY" column like Yahoo's earnings_1y_avg, so this picks, for each
    report's MD日期, the average-EPS column for calendar year(MD日期) + 1 —
    the same "next full fiscal year" consensus concept as Yahoo's series,
    just sourced from named-year columns instead. A report whose next FY
    column isn't present (e.g. its year is outside 2025-2028) is dropped."""
    columns = ["symbol", "as_of_date", "forward_eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, encoding="utf-8", dtype={"代號": str, "股票代號": str})
    symbol_col = "代號" if "代號" in raw.columns else "股票代號"
    required = {symbol_col, "MD日期"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"factset-report CSV missing columns: {', '.join(missing)}")
    raw = raw.copy()
    raw["symbol"] = raw[symbol_col].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    raw["as_of_date"] = pd.to_datetime(raw["MD日期"], errors="coerce")
    raw = raw.dropna(subset=["symbol", "as_of_date"])
    next_fy_col = raw["as_of_date"].dt.year.add(1).astype(str) + "EPS平均值"
    raw["forward_eps"] = pd.to_numeric(
        raw.apply(lambda row, cols=raw.columns: row[next_fy_col[row.name]] if next_fy_col[row.name] in cols else float("nan"), axis=1),
        errors="coerce",
    )
    forward = raw.dropna(subset=["forward_eps"])[columns].sort_values("as_of_date")
    forward = forward.drop_duplicates(subset=["symbol", "as_of_date"], keep="last")
    return forward[forward["symbol"].isin(set(symbols))]


def _yahoo_forward_curve(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    """Yahoo's raw feed unbundled into one row per (report date, target fiscal
    year) instead of picking only the "next FY" figure — kept separate from
    _read_yahoo_consensus_eps, which still feeds the pooled per-day forward-PE
    band. `earnings_0y_avg` targets the report's own calendar year;
    `earnings_1y_avg` targets the year after it. Both are genuine "same date,
    two different target years" facts, not a revision of one another."""
    columns = ["symbol", "source_asof_date", "target_year", "forward_eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, encoding="utf-8", dtype={"stock_code": str})
    required = {"stock_code", "forecast_asof_date", "earnings_0y_avg", "earnings_1y_avg"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"yahoo-consensus CSV missing columns: {', '.join(missing)}")
    raw = raw.copy()
    raw["symbol"] = raw["stock_code"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    raw["source_asof_date"] = pd.to_datetime(raw["forecast_asof_date"], errors="coerce")
    raw = raw.dropna(subset=["symbol", "source_asof_date"])
    rows = []
    for year_offset, eps_col in ((0, "earnings_0y_avg"), (1, "earnings_1y_avg")):
        sub = raw[["symbol", "source_asof_date", eps_col]].rename(columns={eps_col: "forward_eps"})
        sub["target_year"] = raw["source_asof_date"].dt.year + year_offset
        rows.append(sub)
    curve = pd.concat(rows, ignore_index=True)
    curve["forward_eps"] = pd.to_numeric(curve["forward_eps"], errors="coerce")
    curve = curve.dropna(subset=["forward_eps"])
    return curve[curve["symbol"].isin(set(symbols))][columns]


def _factset_forward_curve(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    """FactSet's raw feed unbundled into one row per (report date, target
    fiscal year), covering every named-year EPS平均值 column a report has
    (typically 4), not just calendar_year(MD日期)+1 — kept separate from
    _read_factset_eps, which still feeds the pooled per-day forward-PE band."""
    columns = ["symbol", "source_asof_date", "target_year", "forward_eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    raw = pd.read_csv(path, encoding="utf-8", dtype={"代號": str, "股票代號": str})
    symbol_col = "代號" if "代號" in raw.columns else "股票代號"
    required = {symbol_col, "MD日期"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"factset-report CSV missing columns: {', '.join(missing)}")
    raw = raw.copy()
    raw["symbol"] = raw[symbol_col].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    raw["source_asof_date"] = pd.to_datetime(raw["MD日期"], errors="coerce")
    raw = raw.dropna(subset=["symbol", "source_asof_date"])
    year_columns = [c for c in raw.columns if c.endswith("EPS平均值")]
    rows = []
    for col in year_columns:
        sub = raw[["symbol", "source_asof_date", col]].rename(columns={col: "forward_eps"})
        sub["target_year"] = int(col[:4])
        rows.append(sub)
    curve = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=columns)
    curve["forward_eps"] = pd.to_numeric(curve["forward_eps"], errors="coerce")
    curve = curve.dropna(subset=["forward_eps"])
    curve = curve.drop_duplicates(subset=["symbol", "source_asof_date", "target_year"], keep="last")
    return curve[curve["symbol"].isin(set(symbols))][columns]


def _latest_curve_snapshot(curve: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """The one report/date's worth of target-year estimates that was actually
    known as of `cutoff` — never a later report, and never rows mixed in from
    an earlier report once a newer one exists (that would silently blend two
    different vintages' assumptions into one "curve")."""
    known = curve[curve["source_asof_date"] <= cutoff]
    if known.empty:
        return known
    latest_date = known["source_asof_date"].max()
    return known[known["source_asof_date"] == latest_date].sort_values("target_year")


def _build_daily_box(
    symbol: str, display_years: int, end_date: pd.Timestamp, window: int, forward_eps: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Extra history warms up the PE rolling distribution before the display range.
    data_start = (end_date - pd.DateOffset(years=display_years + 3)).strftime("%Y-%m-%d")
    eps_start = (end_date - pd.DateOffset(years=display_years + 5)).strftime("%Y-%m-%d")
    end_text = end_date.strftime("%Y-%m-%d")

    prices = pd.DataFrame(_fetch("TaiwanStockPrice", symbol, data_start, end_text))
    if prices.empty:
        raise RuntimeError(f"{symbol}: no daily-price data")
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices[["date", "close"]].sort_values("date").set_index("date")

    financials = pd.DataFrame(_fetch("TaiwanStockFinancialStatements", symbol, eps_start, end_text))
    if financials.empty:
        raise RuntimeError(f"{symbol}: no financial-statement data")
    eps = financials.loc[financials["type"] == "EPS", ["date", "value"]].copy()
    if eps.empty:
        raise RuntimeError(f"{symbol}: basic EPS is unavailable")
    eps["period_end"] = pd.to_datetime(eps["date"])
    eps = eps[["period_end", "value"]].drop_duplicates("period_end", keep="last").sort_values("period_end")
    eps["available_date"] = eps["period_end"].map(_availability_date)
    eps["ttm_eps"] = eps["value"].rolling(4).sum()
    eps = eps.dropna(subset=["ttm_eps"])[["available_date", "period_end", "ttm_eps"]]

    split_factors = _stock_dividend_factors(symbol, data_start, end_text)
    prices, eps = _adjust_for_stock_dividends(prices, eps, split_factors)

    daily = pd.merge_asof(
        prices.reset_index().sort_values("date"),
        eps.sort_values("available_date"),
        left_on="date", right_on="available_date", direction="backward",
    ).set_index("date")
    daily["pe"] = daily["close"] / daily["ttm_eps"]
    min_periods = min(window, 120)
    daily["pe_mean"] = daily["pe"].rolling(window, min_periods=min_periods).mean()
    daily["pe_std"] = daily["pe"].rolling(window, min_periods=min_periods).std(ddof=1)
    for sigma, name in ((-2, "m2"), (-1, "m1"), (0, "mean"), (1, "p1"), (2, "p2")):
        daily[f"price_{name}"] = (daily["pe_mean"] + sigma * daily["pe_std"]) * daily["ttm_eps"]

    forward_cols = ["forward_eps", "forward_pe", "forward_pe_mean", "forward_pe_std"]
    forward_cols += [f"forward_price_{name}" for name in ("m2", "m1", "mean", "p1", "p2")]
    if forward_eps.empty:
        for col in forward_cols:
            daily[col] = float("nan")
    else:
        daily = pd.merge_asof(
            daily.reset_index().sort_values("date"),
            forward_eps[["as_of_date", "forward_eps"]].sort_values("as_of_date"),
            left_on="date", right_on="as_of_date", direction="backward",
        ).set_index("date")
        daily["forward_pe"] = daily["close"] / daily["forward_eps"]
        daily["forward_pe_mean"] = daily["forward_pe"].rolling(window, min_periods=min_periods).mean()
        daily["forward_pe_std"] = daily["forward_pe"].rolling(window, min_periods=min_periods).std(ddof=1)
        for sigma, name in ((-2, "m2"), (-1, "m1"), (0, "mean"), (1, "p1"), (2, "p2")):
            daily[f"forward_price_{name}"] = (daily["forward_pe_mean"] + sigma * daily["forward_pe_std"]) * daily["forward_eps"]
    return daily, eps


def _read_trade_events(path: str | None, symbols: Iterable[str]) -> pd.DataFrame:
    columns = ["symbol", "date", "side", "price", "lots"]
    if not path:
        return pd.DataFrame(columns=columns)
    trades = pd.read_csv(path, dtype={"symbol": str, "stock_id": str})
    if "symbol" not in trades.columns and "stock_id" in trades.columns:
        trades = trades.rename(columns={"stock_id": "symbol"})
    if "lots" not in trades.columns and "qty" in trades.columns:
        trades["lots"] = pd.to_numeric(trades["qty"], errors="coerce") / 1000
    required = {"symbol", "date", "side", "price", "lots"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"trades CSV missing columns: {', '.join(missing)}")
    trades = trades.loc[:, columns].copy()
    trades["symbol"] = trades["symbol"].astype(str).str.extract(r"(\d+)", expand=False).str.zfill(4)
    trades["date"] = pd.to_datetime(trades["date"])
    trades["side"] = trades["side"].astype(str).str.lower().replace({"買": "buy", "買進": "buy", "賣": "sell", "賣出": "sell"})
    trades["price"] = pd.to_numeric(trades["price"], errors="coerce")
    trades["lots"] = pd.to_numeric(trades["lots"], errors="coerce")
    trades = trades.dropna(subset=["symbol", "date", "price", "lots"])
    invalid = sorted(set(trades["side"]) - {"buy", "sell"})
    if invalid:
        raise ValueError(f"trades CSV side must be buy/sell (or 買進/賣出), got: {', '.join(invalid)}")
    return trades[trades["symbol"].isin(set(symbols))]


def _plot(
    symbol: str, name: str, years: int, daily: pd.DataFrame, eps: pd.DataFrame,
    forward_eps: pd.DataFrame, trades: pd.DataFrame, output_dir: Path,
    yahoo_curve: pd.DataFrame = None, factset_curve: pd.DataFrame = None,
) -> tuple[Path, Path]:
    display_start = daily.index.max() - pd.DateOffset(years=years)
    view = daily.loc[daily.index >= display_start].copy()
    if view.empty:
        raise RuntimeError(f"{symbol}: no data in the selected display window")

    # DejaVu Sans (the default) has no CJK glyphs, so a Chinese stock_name in the
    # title would silently render as missing-glyph boxes. Prefer whichever CJK
    # font this machine actually has installed, and fall back to DejaVu Sans
    # (English-only titles) elsewhere rather than failing outright.
    plt.rcParams["font.sans-serif"] = [
        "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Noto Sans CJK TC",
        "Noto Sans TC", "SimHei", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    # sharex=True so the two panels line up on one timeline: a forward-EPS
    # point's x-position in the bottom panel is directly comparable to the
    # top panel's price/date grid, not just internally consistent within its
    # own panel. When a forward curve's target year runs past the price
    # history (e.g. FactSet's FY2028E), both panels' x-range is explicitly
    # extended together below, rather than left to independent autoscale.
    figure, (axis, eps_axis) = plt.subplots(2, 1, figsize=(16, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1.6], "hspace": 0.1})
    label = f"{symbol} {name}" if name else symbol
    figure.suptitle(f"{label} | {years}-year price & dynamic TTM P/E valuation box", x=0.125, ha="left", y=0.975, fontsize=16, fontweight="bold")

    axis.fill_between(view.index, view["price_m2"], view["price_p2"], color="#f4c7c3", alpha=0.38, label="Outer valuation range: PE mean ±2σ")
    axis.fill_between(view.index, view["price_m1"], view["price_p1"], color="#b7e1cd", alpha=0.72, label="Core valuation box: PE mean ±1σ")
    for field, color in (("price_m2", "#c94c4c"), ("price_p2", "#c94c4c"), ("price_m1", "#3c8d5a"), ("price_p1", "#3c8d5a")):
        axis.plot(view.index, view[field], color=color, lw=0.8)
    axis.plot(view.index, view["price_mean"], color="#666666", lw=0.9, ls="--", label="PE mean")

    has_forward = view["forward_pe_mean"].notna().any()
    if has_forward:
        axis.plot(view.index, view["forward_price_mean"], color="#d9782d", lw=1.1, ls="--", label="Forward PE mean")
        for field in ("forward_price_m1", "forward_price_p1"):
            axis.plot(view.index, view[field], color="#d9782d", lw=0.7, ls=":")

    axis.plot(view.index, view["close"], color="#17365d", lw=1.7, label="Close (unadjusted)")

    # Trades can predate the display window by years (a long-held position),
    # e.g. 2324/2356/3231 have entries from 2015-2020; without this filter a
    # single old marker forces the shared x-axis to span its full trade
    # history instead of the requested --years window, squashing the actual
    # price line into a sliver at the right edge.
    event_view = trades[(trades["symbol"] == symbol) & (trades["date"] >= display_start)]
    for side, marker, color, label in (("buy", "^", "#117a4a", "Actual buys (size = lots)"), ("sell", "v", "#b71c1c", "Actual sells (size = lots)")):
        points = event_view[event_view["side"] == side]
        if not points.empty:
            axis.scatter(points["date"], points["price"], marker=marker, color=color, s=40 + points["lots"] * 16, zorder=8, label=label)

    last = view.iloc[-1]
    annotation = f"Close {last['close']:.1f}\nOuter upper {last['price_p2']:.1f}"
    if has_forward and pd.notna(last["forward_pe"]):
        annotation += f"\nForward PE {last['forward_pe']:.1f}"
    axis.annotate(annotation, xy=(view.index[-1], last["close"]), xytext=(-122, 30), textcoords="offset points", arrowprops={"arrowstyle": "->", "color": "#17365d"}, fontsize=10, bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#17365d", "alpha": 0.94})
    axis.set_ylabel("Price (TWD)")
    axis.grid(axis="y", color="#d9e2f3", lw=0.7)
    # Monthly gridlines (not just the sparser labeled year/quarter ticks) so a
    # node's exact month is readable directly off the grid, not eyeballed
    # between two labeled ticks that can be a year apart. remove_overlapping_locs
    # defaults to True, which silently drops every minor tick that lands on a
    # major tick's month — since we never draw a major x-gridline, those months
    # would render with no line at all instead of just a bolder one, leaving
    # an uneven handful of months per year rather than all 12.
    axis.xaxis.remove_overlapping_locs = False
    axis.xaxis.set_minor_locator(mdates.MonthLocator())
    axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)
    axis.legend(loc="upper left", ncol=3, fontsize=9, frameon=False)

    eps_view = eps[eps["available_date"] >= display_start]
    # step() only draws between given x-values, so without this the line just
    # stops dead at the last node instead of showing that its TTM figure is
    # still the operative one all the way to today (it holds until the next
    # quarter's statutory deadline actually updates it).
    line_x = pd.concat([eps_view["available_date"], pd.Series([view.index.max()])], ignore_index=True)
    line_y = pd.concat([eps_view["ttm_eps"], pd.Series([eps_view["ttm_eps"].iloc[-1]])], ignore_index=True)
    eps_axis.step(line_x, line_y, where="post", color="#6a329f", lw=2, label="Trailing TTM EPS")
    eps_axis.scatter(eps_view["available_date"], eps_view["ttm_eps"], color="#6a329f", s=26, zorder=3)

    # Yahoo and FactSet forward-EPS curves are plotted separately, unmerged —
    # each source's own estimates placed at the calendar year they actually
    # forecast, not at publish date. The two sources routinely disagree on the
    # same target year (see project notes); showing them side by side is the
    # point, not a defect to reconcile.
    #
    # Every known revision for a given (source, target year) is shown, not
    # just the latest — a consensus that moved from 64 to 99 over several
    # reports is a materially different fact than one that was always 99, and
    # collapsing to "whichever was newest" erased that history. Older
    # revisions render smaller/fainter, a thin dotted line traces the
    # revision path at that year's fixed x, and only the latest value gets a
    # text label to avoid clutter. A second dotted line then connects each
    # source's latest-known value across consecutive target years, so the
    # shape of its forward curve (e.g. FY2026E -> FY2027E -> FY2028E) reads at
    # a glance instead of as isolated dots.
    cutoff = view.index.max()
    forward_points = []  # (x, y, source_label, target_year, color, source_index)
    for source_index, (source_label, curve, color, marker) in enumerate((
        ("Yahoo", yahoo_curve, "#d9782d", "D"),
        ("FactSet", factset_curve, "#1b7f9e", "s"),
    )):
        if curve is None or curve.empty:
            continue
        known = curve[curve["source_asof_date"] <= cutoff]
        if known.empty:
            continue
        x_jitter = pd.Timedelta(days=-30 + source_index * 60)
        latest_report_date = known["source_asof_date"].max().date()
        year_latest = []  # (x, target_year, forward_eps) — one per year, for the cross-year line
        for target_year, revisions in known.groupby("target_year"):
            revisions = revisions.sort_values("source_asof_date")
            x = pd.Timestamp(year=int(target_year), month=7, day=1) + x_jitter
            n = len(revisions)
            for i, forward_eps in enumerate(revisions["forward_eps"]):
                is_latest = i == n - 1
                eps_axis.scatter(
                    [x], [forward_eps], color=color, marker=marker, zorder=4 if is_latest else 3,
                    s=55 if is_latest else 22 + 18 * i / max(n - 1, 1),
                    alpha=1.0 if is_latest else 0.35 + 0.4 * i / max(n - 1, 1),
                )
            if n > 1:
                eps_axis.plot([x, x], [revisions["forward_eps"].iloc[0], revisions["forward_eps"].iloc[-1]], color=color, lw=1, ls=":", alpha=0.55, zorder=2)
            year_latest.append((x, int(target_year), revisions["forward_eps"].iloc[-1]))
        year_latest.sort(key=lambda item: item[0])
        eps_axis.plot([p[0] for p in year_latest], [p[2] for p in year_latest], color=color, lw=1, ls=":", zorder=3, label=f"{source_label} forward EPS (latest per FY, as of {latest_report_date})")
        for x, target_year, forward_eps in year_latest:
            forward_points.append((x, forward_eps, source_label, target_year, color, source_index))

    any_forward_curve = bool(forward_points)
    # Shared axis: extend both panels together to cover the furthest-out
    # forward-curve point, rather than letting each panel's own autoscale
    # fight over the (linked) shared x-limits.
    range_end = max([view.index.max()] + [p[0] for p in forward_points])
    axis.set_xlim(view.index.min(), range_end)
    # Forward-curve label offsets are sized as a fraction of the actual
    # y-range, not a fixed point distance, so a point sitting far above
    # everything else doesn't push its own label past the panel's own top
    # edge — a fixed-points offset does exactly that once the y-range grows,
    # bleeding text into the panel above it.
    eps_axis.margins(y=0.25)
    if any_forward_curve:
        all_y = pd.concat([eps_view["ttm_eps"], pd.Series([p[1] for p in forward_points])])
        y_span = max(all_y.max() - all_y.min(), 1e-9)
        for x, y, source_label, target_year, color, source_index in forward_points:
            text_y = y + (0.07 + 0.09 * source_index) * y_span
            eps_axis.annotate(f"{source_label} FY{target_year}E {y:.1f}", xy=(x, y), xytext=(x, text_y), textcoords="data", fontsize=7.5, color=color, ha="center", va="bottom")
        eps_axis.legend(loc="upper left", fontsize=8, frameon=False)
    eps_axis.set_ylabel("EPS")
    eps_axis.set_xlabel("Trading day")
    eps_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    eps_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    eps_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    eps_axis.xaxis.remove_overlapping_locs = False
    eps_axis.xaxis.set_minor_locator(mdates.MonthLocator())
    eps_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)
    figure.text(0.01, 0.01, "Data: FinMind TaiwanStockPrice / TaiwanStockFinancialStatements. P/E uses unadjusted price and nominal EPS; use dividend-adjusted prices separately for technical research.", fontsize=8.5, color="#555555")
    figure.subplots_adjust(top=0.93)

    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"{symbol}_dynamic_valuation_box_{years}y.png"
    csv_path = output_dir / f"{symbol}_dynamic_valuation_box_{years}y.csv"
    figure.savefig(png_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    view.reset_index().to_csv(csv_path, index=False, float_format="%.6f")
    return png_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True, help="Taiwan stock codes, e.g. 3045 2412")
    parser.add_argument("--years", type=int, choices=(2, 3, 4, 5), default=2, help="Visible price-history years")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Analysis cutoff date, YYYY-MM-DD")
    parser.add_argument("--window", type=int, default=120, help="Rolling PE observations (default: 120, minimum: 120)")
    parser.add_argument("--trades-csv", help="Optional CSV: symbol,date,side,price,lots; supports stock_id/qty aliases and 買進/賣出")
    parser.add_argument("--forward-eps-csv", help="Optional CSV, this skill's own shape: symbol,as_of_date,forward_eps (as_of_date = when the estimate was published, not the target fiscal period)")
    parser.add_argument("--yahoo-consensus-csv", help="Optional CSV in Yahoo Finance's native shape (stock_code, forecast_asof_date, earnings_1y_avg, ...), e.g. a sibling Yahoo.Finance repo's data/reports/raw_yahoo_finance_consensus_daily.csv")
    parser.add_argument("--factset-report-csv", help="Optional CSV in FactSet's native shape (代號/股票代號, MD日期, <year>EPS平均值 columns), e.g. a sibling repo's data/reports/raw_factset_detailed_report.csv")
    parser.add_argument("--output-dir", default="output/dynamic_valuation_box")
    args = parser.parse_args()
    if args.window < 120:
        parser.error("--window must be at least 120 observations")

    symbols = [str(symbol).zfill(4) for symbol in args.symbols]
    end_date = pd.Timestamp(args.end_date)
    trades = _read_trade_events(args.trades_csv, symbols)
    # Multiple forward-EPS sources may be given at once; the backward merge_asof in
    # _build_daily_box only cares about the newest as_of_date known by each trading
    # day, so pooling them and sorting is enough — whichever source last re-estimated
    # wins, regardless of which feed it came from.
    forward_eps_sources = [
        _read_forward_eps(args.forward_eps_csv, symbols),
        _read_yahoo_consensus_eps(args.yahoo_consensus_csv, symbols),
        _read_factset_eps(args.factset_report_csv, symbols),
    ]
    forward_eps_sources = [df for df in forward_eps_sources if not df.empty]
    if forward_eps_sources:
        forward_eps_all = pd.concat(forward_eps_sources, ignore_index=True).sort_values("as_of_date")
    else:
        forward_eps_all = pd.DataFrame(columns=["symbol", "as_of_date", "forward_eps"])
    # For the bottom-panel display, Yahoo and FactSet are kept unmerged (see
    # _plot): each source's own target-fiscal-year curve, not pooled into the
    # single per-day series above.
    yahoo_curve_all = _yahoo_forward_curve(args.yahoo_consensus_csv, symbols)
    factset_curve_all = _factset_forward_curve(args.factset_report_csv, symbols)
    output_dir = Path(args.output_dir)
    for symbol in symbols:
        name = _stock_name(symbol)
        forward_eps = forward_eps_all[forward_eps_all["symbol"] == symbol]
        daily, eps = _build_daily_box(symbol, args.years, end_date, args.window, forward_eps)
        yahoo_curve = yahoo_curve_all[yahoo_curve_all["symbol"] == symbol]
        factset_curve = factset_curve_all[factset_curve_all["symbol"] == symbol]
        png_path, csv_path = _plot(symbol, name, args.years, daily, eps, forward_eps, trades, output_dir, yahoo_curve, factset_curve)
        print(f"{symbol}: {png_path}")
        print(f"{symbol}: {csv_path}")


if __name__ == "__main__":
    main()
