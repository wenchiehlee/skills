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


def _availability_date(period_end: pd.Timestamp) -> pd.Timestamp:
    """Use conservative statutory filing deadlines, never quarter-end data."""
    month = period_end.month
    if month not in STATUTORY_DEADLINES:
        raise ValueError(f"Unexpected fiscal-quarter end: {period_end.date()}")
    filing_month, filing_day = STATUTORY_DEADLINES[month]
    filing_year = period_end.year + (1 if month == 12 else 0)
    return pd.Timestamp(date(filing_year, filing_month, filing_day))


def _build_daily_box(symbol: str, display_years: int, end_date: pd.Timestamp, window: int) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def _plot(symbol: str, years: int, daily: pd.DataFrame, eps: pd.DataFrame, trades: pd.DataFrame, output_dir: Path, window: int) -> tuple[Path, Path]:
    display_start = daily.index.max() - pd.DateOffset(years=years)
    view = daily.loc[daily.index >= display_start].copy()
    if view.empty:
        raise RuntimeError(f"{symbol}: no data in the selected display window")

    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    figure, (axis, eps_axis) = plt.subplots(2, 1, figsize=(16, 9), sharex=True, gridspec_kw={"height_ratios": [4, 1], "hspace": 0.08})
    figure.suptitle(f"{symbol} | {years}-year price & dynamic TTM P/E valuation box", x=0.125, ha="left", y=0.975, fontsize=16, fontweight="bold")
    figure.text(0.125, 0.945, f"TTM EPS is available only after a conservative statutory deadline; each band uses the prior {window} trading-day PE history.", fontsize=9.5, color="#555555")

    axis.fill_between(view.index, view["price_m2"], view["price_p2"], color="#f4c7c3", alpha=0.38, label="Outer valuation range: PE mean ±2σ")
    axis.fill_between(view.index, view["price_m1"], view["price_p1"], color="#b7e1cd", alpha=0.72, label="Core valuation box: PE mean ±1σ")
    for field, color in (("price_m2", "#c94c4c"), ("price_p2", "#c94c4c"), ("price_m1", "#3c8d5a"), ("price_p1", "#3c8d5a")):
        axis.plot(view.index, view[field], color=color, lw=0.8)
    axis.plot(view.index, view["price_mean"], color="#666666", lw=0.9, ls="--", label="PE mean")
    axis.plot(view.index, view["close"], color="#17365d", lw=1.7, label="Close (unadjusted)")

    event_view = trades[trades["symbol"] == symbol]
    for side, marker, color, label in (("buy", "^", "#117a4a", "Actual buys (size = lots)"), ("sell", "v", "#b71c1c", "Actual sells (size = lots)")):
        points = event_view[event_view["side"] == side]
        if not points.empty:
            axis.scatter(points["date"], points["price"], marker=marker, color=color, s=40 + points["lots"] * 16, zorder=8, label=label)

    last = view.iloc[-1]
    axis.annotate(f"Close {last['close']:.1f}\nOuter upper {last['price_p2']:.1f}", xy=(view.index[-1], last["close"]), xytext=(-122, 30), textcoords="offset points", arrowprops={"arrowstyle": "->", "color": "#17365d"}, fontsize=10, bbox={"boxstyle": "round,pad=0.35", "fc": "white", "ec": "#17365d", "alpha": 0.94})
    axis.set_ylabel("Price (TWD)")
    axis.grid(axis="y", color="#d9e2f3", lw=0.7)
    axis.legend(loc="upper left", ncol=3, fontsize=9, frameon=False)

    eps_view = eps[eps["available_date"] >= display_start]
    eps_axis.step(eps_view["available_date"], eps_view["ttm_eps"], where="post", color="#6a329f", lw=2)
    eps_axis.scatter(eps_view["available_date"], eps_view["ttm_eps"], color="#6a329f", s=26, zorder=3)
    eps_axis.set_ylabel("Available TTM EPS")
    eps_axis.set_xlabel("Trading day")
    eps_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    eps_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    eps_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    figure.text(0.01, 0.01, "Data: FinMind TaiwanStockPrice / TaiwanStockFinancialStatements. P/E uses unadjusted price and nominal EPS; use dividend-adjusted prices separately for technical research.", fontsize=8.5, color="#555555")
    figure.subplots_adjust(top=0.90)

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
    parser.add_argument("--window", type=int, default=500, help="Rolling PE observations (default: 500)")
    parser.add_argument("--trades-csv", help="Optional CSV: symbol,date,side,price,lots; supports stock_id/qty aliases and 買進/賣出")
    parser.add_argument("--output-dir", default="output/dynamic_valuation_box")
    args = parser.parse_args()
    if args.window < 120:
        parser.error("--window must be at least 120 observations")

    symbols = [str(symbol).zfill(4) for symbol in args.symbols]
    end_date = pd.Timestamp(args.end_date)
    trades = _read_trade_events(args.trades_csv, symbols)
    output_dir = Path(args.output_dir)
    for symbol in symbols:
        daily, eps = _build_daily_box(symbol, args.years, end_date, args.window)
        png_path, csv_path = _plot(symbol, args.years, daily, eps, trades, output_dir, args.window)
        print(f"{symbol}: {png_path}")
        print(f"{symbol}: {csv_path}")


if __name__ == "__main__":
    main()
