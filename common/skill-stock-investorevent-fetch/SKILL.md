---
name: skill-stock-investorevent-fetch
description: >-
  Regenerate a repo's raw_event_upcoming_earnings.csv locally from that repo's own Taiwan
  watchlists (StockID_TWSE_TPEX.csv / StockID_TWSE_TPEX_focus.csv) and US watchlist
  (raw_conceptstock_company_metadata.csv). Classifies every event into 財報, 法說會, or 受邀法說.
  Deployed identically to InvestorConference and InvestorEvents so both repos compute the same
  event dates and fiscal-quarter labels. Use when the upcoming earnings/法說會 calendar is stale,
  when watchlists change, or before skill-company-investorconference-ingest's --auto-todo /
  --update-readme need fresh calendar data.
---

# Investor Event Fetch Skill

## Role

You keep `raw_event_upcoming_earnings.csv` accurate and self-contained inside whichever repo
runs this skill. `InvestorConference` and `InvestorEvents` both deploy an identical copy under
`skills/skill-stock-investorevent-fetch/` — InvestorConference's `skill-company-investorconference-ingest`
`--auto-todo` scan and README generation, and InvestorEvents' `weekly-earnings.yml` +
`sync-to-Downstream.yml`, all depend on this CSV having correct dates *and* correct 類別
classification, computed the same way in both places.

> [!IMPORTANT]
> Never let the two repos' copies of `scripts/fetch_upcoming_earnings.py` diverge. Fix bugs or
> add classification logic here in the registry (`../skills`), then redeploy to both consumers
> with `self_update.py --deploy-all` — do not patch one repo's copy in place. A prior divergence
> (InvestorEvents stuck on a 645-line pre-`受邀法說` version while InvestorConference had the
> 946-line version with the `KNOWN_US_CALENDAR_YEAR_EARNINGS` fiscal-quarter-mismatch fix) is
> exactly the failure mode this shared skill exists to prevent.

## Prerequisites

Run from the consuming repo's root (`InvestorConference` or `InvestorEvents`). These files must
exist there (download them first if missing — do not fabricate or hand-edit them):

- `StockID_TWSE_TPEX.csv` — full Taiwan watchlist (代號,名稱), used for TW 財報 dates via yfinance.
- `StockID_TWSE_TPEX_focus.csv` — focus Taiwan watchlist, used for the (slower) per-stock MOPS 法說會 scrape.
- `raw_conceptstock_company_metadata.csv` — US watchlist with `Ticker`, `公司名稱`, and `即將發布` (authoritative fiscal-quarter label).

Refresh the two `StockID_TWSE_TPEX*.csv` files with `Get觀察名單.py` and
`raw_conceptstock_company_metadata.csv` from the ConceptStocks sync before running this
skill if they look stale.

## Standard Workflow

```bash
python skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py
```

Optional explicit date window (default: today-30d ~ today+60d):

```bash
python skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py --start 2026-07-01 --end 2026-10-31
```

InvestorEvents' `weekly-earnings.yml` and `fetch_all_events.py` call this script's
`generate_upcoming_earnings()` from the repo root — see "InvestorEvents integration" below.

The script does this in order:

1. Load the US watchlist + `即將發布` fiscal-quarter map from `raw_conceptstock_company_metadata.csv`.
2. Scrape Taiwan 法說會 dates from MOPS for the focus watchlist (`StockID_TWSE_TPEX_focus.csv`).
3. Pull US earnings dates via `yfinance` for every US watchlist ticker.
4. Pull Taiwan earnings dates via `yfinance` for the full watchlist (`StockID_TWSE_TPEX.csv`), falling back `.TW` → `.TWO` for TPEX/OTC stocks.
5. Sync Taiwan 財報 dates to the earlier MOPS 法說會 date when it's more reliable (yfinance TW dates are often stale estimates).
6. Merge into `raw_event_upcoming_earnings.csv`: match existing rows by 事件名稱, update date + 類別, add new rows, derive a same-day 法說會 row for every US 財報 row that doesn't already have one (including rows persisted from earlier runs, not just this run's fresh fetch — yfinance has no separate call-time source, so 財報 and 法說會 are otherwise indistinguishable for US stocks), dedupe near-duplicate 財報 rows, sort by date descending.

## 類別 Classification Rules

Every row's 類別 is exactly one of:

| 類別 | Meaning | How it's assigned |
|------|---------|--------------------|
| `財報` | Financial report release date | Any yfinance earnings-date row (US or TW). |
| `法說會` | Routine investor conference call, timed with the quarter's report | MOPS TW row whose date is within `INVITED_MEETING_THRESHOLD_DAYS` (50 days) of the event's fiscal-quarter end. |
| `受邀法說` | Invited investor forum / conference, not tied to a fresh quarterly report | MOPS TW row whose date is more than 50 days after the quarter end — same heuristic `skill-company-investorconference-ingest`'s README generator uses, so classification is consistent end-to-end. |

This is a from-scratch reclassification, not a downstream label: every `save_csv()` rewrite
re-normalizes 類別 for *existing* rows too (including any legacy `財報公告` value), so running
this skill migrates old data automatically — no separate one-off migration script needed.

## Source Rules

- Never hand-edit `raw_event_upcoming_earnings.csv` — always regenerate through this script so merge/dedupe/classification stay consistent.
- Taiwan watchlists and the US watchlist are the source of truth for *which* stocks to track; do not hardcode stock lists inside this skill.
- `即將發布` from `raw_conceptstock_company_metadata.csv` is authoritative for a US stock's fiscal-quarter label — prefer it over the date-shift heuristic (`_quarter_label`), which assumes a ~1-quarter reporting lag and mislabels fast-reporting companies (e.g. DELL, NVDA).
- Downstream consumers (`skill-company-investorconference-ingest`'s `ingest_from_todo` / `update_readme`) read 類別 as `財報` / `法說會` / `受邀法說` directly — do not reintroduce `財報公告` as an output value.
- A `受邀法說` row can be a genuinely separate appearance from the quarter's regular earnings-day call (e.g. an invited forum weeks/months later). `update_readme` guards against attaching the regular call's already-ingested materials to such a row unless its date is within 14 days of the same-quarter `財報` date — see `skill-company-investorconference-ingest`'s SKILL.md ("README `--update-readme` 合併規則"). Don't assume every `受邀法說` row will carry audio/transcripts even when materials already exist for that quarter.

## InvestorEvents integration

`InvestorEvents` imports this script as a module rather than only running it standalone:
`fetch_all_events.py` does `from fetch_upcoming_earnings import generate_upcoming_earnings`,
expecting the module importable from the repo root. Since the canonical copy now lives under
`skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py`, InvestorEvents'
`fetch_all_events.py` and `.github/workflows/weekly-earnings.yml` add that scripts/ directory to
`sys.path` (or run with `PYTHONPATH` set) before importing — see each file's top for the exact
mechanism. Do not reintroduce a root-level copy of `fetch_upcoming_earnings.py` in InvestorEvents;
that is what caused the original divergence.

## Replaces

This skill is the maintained path for generating `raw_event_upcoming_earnings.csv` inside both
`InvestorConference` and `InvestorEvents`. Never hand-edit rows or let either repo's copy diverge;
extend this skill's script in the registry and redeploy instead.

## Validation

After running, check the merge summary printed to stdout (`新增 N 筆` / `更新日期 N 筆` /
`無變更`), then spot-check classification:

```bash
python -c "
import csv
from collections import Counter
with open('raw_event_upcoming_earnings.csv', encoding='utf-8-sig') as f:
    print(Counter(r['類別'] for r in csv.DictReader(f)))
"
```

Expect only `財報`, `法說會`, `受邀法說` as keys — any other value means classification broke.
