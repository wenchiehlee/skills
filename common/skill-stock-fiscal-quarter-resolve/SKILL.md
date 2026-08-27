---
name: skill-stock-fiscal-quarter-resolve
description: >-
  Deterministic, dependency-free US fiscal-year/quarter resolution shared by
  skill-company-investorconference-ingest, skill-stock-investorevent-fetch, and
  ConceptStocks' update_concept_metadata.py. Given a ticker and an earnings
  announcement date, returns the fiscal year/quarter with a confidence level,
  instead of each consumer guessing or duplicating its own lookup table. Use
  when a US ticker's fiscal-quarter label looks stale or wrong (e.g. NVDA/DELL
  fiscal-year-offset mislabeling, or AMD/GOOGL calendar-year metadata drift).
---

# Fiscal Quarter Resolve Skill

## Role

Single source of truth for two small lookup tables that were previously
duplicated — and drifted — across three places:

| Consumer | Symptom before this skill |
|---|---|
| `skill-company-investorconference-ingest`'s `ingest.py` | Had its own `KNOWN_US_FISCAL_YEAR_START_MONTH` / `calendar_to_fiscal()`, correct but not reused elsewhere. |
| `skill-stock-investorevent-fetch`'s `fetch_upcoming_earnings.py` | Had its own copy of `KNOWN_US_CALENDAR_YEAR_EARNINGS` and a date-reversal function, but blindly trusted ConceptStocks' `即將發布` metadata for fiscal-offset tickers (NVDA, DELL, QCOM, AAPL, MSFT) — which caused NVDA's Q2 FY2027 earnings call to be mislabeled "FY2026 Q4" in `raw_event_upcoming_earnings.csv`. |
| `ConceptStocks`'s `update_concept_metadata.py` | `即將發布` / `最新財報` are LLM-guessed once at first creation and never re-validated — no date arithmetic at all, so the label silently goes stale as quarters pass. |

This skill has **no external dependencies** (no yfinance, no requests, no
filesystem I/O) — it is pure date arithmetic on a ticker + an already-known
announcement date string. That's a deliberate design choice: a consumer that
only needs "what fiscal quarter does this announcement date fall in" should
not have to pull in MOPS scraping, yfinance calls, or watchlist CSV
prerequisites the way `skill-stock-investorevent-fetch` does.

## API

```python
from fiscal_quarter import (
    KNOWN_US_FISCAL_YEAR_START_MONTH,
    KNOWN_US_CALENDAR_YEAR_EARNINGS,
    calendar_to_fiscal,
    expected_us_calendar_earnings_quarter,
    resolve_fiscal_quarter,
)

resolve_fiscal_quarter("NVDA", "2026-08-26")
# {"year": "2027", "quarter": "2", "confidence": "fiscal_offset", "label": "FY2027 Q2"}

resolve_fiscal_quarter("GOOGL", "2026-07-23")
# {"year": "2026", "quarter": "2", "confidence": "calendar_year", "label": "2026 Q2"}

resolve_fiscal_quarter("2330", "2026-07-17")
# {"year": None, "quarter": None, "confidence": "unknown", "label": None}
```

`confidence` tells the caller how much to trust the result:

- `"fiscal_offset"` / `"calendar_year"` — authoritative; prefer this over any
  upstream-guessed label (LLM metadata, stale CSV labels) when they conflict,
  and log the conflict rather than silently overriding.
- `"unknown"` — no mapping for this ticker; fall back to whatever other
  source the caller already has (upstream metadata, a hand-maintained label,
  etc.) rather than treating `None` as a real answer.

`calendar_to_fiscal(ticker, cal_year, cal_q)` and
`expected_us_calendar_earnings_quarter(date_str)` are exposed directly (not
just through `resolve_fiscal_quarter`) so existing call sites in `ingest.py`
and `fetch_upcoming_earnings.py` can import them as drop-in replacements for
their old local copies without changing call signatures.

## Consumers

| Repo | File | How it's wired in |
|---|---|---|
| `InvestorConference` | `skills/skill-company-investorconference-ingest/scripts/ingest.py` | `sys.path` insert to `skills/skill-stock-fiscal-quarter-resolve/scripts/`, imports `calendar_to_fiscal` and `KNOWN_US_CALENDAR_YEAR_EARNINGS` directly (same names as before — no other code changes needed). |
| `InvestorConference`, `InvestorEvents` | `skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py` | Same `sys.path` pattern; `_resolve_us_quarter_label` now calls `resolve_fiscal_quarter()` for **both** `fiscal_offset` and `calendar_year` tickers (previously only calendar-year tickers got a date-derived override — fiscal-offset tickers like NVDA/DELL blindly trusted ConceptStocks metadata). |
| `ConceptStocks` | `scripts/update_concept_metadata.py` | Deployed under `skills/skill-stock-fiscal-quarter-resolve/`; for tickers this skill recognizes, `即將發布`/`最新財報` are computed from the next yfinance earnings date instead of LLM-guessed, and are re-validated every run instead of being frozen once anchor fields (公司名稱/CIK) exist. |

## Verification

`scripts/fiscal_quarter_test.py` pins `resolve_fiscal_quarter()` against real
announcement dates for all 5 `KNOWN_US_FISCAL_YEAR_START_MONTH` tickers
(NVDA, DELL, QCOM, AAPL, MSFT), each cross-checked against a primary source
(the company's own SEC filing or IR press release naming, or an existing
verified InvestorConference README row) rather than computed by hand. Run it
after any change to `fiscal_quarter.py`:

```bash
python scripts/fiscal_quarter_test.py
```

The fiscal quarter is derived by composing `expected_us_calendar_earnings_quarter()`
(a coarse 3-month calendar-quarter bucket) with `calendar_to_fiscal()`, not by
a per-ticker "announcement month -> quarter" lookup table. A month-exact table
was tried first and rejected: it silently breaks whenever an announcement date
straddles a calendar-month boundary in a given year — verified in practice,
Dell's Q2 FY2027 call landed on 2026-09-01 while NVDA's own Q2 FY2027 call
landed 2026-08-26, one calendar month apart despite being the same fiscal
quarter for two companies with the same fiscal-year-start month. The coarser
bucket absorbs that wobble; a month-exact table does not.

## Extending the tables

Adding a ticker:

1. Confirm its actual fiscal-year-start month (or that its fiscal year equals
   the calendar year) from the company's own SEC filings / IR site — not from
   any single consumer's existing (possibly wrong) metadata.
2. Add it to `KNOWN_US_FISCAL_YEAR_START_MONTH` or
   `KNOWN_US_CALENDAR_YEAR_EARNINGS` in `scripts/fiscal_quarter.py` here in the
   registry, never in a consumer's copy.
3. Redeploy to all consumers (`self_update.py --deploy-all`) so they stay
   identical — this skill exists specifically to prevent the three-way
   divergence that caused the original NVDA mislabeling bug.
