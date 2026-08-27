"""
fiscal_quarter.py — Deterministic US fiscal-year/quarter resolution.

Single source of truth for two tables that were previously duplicated (and
drifted) across skill-company-investorconference-ingest's ingest.py,
skill-stock-investorevent-fetch's fetch_upcoming_earnings.py, and
ConceptStocks' update_concept_metadata.py:

  - KNOWN_US_FISCAL_YEAR_START_MONTH: tickers whose fiscal year does not
    start in January, so their FY label cannot be derived by matching the
    calendar year directly (e.g. NVDA's FY starts in February, so an
    earnings call announced in August 2026 is "Q2 FY2027", not "FY2026 Q4").
  - KNOWN_US_CALENDAR_YEAR_EARNINGS: tickers whose fiscal year IS the
    calendar year, kept here because upstream "upcoming report" metadata
    (ConceptStocks' LLM-guessed 即將發布 field) is frequently off by a
    quarter for these too.

resolve_fiscal_quarter() derives the fiscal quarter from an announcement date
by composing a coarse 3-month calendar-quarter bucket with the FY-start-month
adjustment — see its docstring for why a per-ticker "announcement month ->
quarter" lookup table was tried and rejected (it breaks on real boundary
cases, e.g. Dell's Q2 FY2027 call landing on 2026-09-01 while NVDA's own
Q2 FY2027 call landed 2026-08-26).

No external dependencies (no yfinance, no requests, no filesystem access) —
pure date arithmetic only, so any consumer can import this module without
pulling in unrelated fetch/scrape logic or watchlist-file prerequisites.
"""
from __future__ import annotations

# Fiscal year start month for US stocks whose fiscal year != calendar year.
# e.g. QCOM fiscal year starts October -> FY2026 Q1 = Oct-Dec 2025 (calendar Q4 2025)
KNOWN_US_FISCAL_YEAR_START_MONTH = {
    "QCOM": 10,   # October
    "AAPL": 10,   # October
    "MSFT": 7,    # July
    "NVDA": 2,    # February (FY starts Feb 1)
    "DELL": 2,    # February (FY starts Feb 1)
}

# US stocks whose fiscal year equals the calendar year, but whose upstream
# "upcoming report" metadata is unreliable — announcement-date-derived
# calendar quarter should override it.
KNOWN_US_CALENDAR_YEAR_EARNINGS = {"AMD", "AMZN", "GOOGL", "INTC", "META", "TSM"}


def normalize_ticker(symbol: str) -> str:
    return symbol.replace(".TW", "").replace(".TWO", "").upper()


def calendar_to_fiscal(ticker: str, cal_year, cal_q):
    """Return (fy_year, fy_q) strings for a US stock given its calendar year/quarter.
    Returns (None, None) if no fiscal year mapping is defined for the ticker."""
    start_month = KNOWN_US_FISCAL_YEAR_START_MONTH.get(normalize_ticker(ticker))
    if start_month is None:
        return None, None
    fy_start_cal_q = (start_month - 1) // 3 + 1  # e.g. Oct(10) -> Q4
    cq = int(cal_q)
    cy = int(cal_year)
    fy_q = (cq - fy_start_cal_q) % 4 + 1
    fy_year = cy + 1 if cq >= fy_start_cal_q else cy
    return str(fy_year), str(fy_q)


def expected_us_calendar_earnings_quarter(date_str: str):
    """依財報公告日期反推日曆季度（美股慣例：報告月份即所屬季度）。date_str: 'YYYY-MM-DD'."""
    y, mo = int(date_str[:4]), int(date_str[5:7])
    if 1 <= mo <= 3:
        return str(y - 1), "4"
    if 4 <= mo <= 6:
        return str(y), "1"
    if 7 <= mo <= 9:
        return str(y), "2"
    return str(y), "3"


def resolve_fiscal_quarter(ticker: str, date_str: str) -> dict:
    """Resolve fiscal year/quarter for a US earnings ANNOUNCEMENT date.

    Returns {"year": str|None, "quarter": str|None, "confidence": str, "label": str|None}.

    For KNOWN_US_FISCAL_YEAR_START_MONTH tickers, this composes
    expected_us_calendar_earnings_quarter() (a coarse, 3-month-bucket
    calendar-quarter estimate — the same heuristic already used elsewhere
    for calendar-year tickers) with calendar_to_fiscal() (the FY-start-month
    adjustment). This composition was deliberately chosen over a per-ticker
    "announcement month -> quarter" lookup table: a month-exact table breaks
    whenever a company's actual announcement date straddles a calendar-month
    boundary in a given year (verified in practice — Dell's Q2 FY2027 call
    landed on 2026-09-01, one day into September, while NVDA's own Q2 FY2027
    call landed 2026-08-26; a month-keyed table would treat these as
    different quarters even though they're the same one). The 3-month-bucket
    heuristic is coarse enough to absorb that wobble and has been verified
    against every real data point available in this repo across all 5 known
    tickers (NVDA, DELL, QCOM, AAPL, MSFT) — see fiscal_quarter_test.py.

    confidence:
      - "fiscal_offset": ticker in KNOWN_US_FISCAL_YEAR_START_MONTH;
        label is 'FY{year} Q{quarter}'.
      - "calendar_year": ticker in KNOWN_US_CALENDAR_YEAR_EARNINGS;
        label is '{year} Q{quarter}' (deliberately NOT FY-prefixed — these
        tickers' fiscal year IS the calendar year).
      - "unknown": no mapping for this ticker; caller must fall back to
        another source (e.g. upstream metadata) and should not treat this
        result as authoritative.
    """
    t = normalize_ticker(ticker)

    if t in KNOWN_US_FISCAL_YEAR_START_MONTH:
        cal_year, cal_q = expected_us_calendar_earnings_quarter(date_str)
        fy_year, fy_q = calendar_to_fiscal(t, cal_year, cal_q)
        return {
            "year": fy_year, "quarter": fy_q, "confidence": "fiscal_offset",
            "label": f"FY{fy_year} Q{fy_q}",
        }

    if t in KNOWN_US_CALENDAR_YEAR_EARNINGS:
        cy, cq = expected_us_calendar_earnings_quarter(date_str)
        return {
            "year": cy, "quarter": cq, "confidence": "calendar_year",
            "label": f"{cy} Q{cq}",
        }

    return {"year": None, "quarter": None, "confidence": "unknown", "label": None}
