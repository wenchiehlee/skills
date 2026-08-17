---
name: skill-investorconference-upcoming-earnings
description: >-
  Regenerate InvestorConference's raw_event_upcoming_earnings.csv locally from the repo's own
  Taiwan watchlists (StockID_TWSE_TPEX.csv / StockID_TWSE_TPEX_focus.csv) and the US watchlist
  (raw_conceptstock_company_metadata.csv). Classifies every event into 財報, 法說會, or 受邀法說.
  Use when the upcoming earnings/法說會 calendar is stale, when watchlists change, or before
  skill-investorconference-ingest's --auto-todo / --update-readme need fresh calendar data.
---

# InvestorConference Upcoming Earnings Skill

## Role

You keep `raw_event_upcoming_earnings.csv` accurate and self-contained inside the
`InvestorConference` repo. This calendar drives `skill-investorconference-ingest`'s
`--auto-todo` scan and README generation, so its 類別 classification must be correct,
not just its dates.

## Prerequisites

Run from the `InvestorConference` repo root. These files must exist there (download them
first if missing — do not fabricate or hand-edit them):

- `StockID_TWSE_TPEX.csv` — full Taiwan watchlist (代號,名稱), used for TW 財報 dates via yfinance.
- `StockID_TWSE_TPEX_focus.csv` — focus Taiwan watchlist, used for the (slower) per-stock MOPS 法說會 scrape.
- `raw_conceptstock_company_metadata.csv` — US watchlist with `Ticker`, `公司名稱`, and `即將發布` (authoritative fiscal-quarter label).

Refresh the two `StockID_TWSE_TPEX*.csv` files with `Get觀察名單.py` and
`raw_conceptstock_company_metadata.csv` from the ConceptStocks sync before running this
skill if they look stale.

## Standard Workflow

```bash
python skills/skill-investorconference-upcoming-earnings/scripts/fetch_upcoming_earnings.py
```

Optional explicit date window (default: today-30d ~ today+60d):

```bash
python skills/skill-investorconference-upcoming-earnings/scripts/fetch_upcoming_earnings.py --start 2026-07-01 --end 2026-10-31
```

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
| `受邀法說` | Invited investor forum / conference, not tied to a fresh quarterly report | MOPS TW row whose date is more than 50 days after the quarter end — same heuristic `skill-investorconference-ingest`'s README generator uses, so classification is consistent end-to-end. |

This is a from-scratch reclassification, not a downstream label: every `save_csv()` rewrite
re-normalizes 類別 for *existing* rows too (including any legacy `財報公告` value), so running
this skill migrates old data automatically — no separate one-off migration script needed.

## Source Rules

- Never hand-edit `raw_event_upcoming_earnings.csv` — always regenerate through this script so merge/dedupe/classification stay consistent.
- Taiwan watchlists and the US watchlist are the source of truth for *which* stocks to track; do not hardcode stock lists inside this skill.
- `即將發布` from `raw_conceptstock_company_metadata.csv` is authoritative for a US stock's fiscal-quarter label — prefer it over the date-shift heuristic (`_quarter_label`), which assumes a ~1-quarter reporting lag and mislabels fast-reporting companies (e.g. DELL, NVDA).
- Downstream consumers (`skill-investorconference-ingest`'s `ingest_from_todo` / `update_readme`) read 類別 as `財報` / `法說會` / `受邀法說` directly — do not reintroduce `財報公告` as an output value.
- A `受邀法說` row can be a genuinely separate appearance from the quarter's regular earnings-day call (e.g. an invited forum weeks/months later). `update_readme` guards against attaching the regular call's already-ingested materials to such a row unless its date is within 14 days of the same-quarter `財報` date — see `skill-investorconference-ingest`'s SKILL.md ("README `--update-readme` 合併規則"). Don't assume every `受邀法說` row will carry audio/transcripts even when materials already exist for that quarter.

## Replaces

This skill is the maintained path for generating `raw_event_upcoming_earnings.csv` inside
`InvestorConference`. Avoid copying the calendar in from another repo's `fetch_upcoming_earnings.py`
or hand-editing rows; extend this skill's script instead if scraping/classification needs to change.

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
