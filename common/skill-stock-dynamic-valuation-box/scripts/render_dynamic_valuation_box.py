"""Render Taiwan-stock dynamic valuation-box charts from public daily price/EPS data.

The chart is deliberately no-look-ahead.  Quarterly EPS enters the model only
on a conservative statutory filing deadline, and each day's PE band uses only
the trailing rolling window ending on that day.
"""

from __future__ import annotations

import argparse
import os
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo
import requests
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd


SKILL_METADATA_PATH = Path(__file__).resolve().parents[1] / "metadata.json"
try:
    _skill_metadata = json.loads(SKILL_METADATA_PATH.read_text(encoding="utf-8"))
    CHART_SKILL_VERSION = str(_skill_metadata["version"])
    CHART_VERSION = f"{_skill_metadata['name']}@{CHART_SKILL_VERSION}"
except (OSError, ValueError, KeyError):
    CHART_SKILL_VERSION = "unknown"
    CHART_VERSION = "skill-stock-dynamic-valuation-box@unknown"
CHART_FONT_VERSION = "noto-sans-cjk-tc-v1"
CHART_METADATA = f"chart-version: {CHART_VERSION}; font: {CHART_FONT_VERSION}"


def _updated_label() -> str:
    updated = datetime.now(ZoneInfo("Asia/Taipei"))
    return updated.strftime("Updated: %Y-%m-%d %H:%M CST") + f" ({CHART_SKILL_VERSION})"

try:
    # Optional: matches skill-finmind-fetch's convention of reading tokens from
    # a .env file rather than requiring them already exported in the shell.
    # Falls back to plain os.environ (still works for CI secrets, which are
    # exported directly) if python-dotenv isn't installed.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _load_local_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_local_dotenv()

# Sibling registry skill: the μ/σ/±1σ/±2σ PE-band math is shared with
# skill-stock-ma-rsi-bband-macd-peband's calc_pe_band_series() instead of being
# reimplemented here. That function takes no position on adjusted-vs-unadjusted
# close (pure PE_t = close_t/EPS_t math), so it's safe to feed the unadjusted
# close this skill deliberately uses (see "Required valuation rules" below).
PEBAND_SCRIPTS_DIR = (Path(__file__).resolve().parent / "../../skill-stock-ma-rsi-bband-macd-peband/scripts").resolve()
sys.path.insert(0, str(PEBAND_SCRIPTS_DIR))
from indicators import calc_bbands, calc_ma, calc_pe_band_series  # noqa: E402

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_QUOTA_URL = "https://api.web.finmindtrade.com/v2/user_info"
STATUTORY_DEADLINES = {3: (5, 15), 6: (8, 14), 9: (11, 14), 12: (3, 31)}

# Historical drift across this codebase's various FinMind-consuming scripts left
# three different env-var naming schemes for a pool of rotatable tokens (a single
# free FinMind account's daily quota is tiny) — this skill's own original
# FINMIND_TOKEN/FINMIND_API_TOKEN, the numbered FINMIND_TOKEN1..20 convention that
# is actually current (see Python-Actions.FinMind's .env.example and its
# daily-finmind-status.yml secrets), and skill-finmind-fetch's
# FINDMIND_GMAIL_TOKEN[1-6] (note the transposed "FINDMIND" spelling there,
# which turns out to be a legacy name only still referenced by an archived
# script — kept here purely for backward compatibility, checked last).
# Checking all of them means whichever convention is already in a given
# machine's .env just works, instead of forcing a rename or a hard dependency
# on skill-finmind-fetch's heavier requests/python-dotenv-based fetch module
# just to read token names.
TOKEN_ENV_NAMES = (
    "FINMIND_TOKEN", "FINMIND_API_TOKEN",
    *(f"FINMIND_TOKEN{i}" for i in range(1, 21)),
    "FINDMIND_GMAIL_TOKEN", *(f"FINDMIND_GMAIL_TOKEN{i}" for i in range(1, 21)),
)

_live_tokens: list[str] | None = None
_token_remaining: dict[str, int] = {}


def _finmind_quota_remaining(token: str) -> int:
    """Return the current hourly quota remaining for a token.

    FinMind's data API now requires Bearer authentication; this separate
    user-info check is a guard against retrying known-exhausted tokens.
    Cache the result per process and decrement after each successful data
    request so a render batch does not need a quota call for every request.
    """
    if token in _token_remaining:
        return _token_remaining[token]
    try:
        response = requests.get(
            FINMIND_QUOTA_URL, headers={"Authorization": f"Bearer {token}"}, timeout=20,
        )
        body = response.json()
        limit = int(body.get("api_request_limit", 0) or 0)
        used = int(body.get("user_count", 0) or 0)
        remaining = max(limit - used, 0) if limit > 0 else 0
    except (requests.RequestException, OSError, ValueError, TypeError):
        remaining = 0
    _token_remaining[token] = remaining
    return remaining


def _finmind_tokens() -> list[str]:
    """Every configured token, deduplicated, in the order TOKEN_ENV_NAMES lists
    them. Cached at module scope and only ever shrunk (via _retire_token) so a
    token that FinMind rejects mid-run stays retired for the rest of this
    process instead of being retried on every subsequent _fetch call."""
    global _live_tokens
    if _live_tokens is None:
        seen: list[str] = []
        for name in TOKEN_ENV_NAMES:
            value = os.environ.get(name)
            if value and value.strip() and value.strip() not in seen:
                seen.append(value.strip())
        # Double-check every token against FinMind's quota API before the
        # first data request; exhausted tokens are never selected.
        _live_tokens = [token for token in seen if _finmind_quota_remaining(token) > 0]
    return _live_tokens


def _retire_token(token: str) -> None:
    if _live_tokens and token in _live_tokens:
        _live_tokens.remove(token)


def _fetch(dataset: str, symbol: str, start: str, end: str) -> list[dict]:
    tokens = _finmind_tokens()
    # None = anonymous request. Anonymous FinMind quota is small enough that a
    # single run can exhaust it, but it is still a valid mode this skill has
    # always supported for light/no-token use, so it stays the fallback rather
    # than a hard requirement.
    attempt_tokens: list[str | None] = list(tokens) if tokens else [None]
    last_error: Exception | None = None
    for token in attempt_tokens:
        params = {"dataset": dataset, "data_id": symbol, "start_date": start, "end_date": end}
        headers = {"User-Agent": "dynamic-valuation-box/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.get(FINMIND_URL, params=params, headers=headers, timeout=60)
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            raise RuntimeError(f"{symbol} {dataset}: FinMind request failed ({exc})") from exc
        if response.status_code == 402 and token:
            _retire_token(token)
            continue
        if token and token in _token_remaining:
            _token_remaining[token] = max(_token_remaining[token] - 1, 0)
        if body.get("status") != 200:
            msg = str(body.get("msg", "")).strip()
            if token and ("reach the upper limit" in msg.lower() or "token is illegal" in msg.lower()):
                _retire_token(token)
                last_error = RuntimeError(msg)
                continue
            raise RuntimeError(f"{symbol} {dataset}: {body.get('msg', body)}")
        return body.get("data", [])
    raise RuntimeError(
        f"{symbol} {dataset}: FinMind quota exhausted on every configured token. "
        f"Set at least one of {', '.join(TOKEN_ENV_NAMES[:4])}, ... in the environment or .env."
    ) from last_error


def _stock_name(symbol: str) -> str:
    """Best-effort Chinese/English name lookup so charts read "2412 中華電"
    instead of a bare code; falls back to the code alone if FinMind has
    nothing (e.g. a delisted or newly listed ticker)."""
    try:
        rows = _fetch("TaiwanStockInfo", symbol, "", "")
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


def _normalize_symbol_series(values: pd.Series) -> pd.Series:
    """Normalize Taiwan numeric codes while preserving international tickers."""
    text = values.astype(str).str.strip()
    numeric = text.str.extract(r"^(\d+)(?:\.0)?$", expand=False)
    return numeric.where(numeric.notna(), text.str.upper()).where(numeric.isna(), numeric.str.zfill(4))


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
    forward["symbol"] = _normalize_symbol_series(forward["symbol"])
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
    forward["symbol"] = _normalize_symbol_series(forward["symbol"])
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
    raw["symbol"] = _normalize_symbol_series(raw[symbol_col])
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
    raw["symbol"] = _normalize_symbol_series(raw["stock_code"])
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
    raw["symbol"] = _normalize_symbol_series(raw[symbol_col])
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
    known = curve[curve["source_asof_date"] <= cutoff].sort_values("source_asof_date").copy()
    if known.empty:
        known = known.loc[known.groupby("target_year")["forward_eps"].shift().ne(known["forward_eps"])]
        return known
    latest_date = known["source_asof_date"].max()
    return known[known["source_asof_date"] == latest_date].sort_values("target_year")



def _build_monthly_revenue(symbol: str, start: str, end: str) -> pd.DataFrame:
    rows = _fetch("TaiwanStockMonthRevenue", symbol, start, end)
    revenue = pd.DataFrame(rows)
    if revenue.empty:
        return pd.DataFrame(columns=["date", "finmind_revenue_m_twd", "finmind_yoy_pct"])
    revenue["year"] = pd.to_numeric(revenue["revenue_year"], errors="coerce")
    revenue["month"] = pd.to_numeric(revenue["revenue_month"], errors="coerce")
    revenue["revenue"] = pd.to_numeric(revenue["revenue"], errors="coerce")
    revenue = revenue.dropna(subset=["year", "month", "revenue"]).copy()
    revenue["date"] = pd.to_datetime(dict(year=revenue["year"].astype(int), month=revenue["month"].astype(int), day=1))
    revenue = revenue.sort_values("date").drop_duplicates("date", keep="last")
    revenue["finmind_revenue_m_twd"] = revenue["revenue"] / 1e6
    revenue["finmind_yoy_pct"] = revenue["finmind_revenue_m_twd"].replace(0, float("nan")).pct_change(12) * 100
    return revenue[["date", "finmind_revenue_m_twd", "finmind_yoy_pct"]].reset_index(drop=True)


def _read_analyzer_revenue(path: str, symbol: str) -> pd.DataFrame:
    columns = ["date", "analyzer_revenue_m_twd", "analyzer_yoy_pct"]
    if not path:
        return pd.DataFrame(columns=columns)
    try:
        revenue = pd.read_csv(path, encoding="utf-8-sig")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return pd.DataFrame(columns=columns)
    revenue["stock_code"] = revenue["stock_code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    revenue = revenue[revenue["stock_code"] == symbol].copy()
    if revenue.empty:
        return pd.DataFrame(columns=columns)
    revenue["date"] = pd.to_datetime(revenue["月別"].astype(str).str.replace("/", "-", regex=False) + "-01", errors="coerce")
    revenue["analyzer_revenue_m_twd"] = pd.to_numeric(revenue["合併營業收入_營收_億"], errors="coerce") * 100
    revenue = revenue.dropna(subset=["date", "analyzer_revenue_m_twd"]).sort_values("date").drop_duplicates("date", keep="last")
    revenue["analyzer_yoy_pct"] = revenue["analyzer_revenue_m_twd"].replace(0, float("nan")).pct_change(12) * 100
    return revenue[columns].reset_index(drop=True)


def _read_finmind_revenue_csv(path: str, symbol: str) -> pd.DataFrame:
    """Read the synchronized local FinMind monthly-revenue export."""
    columns = ["date", "finmind_revenue_m_twd", "finmind_yoy_pct"]
    if not path:
        return pd.DataFrame(columns=columns)
    try:
        revenue = pd.read_csv(path, encoding="utf-8-sig")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return pd.DataFrame(columns=columns)
    required = {"stock_code", "月別", "合併營業收入_營收_億"}
    if not required.issubset(revenue.columns):
        return pd.DataFrame(columns=columns)
    revenue["stock_code"] = revenue["stock_code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    revenue = revenue[revenue["stock_code"] == symbol].copy()
    if revenue.empty:
        return pd.DataFrame(columns=columns)
    revenue["date"] = pd.to_datetime(revenue["月別"].astype(str).str.replace("/", "-", regex=False) + "-01", errors="coerce")
    revenue["finmind_revenue_m_twd"] = pd.to_numeric(revenue["合併營業收入_營收_億"], errors="coerce") * 100
    revenue = revenue.dropna(subset=["date", "finmind_revenue_m_twd"]).sort_values("date").drop_duplicates("date", keep="last")
    revenue["finmind_yoy_pct"] = revenue["finmind_revenue_m_twd"].replace(0, float("nan")).pct_change(12) * 100
    return revenue[columns].reset_index(drop=True)


def _read_local_eps_ratio_csv(path: str, symbol: str) -> pd.DataFrame:
    """Read quarterly EPS from the synchronized FinMind ratio export.

    FinMind's live financial-statement endpoint can expose only a recent
    history for some symbols. This local export is used only to warm up the
    EPS series, so the visible chart can calculate the earliest YoY bars
    without making additional API calls.
    """
    columns = ["period_end", "available_date", "eps"]
    if not path:
        return pd.DataFrame(columns=columns)
    try:
        header = pd.read_csv(path, nrows=0).columns
        eps_column = next((name for name in header if str(name).startswith("每股稅後盈餘 (元)")), None)
        if eps_column is None:
            return pd.DataFrame(columns=columns)
        raw = pd.read_csv(path, usecols=["stock_code", "季度", eps_column])
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=columns)
    stock = raw["stock_code"].astype(str).str.extract(r"(\d+)")[0].str.zfill(4)
    raw = raw[stock == symbol].copy()
    if raw.empty:
        return pd.DataFrame(columns=columns)
    quarter = raw["季度"].astype(str).str.extract(r"(\d{4})Q([1-4])")
    raw["year"] = pd.to_numeric(quarter[0], errors="coerce")
    raw["quarter"] = pd.to_numeric(quarter[1], errors="coerce")
    raw["eps"] = pd.to_numeric(raw[eps_column], errors="coerce")
    raw = raw.dropna(subset=["year", "quarter", "eps"])
    month_day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
    raw["period_end"] = [pd.Timestamp(int(year), *month_day[int(q)]) for year, q in zip(raw["year"], raw["quarter"])]
    raw["available_date"] = raw["period_end"].map(_availability_date)
    return raw[columns].drop_duplicates("period_end", keep="last").sort_values("period_end").reset_index(drop=True)


def _build_profit_metrics(financials: pd.DataFrame) -> pd.DataFrame:
    """Build no-look-ahead quarterly net-profit and margin metrics."""
    columns = [
        "period_end", "available_date", "revenue", "net_profit",
        "net_profit_yoy_pct", "net_margin_pct", "net_margin_yoy_pct",
    ]
    required = {"date", "type", "value"}
    if not required.issubset(financials.columns):
        return pd.DataFrame(columns=columns)
    rows = financials[financials["type"].isin(["Revenue", "IncomeAfterTaxes", "IncomeAfterTax"])].copy()
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows["period_end"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna(subset=["period_end", "value"]).drop_duplicates(["period_end", "type"], keep="last")
    pivot = rows.pivot(index="period_end", columns="type", values="value").sort_index()
    income_type = next((name for name in ("IncomeAfterTaxes", "IncomeAfterTax") if name in pivot.columns), None)
    if "Revenue" not in pivot.columns or income_type is None:
        return pd.DataFrame(columns=columns)
    # FinMind financial-statement amounts are reported in thousand TWD, while
    # the chart's revenue panel uses million TWD. Normalize both financial
    # amounts to million TWD so net profit is directly comparable with revenue.
    metrics = pd.DataFrame({"revenue": pivot["Revenue"] / 1_000, "net_profit": pivot[income_type] / 1_000})
    metrics["available_date"] = metrics.index.to_series().map(_availability_date)
    metrics["net_profit_yoy_pct"] = metrics["net_profit"].pct_change(4) * 100
    metrics["net_margin_pct"] = metrics["net_profit"].div(metrics["revenue"].replace(0, float("nan"))) * 100
    metrics["net_margin_yoy_pct"] = metrics["net_margin_pct"].diff(4)
    metrics["period_end"] = metrics.index
    return metrics.reset_index(drop=True)[columns]


def _build_daily_box(
    symbol: str, display_years: int, end_date: pd.Timestamp, window: int, forward_eps: pd.DataFrame, local_eps_csv: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    eps["eps"] = eps["value"]
    local_eps = _read_local_eps_ratio_csv(local_eps_csv, symbol)
    if not local_eps.empty:
        eps = pd.concat([eps[["period_end", "available_date", "eps"]], local_eps], ignore_index=True)
        eps = eps.drop_duplicates("period_end", keep="last").sort_values("period_end")
    eps["ttm_eps"] = eps["eps"].rolling(4).sum()
    eps = eps.dropna(subset=["ttm_eps"])[["available_date", "period_end", "eps", "ttm_eps"]]
    profit_metrics = _build_profit_metrics(financials)

    split_factors = _stock_dividend_factors(symbol, data_start, end_text)
    prices, eps = _adjust_for_stock_dividends(prices, eps, split_factors)

    prices = prices.reset_index()
    prices["date"] = prices["date"].astype("datetime64[ns]")
    eps["available_date"] = eps["available_date"].astype("datetime64[ns]")
    daily = pd.merge_asof(
        prices.sort_values("date"),
        eps.sort_values("available_date"),
        left_on="date", right_on="available_date", direction="backward",
    ).set_index("date")
    trailing_band = calc_pe_band_series(daily["close"], daily["ttm_eps"], period=window)
    daily = daily.join(trailing_band[["pe", "pe_mean", "pe_std", "price_m2", "price_m1", "price_mean", "price_p1", "price_p2"]])

    forward_cols = ["forward_eps", "forward_pe", "forward_pe_mean", "forward_pe_std"]
    forward_cols += [f"forward_price_{name}" for name in ("m2", "m1", "mean", "p1", "p2")]
    if forward_eps.empty:
        for col in forward_cols:
            daily[col] = float("nan")
    else:
        forward_eps = forward_eps.copy()
        forward_eps["as_of_date"] = pd.to_datetime(forward_eps["as_of_date"]).astype("datetime64[ns]")
        daily = pd.merge_asof(
            daily.reset_index().sort_values("date"),
            forward_eps[["as_of_date", "forward_eps"]].sort_values("as_of_date"),
            left_on="date", right_on="as_of_date", direction="backward",
        ).set_index("date")
        # A separate, lower min_periods than the trailing box's: Yahoo/FactSet
        # coverage often starts well within the display window (e.g. 81
        # trading days for a stock whose feed began in May), and reusing the
        # trailing box's 120-day floor left forward_pe_mean entirely NaN for
        # those names — hiding both the historical band and the future trend
        # ray even though the bottom panel already had forward-EPS points to
        # show. Forward EPS is an analyst estimate, not a noisy daily price
        # series, so a shorter warm-up is an acceptable trade for surfacing it
        # sooner; ±1σ will just be wider on a smaller sample early on.
        forward_band = calc_pe_band_series(daily["close"], daily["forward_eps"], period=window, min_periods=min(window, 20))
        daily["forward_pe"] = forward_band["pe"]
        daily["forward_pe_mean"] = forward_band["pe_mean"]
        daily["forward_pe_std"] = forward_band["pe_std"]
        for name in ("m2", "m1", "mean", "p1", "p2"):
            daily[f"forward_price_{name}"] = forward_band[f"price_{name}"]
    return daily, eps, profit_metrics


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
    forward_eps: pd.DataFrame, trades: pd.DataFrame, monthly_revenue: pd.DataFrame,
    profit_metrics: pd.DataFrame, output_dir: Path,
    yahoo_curve: pd.DataFrame = None, factset_curve: pd.DataFrame = None,
    revenue_label: str = "Monthly revenue", revenue_axis_label: str = "Revenue (M TWD)",
    growth_label: str = "Revenue YoY growth", profit_axis_label: str = "Net profit (NT$ million)",
) -> tuple[Path, Path, Path]:
    daily = daily.copy()
    daily["sma20"] = calc_ma(daily["close"], 20)
    daily["sma60"] = calc_ma(daily["close"], 60)
    daily["sma120"] = calc_ma(daily["close"], 120)
    daily["sma240"] = calc_ma(daily["close"], 240)
    bands = calc_bbands(daily["close"], period=20, k=2.0)
    daily["bband_mid"] = bands["mid"]
    daily["bband_upper2"] = bands["upper"]
    daily["bband_lower2"] = bands["lower"]
    daily["bband_upper1"] = daily["bband_mid"] + bands["std"]
    daily["bband_lower1"] = daily["bband_mid"] - bands["std"]
    display_start = daily.index.max() - pd.DateOffset(years=years)
    view = daily.loc[daily.index >= display_start].copy()
    if view.empty:
        raise RuntimeError(f"{symbol}: no data in the selected display window")

    # Prefer a supplied/installed CJK font so Traditional Chinese labels render
    # correctly in both PNG and SVG; DejaVu Sans remains the final fallback.
    cjk_font_path = os.environ.get("TW_CJK_FONT", "")
    cjk_family = ""
    if cjk_font_path and Path(cjk_font_path).is_file():
        font_manager.fontManager.addfont(cjk_font_path)
        cjk_family = font_manager.FontProperties(fname=cjk_font_path).get_name()
    has_cjk_name = any("\u3400" <= char <= "\u9fff" for char in str(name))
    if has_cjk_name and not cjk_family:
        raise RuntimeError(f"{symbol}: Traditional Chinese company name requires a valid TW_CJK_FONT; refusing missing-glyph fallback")
    preferred_fonts = [cjk_family] if cjk_family else []
    plt.rcParams["font.sans-serif"] = preferred_fonts + [
        "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Noto Sans CJK TC",
        "Noto Sans TC", "SimHei", "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["svg.fonttype"] = "path"

    # Precomputed once, up front, so both panels can use the same per-source
    # forward-EPS facts: the top panel projects a future trend ray from today
    # through each source's own future-year estimate, and the bottom panel
    # draws that source's full revision history. Splitting this out avoids
    # recomputing "the latest known estimate per target year" twice.
    cutoff = view.index.max()
    source_forward = {}
    for source_index, (source_label, curve, color, marker) in enumerate((
        ("Yahoo", yahoo_curve, "#d9782d", "D"),
        ("FactSet", factset_curve, "#1b7f9e", "s"),
    )):
        if curve is None or curve.empty:
            continue
        known = curve[curve["source_asof_date"] <= cutoff].sort_values("source_asof_date").copy()
        if known.empty:
            continue
        known = known.loc[known.groupby("target_year")["forward_eps"].shift().ne(known["forward_eps"])]
        year_latest = []  # (x, target_year, forward_eps) — one per year
        panel_curves = []  # release-date revisions plus an FY-end terminal node
        for target_year, revisions in known.groupby("target_year"):
            revisions = revisions.sort_values("source_asof_date")
            target_year = int(target_year)
            x = pd.Timestamp(year=target_year, month=12, day=31)
            year_latest.append((x, target_year, revisions["forward_eps"].iloc[-1]))
            panel_revisions = revisions[revisions["source_asof_date"] <= x].copy()
            if panel_revisions.empty:
                continue
            panel_revisions = panel_revisions.sort_values("source_asof_date")
            # Panel 4 uses each target FY as its own visual timeline. Keep
            # the release month/day and EPS revision value, but move the
            # release node into target_year (e.g. 2026-09-04 -> 2027-09-04
            # for FY2027E). This prevents FY2027E/FY2028E revisions from
            # collapsing into the same 2026 slice while preserving their
            # within-year revision sequence.
            curve_dates = [
                pd.Timestamp(
                    year=target_year,
                    month=release_date.month,
                    day=min(release_date.day, pd.Timestamp(year=target_year, month=release_date.month, day=1).days_in_month),
                )
                for release_date in panel_revisions["source_asof_date"]
            ]
            curve_values = [float(value) for value in panel_revisions["forward_eps"]]
            terminal_added = curve_dates[-1] < x
            if terminal_added:
                curve_dates.append(x)
                curve_values.append(curve_values[-1])
            panel_curves.append({
                "target_year": target_year,
                "dates": curve_dates,
                "values": curve_values,
                "terminal_added": terminal_added,
            })
        year_latest.sort(key=lambda item: item[0])
        source_forward[source_label] = {
            "color": color, "marker": marker, "known": known,
            "year_latest": year_latest, "panel_curves": panel_curves,
            "latest_report_date": known["source_asof_date"].max().date(),
        }

    # sharex=True so the two panels line up on one timeline: a forward-EPS
    # point's x-position in the bottom panel is directly comparable to the
    # top panel's price/date grid, not just internally consistent within its
    # own panel. When a forward curve's target year runs past the price
    # history (e.g. FactSet's FY2028E), both panels' x-range is explicitly
    # extended together below, rather than left to independent autoscale.
    figure, (axis, technical_axis, pe_axis, eps_axis, reported_eps_axis, eps_yoy_axis, revenue_axis, growth_axis, net_profit_axis, net_profit_yoy_axis, net_margin_axis, net_margin_yoy_axis) = plt.subplots(
        12, 1, figsize=(16, 34.0), sharex=True,
        gridspec_kw={"height_ratios": [3, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], "hspace": 0.1},
    )
    label = f"{symbol} {name}" if name else symbol
    figure.suptitle(f"{label} | {years}-year price, valuation box, EPS, revenue & profit trend", x=0.125, ha="left", y=0.975, fontsize=16, fontweight="bold")

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

    # Future trend rays: today's forward-PE multiple (mean and ±1σ, held
    # constant) applied to each source's OWN future-year EPS estimate — not
    # a new multiple assumption, just "what would price be at today's
    # multiple once this year's consensus EPS is realized." One ray per
    # source (colored to match its bottom-panel markers), since Yahoo and
    # FactSet routinely imply different future prices from the same multiple.
    last_row = view.iloc[-1]
    if has_forward and pd.notna(last_row["forward_pe_mean"]):
        today_x = view.index[-1]
        mean_pe = last_row["forward_pe_mean"]
        std_pe = last_row["forward_pe_std"] if pd.notna(last_row["forward_pe_std"]) else 0.0
        for source_label, info in source_forward.items():
            future = [item for item in info["year_latest"] if item[0] > today_x]
            if not future:
                continue
            xs = [today_x] + [item[0] for item in future]
            mean_ys = [last_row["forward_price_mean"]] + [mean_pe * eps for _, _, eps in future]
            axis.plot(xs, mean_ys, color=info["color"], lw=1.1, ls="--", alpha=0.85, zorder=3)
            for sigma, base_field in ((-1, "forward_price_m1"), (1, "forward_price_p1")):
                band_ys = [last_row[base_field]] + [(mean_pe + sigma * std_pe) * eps for _, _, eps in future]
                axis.plot(xs, band_ys, color=info["color"], lw=0.7, ls=":", alpha=0.7, zorder=2)

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

    technical_axis.plot(view.index, view["close"], color="#17365d", lw=1.4, label="Close (same as panel 1)")
    for field, color, label_text in (("sma20", "#d62728", "SMA20"), ("sma60", "#ff7f0e", "SMA60"), ("sma120", "#2ca02c", "SMA120"), ("sma240", "#9467bd", "SMA240")):
        technical_axis.plot(view.index, view[field], color=color, lw=1.5 if field == "sma20" else 0.9, label=label_text, zorder=5 if field == "sma20" else 4)
    technical_axis.fill_between(view.index, view["bband_lower2"], view["bband_upper2"], color="#d9d9d9", alpha=0.25, label="Bollinger ±2σ")
    technical_axis.fill_between(view.index, view["bband_lower1"], view["bband_upper1"], color="#9ecae1", alpha=0.28, label="Bollinger ±1σ")
    technical_axis.plot(view.index, view["bband_mid"], color="#3182bd", lw=1.0, ls="--", label="Bollinger middle (SMA20)")
    technical_axis.plot(view.index, view["bband_upper1"], color="#3182bd", lw=0.7, ls=":")
    technical_axis.plot(view.index, view["bband_lower1"], color="#3182bd", lw=0.7, ls=":")
    technical_axis.plot(view.index, view["bband_upper2"], color="#756bb1", lw=0.7, ls=":")
    technical_axis.plot(view.index, view["bband_lower2"], color="#756bb1", lw=0.7, ls=":")
    technical_axis.set_ylabel("Price")
    technical_axis.grid(axis="y", color="#d9e2f3", lw=0.7)
    technical_axis.legend(loc="upper left", ncol=4, fontsize=7, frameon=False)

    pe_axis.plot(view.index, view["pe"], color="#6a329f", lw=0.8, alpha=0.65, label="Trailing P/E")
    pe_axis.plot(view.index, view["pe_mean"], color="#666666", lw=1.2, ls="--", label="P/E mean")
    if has_forward:
        pe_axis.plot(view.index, view["forward_pe"], color="#d9782d", lw=0.8, alpha=0.65, label="Forward P/E")
        pe_axis.plot(view.index, view["forward_pe_mean"], color="#d9782d", lw=1.1, ls="--", label="Forward P/E mean")
    pe_axis.set_ylabel("P/E")
    pe_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    pe_axis.legend(loc="upper left", ncol=4, frameon=False, fontsize=7)
    pe_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    pe_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    pe_axis.xaxis.remove_overlapping_locs = False
    pe_axis.xaxis.set_minor_locator(mdates.MonthLocator())
    pe_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)

    eps_view = eps[eps["available_date"] >= display_start]
    # step() only draws between given x-values, so without this the line just
    # stops dead at the last node instead of showing that its TTM figure is
    # still the operative one all the way to today (it holds until the next
    # quarter's statutory deadline actually updates it).
    line_x = pd.concat([eps_view["available_date"], pd.Series([view.index.max()])], ignore_index=True)
    line_y = pd.concat([eps_view["ttm_eps"], pd.Series([eps_view["ttm_eps"].iloc[-1]])], ignore_index=True)
    eps_axis.step(line_x, line_y, where="post", color="#6a329f", lw=2, label="Trailing TTM EPS")
    eps_axis.scatter(eps_view["available_date"], eps_view["ttm_eps"], color="#6a329f", s=26, zorder=3)

    # Yahoo and FactSet forward-EPS curves are plotted separately, unmerged.
    # Each FY segment preserves the month/day of every estimate revision but
    # places it inside the target FY (e.g. 2026-09-04 -> 2027-09-04 for
    # FY2027E), then carries the last known value to that FY's 12/31 terminal
    # node. Released estimates are circles; the FY-end terminal is a triangle
    # and is the only node carrying the FY label. This makes both the estimate
    # revision history and the eventual target-year value easy to read.
    forward_points = []  # (x, y, source_label, target_year, color, source_index)
    terminal_points = []  # (x, y, source_label, target_year, color, source_index)
    line_styles = {2025: ":", 2026: ":", 2027: ":", 2028: ":"}
    for source_index, source_label in enumerate(("Yahoo", "FactSet")):
        info = source_forward.get(source_label)
        if info is None:
            continue
        color, year_latest, panel_curves = info["color"], info["year_latest"], info["panel_curves"]
        for curve_index, curve in enumerate(sorted(panel_curves, key=lambda item: item["target_year"])):
            target_year = curve["target_year"]
            curve_dates, curve_values = curve["dates"], curve["values"]
            eps_axis.plot(
                curve_dates, curve_values, color=color, lw=1.5,
                ls=line_styles.get(target_year, "-"), alpha=0.9,
                zorder=3, label=f"{source_label} consensus" if curve_index == 0 else None,
            )
            released_end = len(curve_dates) - 1 if curve["terminal_added"] else len(curve_dates)
            if released_end:
                eps_axis.scatter(
                    curve_dates[:released_end], curve_values[:released_end],
                    color=color, marker="o", s=28, alpha=0.92, zorder=4,
                )
            if curve["terminal_added"]:
                eps_axis.scatter(
                    [curve_dates[-1]], [curve_values[-1]], color=color,
                    marker="^", s=62, zorder=5,
                )
            terminal_points.append((curve_dates[-1], curve_values[-1], source_label, target_year, color, source_index))
        for x, target_year, forward_eps in year_latest:
            forward_points.append((x, forward_eps, source_label, target_year, color, source_index))

    any_forward_curve = bool(forward_points or terminal_points)
    # Shared axis: extend both panels together to cover the furthest-out
    # forward-curve point, rather than letting each panel's own autoscale
    # fight over the (linked) shared x-limits.
    range_points = forward_points + terminal_points
    range_end = max([view.index.max()] + [p[0] for p in range_points])
    axis.set_xlim(view.index.min(), range_end)
    eps_axis.margins(y=0.25)
    if any_forward_curve:
        all_y = pd.concat([eps_view["ttm_eps"], pd.Series([p[1] for p in range_points])])
        y_span = max(all_y.max() - all_y.min(), 1e-9)
        for x, y, source_label, target_year, color, source_index in terminal_points:
            # Same-FY Yahoo/FactSet terminal values can be very close. Keep
            # both labels exactly on the terminal FY date and separate them
            # vertically with a leader line; horizontal offsets falsely imply
            # that one source belongs to the next fiscal year.
            text_y = y + (0.08 + 0.11 * source_index) * y_span
            eps_axis.annotate(
                f"{source_label} FY{target_year}E {y:.1f}", xy=(x, y),
                xytext=(x, text_y), textcoords="data", fontsize=7.5,
                color=color, ha="center", va="bottom",
                arrowprops={"arrowstyle": "-", "color": color, "lw": 0.6},
            )
        eps_axis.legend(loc="upper left", fontsize=8, frameon=False)
    eps_axis.axvline(cutoff, color="#555555", lw=0.8, ls="--", alpha=0.7, zorder=1)
    eps_axis.text(cutoff, 0.98, "Today", transform=eps_axis.get_xaxis_transform(), ha="right", va="top", fontsize=7, color="#555555")
    eps_axis.set_title("Trailing TTM EPS vs Yahoo / FactSet consensus", loc="left", fontsize=10, pad=4)
    eps_axis.set_ylabel("EPS")
    eps_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    eps_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    eps_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    eps_axis.xaxis.remove_overlapping_locs = False
    eps_axis.xaxis.set_minor_locator(mdates.MonthLocator())
    eps_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)
    # Calculate YoY against the complete available EPS history before
    # restricting the chart to its visible window. Calculating pct_change(4)
    # after this filter incorrectly leaves the first four visible quarters
    # blank even when their year-earlier EPS observations were fetched during
    # the warm-up period (e.g. 2356's 2023-2024 bars in a 3-year chart).
    eps_reported_all = pd.to_numeric(
        eps.get("eps", eps.get("value", pd.Series(index=eps.index, dtype=float))),
        errors="coerce",
    )
    eps_with_yoy = eps.copy()
    eps_with_yoy["eps_yoy_pct"] = eps_reported_all.pct_change(4) * 100
    eps_reported_view = eps_with_yoy[eps_with_yoy["available_date"] >= display_start].copy()
    eps_reported = pd.to_numeric(
        eps_reported_view.get("eps", eps_reported_view.get("value", pd.Series(index=eps_reported_view.index, dtype=float))),
        errors="coerce",
    )
    eps_reported_yoy = pd.to_numeric(eps_reported_view["eps_yoy_pct"], errors="coerce")
    valid_eps = eps_reported.notna()
    if valid_eps.any():
        reported_eps_axis.bar(eps_reported_view.loc[valid_eps, "available_date"], eps_reported.loc[valid_eps], width=45, color="#8064a2", alpha=0.82, label="Reported quarterly EPS")
        reported_eps_axis.legend(loc="upper left", frameon=False, fontsize=8)
    else:
        reported_eps_axis.text(0.5, 0.5, "Reported EPS data unavailable", transform=reported_eps_axis.transAxes, ha="center", va="center")
    reported_eps_axis.set_ylabel("EPS")
    reported_eps_axis.grid(axis="y", color="#e6e6e6", lw=0.7)

    valid_eps_yoy = eps_reported_yoy.notna()
    if valid_eps_yoy.any():
        eps_yoy_axis.bar(
            eps_reported_view.loc[valid_eps_yoy, "available_date"], eps_reported_yoy.loc[valid_eps_yoy], width=45,
            color=["#c00000" if value > 0 else "#70ad47" for value in eps_reported_yoy.loc[valid_eps_yoy]],
            alpha=0.82, label="EPS YoY growth",
        )
        eps_yoy_axis.legend(loc="upper left", frameon=False, fontsize=8)
    else:
        eps_yoy_axis.text(0.5, 0.5, "EPS YoY data unavailable", transform=eps_yoy_axis.transAxes, ha="center", va="center")
    eps_yoy_axis.axhline(0, color="#999999", lw=0.7)
    eps_yoy_axis.set_ylabel("YoY (%)")
    eps_yoy_axis.grid(axis="y", color="#e6e6e6", lw=0.7)

    # Keep every panel aligned to the same monthly vertical grid, including
    # the two reported-EPS bar panels whose x-axis labels are hidden by the
    # shared axis. This makes a quarter's bars line up with the revenue,
    # profit, and valuation panels instead of leaving panels 4-5 gridless.
    all_panels = (
        axis, technical_axis, pe_axis, eps_axis, reported_eps_axis, eps_yoy_axis,
        revenue_axis, growth_axis, net_profit_axis, net_profit_yoy_axis,
        net_margin_axis, net_margin_yoy_axis,
    )
    for panel_axis in all_panels:
        panel_axis.xaxis.remove_overlapping_locs = False
        panel_axis.xaxis.set_minor_locator(mdates.MonthLocator())
        panel_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)

    revenue_view = monthly_revenue[monthly_revenue["date"] >= display_start].copy()
    revenue_series = revenue_view.get("revenue_m_twd", pd.Series(index=revenue_view.index, dtype=float))
    yoy_series = revenue_view.get("revenue_yoy_pct", pd.Series(index=revenue_view.index, dtype=float))
    # Bar width scales inversely with the display window: the same 18-day
    # width that reads fine when 2 years of bars fit across the figure
    # starts overlapping once --years stretches the same width to cover
    # 5 years of months, so scale it down proportionally.
    bar_width = 18 * 2 / years
    if revenue_series.notna().any():
        revenue_axis.bar(revenue_view["date"], revenue_series, width=bar_width, color="#5b9bd5", alpha=0.78, label=revenue_label)
        revenue_axis.set_ylabel(revenue_axis_label)
        revenue_axis.legend(loc="upper left", frameon=False, fontsize=8)
    else:
        revenue_axis.text(0.5, 0.5, "Monthly revenue data unavailable", transform=revenue_axis.transAxes, ha="center", va="center")
    revenue_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    revenue_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    revenue_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    revenue_axis.xaxis.remove_overlapping_locs = False
    revenue_axis.xaxis.set_minor_locator(mdates.MonthLocator())
    revenue_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)
    if yoy_series.notna().any():
        growth_axis.bar(revenue_view["date"], yoy_series, width=bar_width, color=["#c00000" if value > 0 else "#70ad47" for value in yoy_series], alpha=0.82, label=growth_label)
        growth_axis.axhline(0, color="#999999", lw=0.7)
        growth_axis.legend(loc="upper left", frameon=False, fontsize=8)
    else:
        growth_axis.text(0.5, 0.5, "Revenue YoY data unavailable", transform=growth_axis.transAxes, ha="center", va="center")
    growth_axis.set_ylabel("YoY (%)")
    growth_axis.set_xlabel("Month")
    growth_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
    growth_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
    growth_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    growth_axis.xaxis.remove_overlapping_locs = False
    growth_axis.xaxis.set_minor_locator(mdates.MonthLocator())
    growth_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)

    profit_view = profit_metrics[profit_metrics["available_date"] >= display_start].copy()
    metric_specs = (
        (net_profit_axis, "net_profit", "Net profit", profit_axis_label, "#4472c4", "bar"),
        (net_profit_yoy_axis, "net_profit_yoy_pct", "Net profit YoY", "YoY (%)", "#70ad47", "bar"),
        (net_margin_axis, "net_margin_pct", "Net profit margin", "Margin (%)", "#7030a0", "bar"),
        (net_margin_yoy_axis, "net_margin_yoy_pct", "Margin YoY change", "Δ margin (pp)", "#ed7d31", "bar"),
    )
    for metric_axis, field, label_text, ylabel, color, kind in metric_specs:
        series = profit_view.get(field, pd.Series(index=profit_view.index, dtype=float))
        valid = series.notna()
        if valid.any():
            if kind == "bar":
                colors = (
                    ["#c00000" if value > 0 else "#70ad47" for value in series.loc[valid]]
                    if "yoy" in field
                    else color
                )
                metric_axis.bar(
                    profit_view.loc[valid, "available_date"], series.loc[valid], width=45,
                    color=colors, alpha=0.82, label=label_text,
                )
            else:
                metric_axis.plot(profit_view.loc[valid, "available_date"], series.loc[valid], color=color, lw=1.4, marker="o", ms=3, label=label_text)
            metric_axis.legend(loc="upper left", frameon=False, fontsize=7)
        else:
            metric_axis.text(0.5, 0.5, f"{label_text} data unavailable", transform=metric_axis.transAxes, ha="center", va="center")
        metric_axis.set_ylabel(ylabel)
        metric_axis.grid(axis="y", color="#e6e6e6", lw=0.7)
        metric_axis.xaxis.set_major_locator(mdates.MonthLocator(interval=max(3, years * 2)))
        metric_axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        metric_axis.xaxis.remove_overlapping_locs = False
        metric_axis.xaxis.set_minor_locator(mdates.MonthLocator())
        metric_axis.grid(which="minor", axis="x", color="#c9c9c9", lw=0.5)

    # The shared x-axis (line ~625) is deliberately stretched past the price
    # history to fit the furthest forward-EPS target year (e.g. FactSet
    # FY2028E) so the top price panel's trend rays and the EPS panel's
    # forward markers have room to plot. Monthly revenue never has data out
    # there, so without this shading revenue_axis/growth_axis were left with
    # a multi-year dead blank stretch on their right edge with no visual
    # explanation for why. Shade that stretch and label it once, rather than
    # leaving readers to guess whether data is missing or just flat/zero.
    last_revenue_date = view.index.max()
    if range_end > last_revenue_date:
        for shaded_axis in (revenue_axis, growth_axis):
            shaded_axis.axvspan(last_revenue_date, range_end, color="#ececec", alpha=0.7, zorder=0)
        projection_mid = last_revenue_date + (range_end - last_revenue_date) / 2
        revenue_axis.annotate(
            "Forward-EPS projection window — no revenue data yet", xy=(projection_mid, 0.92),
            xycoords=("data", "axes fraction"), ha="center", va="top", fontsize=7.5, color="#888888",
        )

    updated_label = _updated_label()
    figure.text(
        0.5, 0.004, updated_label, ha="center", va="bottom",
        fontsize=8, color="#666666", transform=figure.transFigure,
    )
    figure.subplots_adjust(top=0.93, bottom=0.02)

    output_dir.mkdir(parents=True, exist_ok=True)
    png_path = output_dir / f"{symbol}_dynamic_valuation_box_{years}y.png"
    csv_path = output_dir / f"{symbol}_dynamic_valuation_box_{years}y.csv"
    svg_path = output_dir / f"{symbol}_dynamic_valuation_box_{years}y.svg"
    figure.savefig(
        png_path, dpi=180, bbox_inches="tight",
        metadata={"ChartVersion": CHART_VERSION, "ChartMetadata": CHART_METADATA, "Updated": updated_label},
    )
    figure.savefig(svg_path, format="svg", bbox_inches="tight")
    # Version the embedded Traditional Chinese font so old SVGs can be
    # identified and regenerated incrementally without forcing every ticker.
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_comment = CHART_METADATA + "; " + updated_label
    if CHART_METADATA not in svg_text:
        svg_text = svg_text.replace("?>\n", "?>\n<!-- " + svg_comment + " -->\n", 1)
        svg_path.write_text(svg_text, encoding="utf-8")
    csv_data = view.reset_index().to_csv(index=False, float_format="%.6f")
    csv_path.write_text("# " + CHART_METADATA + "; " + updated_label + "\n" + csv_data, encoding="utf-8")
    plt.close(figure)
    return png_path, svg_path, csv_path


def _discover_forward_feed(filename: str) -> str | None:
    """Find the standard sibling-repo forward-EPS feed when no path is given."""
    # Yahoo Finance and FactSet are upstream feeds, but this renderer consumes
    # only the canonical copy synchronized into biztrends.TW. That preserves
    # the intended dependency direction: Yahoo.Finance -> biztrends.TW ->
    # My-TW-Coverage, and prevents a local direct-upstream path from silently
    # bypassing the integration repository.
    candidates = [
        Path.cwd().parent / "biztrends.TW" / "data" / "Yahoo.Finance" / filename,
        Path.cwd().parent / "biztrends.TW" / "data" / "GoogleSearch.Factset" / filename,
        Path("/app/projects/biztrends.TW/data/Yahoo.Finance") / filename,
        Path("/app/projects/biztrends.TW/data/GoogleSearch.Factset") / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True, help="Taiwan stock codes, e.g. 3045 2412")
    parser.add_argument("--company-name", default="", help="Company name for the SVG title; avoids an extra FinMind info request")
    parser.add_argument("--years", type=int, choices=(2, 3, 4, 5), default=3, help="Visible price-history years")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Analysis cutoff date, YYYY-MM-DD")
    parser.add_argument("--window", type=int, default=120, help="Rolling PE observations (default: 120, minimum: 120)")
    parser.add_argument("--trades-csv", help="Optional CSV: symbol,date,side,price,lots; supports stock_id/qty aliases and 買進/賣出")
    parser.add_argument("--forward-eps-csv", help="Optional CSV, this skill's own shape: symbol,as_of_date,forward_eps (as_of_date = when the estimate was published, not the target fiscal period)")
    parser.add_argument("--yahoo-consensus-csv", help="Optional CSV in Yahoo Finance's native shape (stock_code, forecast_asof_date, earnings_1y_avg, ...), e.g. a sibling Yahoo.Finance repo's data/reports/raw_yahoo_finance_consensus_daily.csv")
    parser.add_argument("--factset-report-csv", help="Optional CSV in FactSet's native shape (代號/股票代號, MD日期, <year>EPS平均值 columns), e.g. a sibling repo's data/reports/raw_factset_detailed_report.csv")
    parser.add_argument("--finmind-revenue-csv", help="Optional synchronized FinMind monthly-revenue CSV used when live FinMind data is unavailable or incomplete")
    parser.add_argument("--finmind-financial-ratio-csv", help="Optional synchronized FinMind quarterly-ratio CSV used to warm up EPS history")
    parser.add_argument("--analyzer-revenue-csv", default="../Python-Actions.GoodInfo.Analyzer/data/stage1_raw/raw_revenue.csv", help="Optional GoodInfo Analyzer monthly revenue CSV")
    parser.add_argument("--output-dir", default="output/dynamic_valuation_box")
    parser.add_argument("--require-forward-eps", action="store_true", help="Fail if no forward-EPS rows are available for a requested symbol")
    args = parser.parse_args()
    if args.yahoo_consensus_csv is None:
        args.yahoo_consensus_csv = _discover_forward_feed("raw_yahoo_finance_consensus_daily.csv")
    if args.factset_report_csv is None:
        args.factset_report_csv = _discover_forward_feed("raw_factset_detailed_report.csv")
    if args.window < 120:
        parser.error("--window must be at least 120 observations")

    # Fail fast with an actionable message instead of letting the first FinMind
    # call fifteen symbols in surface a bare "HTTP Error 402: Payment Required"
    # deep in a traceback. Anonymous access is still allowed to proceed — it is
    # a small but real quota, not zero — this is a warning, not a hard exit.
    if not _finmind_tokens():
        print(
            "[render_dynamic_valuation_box] Warning: no FinMind token found in the "
            f"environment (checked {', '.join(TOKEN_ENV_NAMES)}). Proceeding with "
            "anonymous FinMind access, whose daily quota is small and may fail with "
            "HTTP 402 partway through this run. Set one of those env vars (directly "
            "or via a .env file) to use a real quota.",
            file=sys.stderr,
        )

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
    missing_forward = [symbol for symbol in symbols if forward_eps_all[forward_eps_all["symbol"] == symbol].empty]
    if missing_forward:
        message = "No forward EPS rows found for: " + ", ".join(missing_forward)
        if args.require_forward_eps:
            raise RuntimeError(message + ". Supply --forward-eps-csv, --yahoo-consensus-csv, or --factset-report-csv.")
        print(f"[render_dynamic_valuation_box] Warning: {message}; trailing-only valuation will be rendered for those symbols.", file=sys.stderr)
    # For the bottom-panel display, Yahoo and FactSet are kept unmerged (see
    # _plot): each source's own target-fiscal-year curve, not pooled into the
    # single per-day series above.
    yahoo_curve_all = _yahoo_forward_curve(args.yahoo_consensus_csv, symbols)
    factset_curve_all = _factset_forward_curve(args.factset_report_csv, symbols)
    output_dir = Path(args.output_dir)
    for symbol in symbols:
        # Bulk runs already have the company name in the surrounding page data;
        # avoid an extra FinMind TaiwanStockInfo call per symbol here.
        name = args.company_name.strip()
        forward_eps = forward_eps_all[forward_eps_all["symbol"] == symbol]
        daily, eps, profit_metrics = _build_daily_box(symbol, args.years, end_date, args.window, forward_eps, args.finmind_financial_ratio_csv)
        revenue_start = (end_date - pd.DateOffset(years=args.years + 1)).strftime("%Y-%m-%d")
        local_finmind_revenue = _read_finmind_revenue_csv(args.finmind_revenue_csv, symbol)
        if not local_finmind_revenue.empty:
            # Prefer the synchronized local feed so bulk rendering does not
            # spend a live request on data already present on disk.
            monthly_revenue = local_finmind_revenue
        else:
            try:
                monthly_revenue = _build_monthly_revenue(symbol, revenue_start, end_date.strftime("%Y-%m-%d"))
            except RuntimeError:
                if not args.finmind_revenue_csv:
                    raise
                monthly_revenue = pd.DataFrame(columns=["date", "finmind_revenue_m_twd", "finmind_yoy_pct"])
        analyzer_revenue = _read_analyzer_revenue(args.analyzer_revenue_csv, symbol)
        monthly_revenue = monthly_revenue.merge(analyzer_revenue, on="date", how="outer").sort_values("date")
        monthly_revenue["revenue_m_twd"] = monthly_revenue["analyzer_revenue_m_twd"].combine_first(monthly_revenue["finmind_revenue_m_twd"])
        monthly_revenue["revenue_yoy_pct"] = monthly_revenue["revenue_m_twd"].replace(0, float("nan")).pct_change(12) * 100
        yahoo_curve = yahoo_curve_all[yahoo_curve_all["symbol"] == symbol]
        factset_curve = factset_curve_all[factset_curve_all["symbol"] == symbol]
        png_path, svg_path, csv_path = _plot(
            symbol, name, args.years, daily, eps, forward_eps, trades, monthly_revenue,
            profit_metrics, output_dir, yahoo_curve, factset_curve,
        )
        print(f"{symbol}: {svg_path}")
        print(f"{symbol}: {png_path}")
        print(f"{symbol}: {csv_path}")


if __name__ == "__main__":
    main()
