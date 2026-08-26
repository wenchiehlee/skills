---
name: skill-googlesearch-factsets-fetch
description: >-
  Operate and maintain the GoogleSearch.Factset two-stage pipeline: Stage 0
  watchlist refresh (Get觀察名單.py), Stage 1 Search Group (API-key rotation +
  4-layer content validation into data/md/*.md), Stage 2 Process Group
  (quality scoring, reports, Google Sheets upload), and the quarantine step
  between Search and Process. Covers manual triggering and debugging of
  Actions-update-lists.yaml, Actions-search.yaml, Actions-quarantine-files.yaml,
  and Actions-process.yaml, and triaging/fixing the GitHub Issues this repo's
  automation opens (daily Quarantine Alert data-quality issues). Use when the
  user asks to run or debug the FactSet pipeline, refresh the watchlist,
  investigate quarantined/low-quality MD files, or work through open issues at
  https://github.com/wenchiehlee/GoogleSearch.Factset/issues.
---

# GoogleSearch.Factset Fetch Skill

This skill covers the `GoogleSearch.Factset` repo's two-stage FactSet data pipeline. Work from the repo root unless the user gives another path. Full architectural reference lives in `CLAUDE.md` and `README.md` — this skill is the operational/maintenance layer on top of that: running stages, debugging workflows, and closing out the issues the automation opens.

## Source Of Truth

- Observation watchlist: `StockID_TWSE_TPEX.csv`
- Focus watchlist: `StockID_TWSE_TPEX_focus.csv`
- Watchlist refresh script: `Get觀察名單.py`
- Search CLI: `search_group/search_cli.py`
- Process CLI: `process_group/process_cli.py`
- Quarantine script: `scripts/quarantine_files.py`
- Data exchange (Search → Process): `data/md/*.md` — content-hash filenames `{代號}_{名稱}_factset_{hash}.md`
- Quarantined files: `data/quarantine/{inflated_quality,low_quality,inconsistent,old}/`
- Reports: `data/reports/*.csv` (`factset_detailed_report_latest.csv` drives quarantine detection)
- Workflows: `.github/workflows/Actions-update-lists.yaml`, `Actions-search.yaml`, `Actions-quarantine-files.yaml`, `Actions-process.yaml`
- Issue tracker: `https://github.com/wenchiehlee/GoogleSearch.Factset/issues`
- Skill-owned tooling: `scripts/analyze_quarantine_issues.py` (this skill's own script — aggregates open `data-quality` issues into a chronic-offender report; does not duplicate `quarantine_files.py` or `process_cli.py`, which operate on local files/CSV, not GitHub Issues)

Pipeline order enforced by `workflow_run` chaining: **Update Lists → Search (+CSV) → Quarantine → Process**.

## Two-Stage Architecture — Standard Workflow

```bash
# Stage 0: refresh watchlists
python Get觀察名單.py

# Stage 1: Search Group
python search_group/search_cli.py validate
python search_group/search_cli.py search --all --count 2 --min-quality 4
python search_group/search_cli.py status

# Quarantine (between Stage 1 and Stage 2)
python process_group/process_cli.py generate-csv
python scripts/quarantine_files.py --max-quality 7.4 --quarantine --yes

# Stage 2: Process Group
python process_group/process_cli.py process
python process_group/process_cli.py keyword-summary --no-upload
python process_group/process_cli.py watchlist-summary --no-upload
```

Targeted re-runs:

```bash
# Resume interrupted search
python search_group/search_cli.py search --resume --min-quality 4

# Re-search a single company (e.g. after quarantine flagged it)
python search_group/search_cli.py search --company 2330 --count 3 --min-quality 6

# Process only what changed recently
python process_group/process_cli.py process-recent --hours=24
python process_group/process_cli.py process-single --company 2330 --no-upload
```

## GitHub Actions Endpoints

### `Actions-update-lists.yaml` (primary endpoint for this skill)

- Schedule: daily `0 18 * * *` (18:00 UTC / 02:00 Taipei), plus `workflow_dispatch`
- Runs `Get觀察名單.py`, commits `StockID_TWSE_TPEX.csv` + `StockID_TWSE_TPEX_focus.csv` with message `📋 Update stock lists (Observation & Focus) - <date>` only if they changed
- Downstream: `Actions-search.yaml` listens via `workflow_run` on `["Update Stock Lists"]` and only proceeds if `conclusion == 'success'`

```bash
gh workflow run "Update Stock Lists"
gh run list --workflow "Actions-update-lists.yaml" --limit 5
gh run watch <run-id> --exit-status
```

If a scheduled run produced no commit, that's expected when the source lists didn't change — verify by diffing `StockID_TWSE_TPEX*.csv` against the previous commit, not by assuming failure.

### `Actions-search.yaml`

- Triggers on `workflow_run` completion of Update Lists, or `workflow_dispatch` (`company_count`, `min_quality`, `specific_companies`)
- Splits the watchlist into 4 parallel `matrix.batch` jobs; supports up to `GOOGLE_SEARCH_API_KEY14` / `GOOGLE_SEARCH_CSE_ID14` for rotation
- Runs `process_group/process_cli.py generate-csv` at the end so quarantine detection has fresh data
- Commits `data/md/*.md` with `🔍 Search Group v<ver> Results + CSV - <timestamp>`, retries push with `git pull --rebase -X ours` up to 10 times

### `Actions-quarantine-files.yaml`

- Triggers on `workflow_run` completion of the Search workflow (any conclusion except cancelled/skipped), or `workflow_dispatch`
- Runs `process_cli.py generate-csv` → `scripts/quarantine_files.py --max-quality 7.4 --quarantine --yes`
- Criteria: quarantine if `(quality_score >= 7.5 AND missing revenue/EPS)` OR `quality_score <= 7.4`
- Commits moved files + `old_files_report.txt` as `chore: Daily quarantine - CSV-based detection`
- **Opens a GitHub Issue automatically if more than 20 files were quarantined** (labels `data-quality`, `automated`) — see Issue Triage below

### `Actions-process.yaml`

- Triggers on `push` to `main`, `workflow_run` completion of Quarantine, or `workflow_dispatch` (`command`, `hours`, `no_upload`, `force_upload`)
- Commits `data/reports/*.csv`/`*.json` as `📊 Process Group v<ver> Reports - <timestamp>`

## Issue Triage & Resolution

The Quarantine workflow opens a new issue every day it quarantines >20 files, titled `🗂️ Quarantine Alert: N files detected (inflated/low quality)`, labeled `data-quality` + `automated`. **These issues are never auto-closed** — as of 2026-08-25 there are 118 open issues, one per day back to the repo's creation, because nothing in the pipeline closes them once the underlying files are fixed. Treat this backlog as a standing maintenance task, not a one-off.

### Step 1 — Survey open issues (most-effective-first, not one-by-one)

Do **not** `gh issue view` every issue individually — 118 open issues means 118 slow round-trips for data that's 95% identical day to day. Instead pull the newest N issues' bodies in a single call and run them through this skill's own aggregator:

```bash
gh issue list --repo wenchiehlee/GoogleSearch.Factset --json number,title,createdAt,body \
  --limit 10 --state open --label data-quality > issues.json
python scripts/analyze_quarantine_issues.py --json-in issues.json
```

This surfaces which stock codes are **chronic** (flagged in nearly every issue) vs. one-off. Chronic offenders are a code/process bug, not 19 separate data problems — triage those first since fixing the underlying cause closes many issues at once instead of one company at a time.

### Step 2 — Confirmed root cause (found and fixed 2026-08-25 — verify still current before reusing)

Across the newest 10 issues (#109–#118), 19 stock codes account for 321 of 341 flagged files, each recurring in ~18-23 of the 10 issues (i.e. essentially every day). They split into two genuinely different problems — don't treat them as one bug:

**A) `inflated_quality` (e.g. `2330` 台積電, flagged in all 10/10 issues) — was a real parser bug, now fixed.** The MD body (raw HTML fetched by Search Group) actually contains a well-formed `<table>` with the correct EPS and revenue figures — cnyes.com articles embed a schema.org `NewsArticle` JSON-LD block (`<script type="application/ld+json">`) near the top of the page whose `articleBody` field repeats the same section headings ("市場預估EPS", "市場預估營收") as plain text, well before the real `<table>` elements later in the page. `process_group/md_parser.py::_find_eps_table_html()` / `_find_revenue_table_html()` located the target table with `re.search(r'<anchor text>.*?<table>...</table>')` — an unbounded, non-greedy scan from the *first* occurrence of the anchor text. For "市場預估EPS" that first occurrence happened to be immediately followed by the correct table (lucky ordering). For "市場預估營收" it wasn't: the leftmost anchor sits inside the JSON-LD text, ~21,000 characters before *any* real table, so the regex's nearest-following-`<table>` was the EPS table, not the revenue table. `_extract_revenue_table_stats()` then read EPS-sized numbers (75–137) through a revenue parser that requires `>= 1000` (`_parse_numeric_value(raw, min_val=1000)`), rejected all of them, and returned all-`None` revenue stats — which is exactly `quarantine_files.py`'s `inflated_quality` trigger (`quality_score >= 7.5 AND missing revenue`).

  **Fix applied**: `process_group/md_parser.py` now has `_find_table_html_near_anchor(content, anchor, max_gap=2000)`, which tries every occurrence of the anchor text and accepts the first one with a `<table>` within `max_gap` characters (measured on a real page: genuine anchor→table gaps are 52–426 chars; the false JSON-LD anchor's gap is ~21,000–26,000 chars — enormous margin). `_find_eps_table_html()` and `_find_revenue_table_html()` now both call this helper. Verified directly against the real quarantined files for `2330` and `2357`: revenue stats went from all-`None` to fully populated (e.g. `revenue_2026_avg: 5049128260.0` for 2330). This is a `process_group` fix only — nothing in Search Group or the workflow YAML needed to change (no new dependency; `beautifulsoup4` was never actually needed for this).

**B) `low_quality` (score ≤ 7.4) for the other ~15 chronic stocks — not the same bug, still open.** Spot-checking `2357` (華碩) showed good EPS/target-price/analyst-count data (`data_completeness: 10.0`, `analyst_coverage: 8.0`) but a very low `data_freshness` score (`1`, for a 230-day-old article) — the same cnyes.com FactSet article keeps getting re-surfaced by search because no fresher one exists yet for that company. This is a genuine "stale source" condition, not a parsing bug — the Step 3 remedy below (re-search / pattern tuning) is the right tool for these, not another code fix.

### Step 3 — Fix root cause per reason (for genuinely one-off flags, once chronic offenders are separated out)

- **`low_quality`** (score ≤ 7.4), non-chronic: the search query for that company isn't finding good FactSet sources. Re-search with a higher `--min-quality`; inspect `search_group/instructions.md` / `REFINED_SEARCH_PATTERNS` for that company's query category.
- **`inflated_quality`** (score ≥ 7.5 but missing revenue/EPS), non-chronic: check the MD file's frontmatter/body for the same raw-HTML symptom above before assuming it's a one-off.
- **`inconsistent`** / **`old`**: usually resolved by a fresh `search_cli.py search --company <code>` re-run once the company is confirmed still on the current watchlist (`StockID_TWSE_TPEX.csv`).

Re-run for genuinely one-off, non-chronic companies only:

```bash
python search_group/search_cli.py search --company <code> --count 3 --min-quality 6
python process_group/process_cli.py process-single --company <code> --no-upload
```

Quarantined files are moved out of `data/md/`, not deleted — a fresh, higher-quality file for the same company will sit alongside them under a new content hash; the old quarantined copy in `data/quarantine/` does not need manual deletion unless the user asks.

### Step 4 — Close resolved issues

Once files for the companies named in an issue have been re-searched and pass quality (score ≥ 7.5 with full data, or explicitly accepted as-is), close it with a note referencing what was done:

```bash
gh issue comment <number> --repo wenchiehlee/GoogleSearch.Factset --body "Re-searched <codes>; new files pass quality threshold. Closing."
gh issue close <number> --repo wenchiehlee/GoogleSearch.Factset
```

When working through the backlog, prefer closing oldest-first and note in each comment which companies were addressed — later issues for the same company are often duplicates of an unresolved pattern, not new problems, so check newer issues for the same stock code before treating them as separate work.

### Step 5 — Address the systemic gap

The `inflated_quality` root cause (Step 2A) is fixed in `process_group/md_parser.py` as of 2026-08-25 — re-verify it's still applied (`git log -1 --oneline -- process_group/md_parser.py`) before assuming it's live; it still needs a commit/push and a Process Group re-run to actually re-score existing quarantined files and stop new ones from being wrongly flagged.

Remaining durable fixes, in priority order:
1. Re-run Process Group (`process_cli.py generate-csv` at minimum) after the `md_parser.py` fix lands, then re-check whether previously `inflated_quality` files now pass — this closes those issues without re-searching anything, since the underlying HTML/data was fine all along.
2. For `low_quality` chronic stocks (Step 2B, stale-article cases), tighten their search patterns or accept older articles at a lower quality floor, so they stop reappearing in daily reports for a condition that isn't going to change until a new FactSet consensus is published.
3. Add an auto-close step to `Actions-quarantine-files.yaml` (or a new workflow) that closes prior `data-quality` issues once a subsequent quarantine run finds zero files for the same companies — this is process debt independent of either root cause above.

Confirm with the user before editing workflow YAML or committing/pushing scoring logic changes — these are shared automation, not local files.

## Failure Modes

- `觀察名單未載入` → `StockID_TWSE_TPEX.csv` missing from repo root; re-run `Get觀察名單.py` or `Actions-update-lists.yaml`.
- `All API keys exhausted` → add more `GOOGLE_SEARCH_API_KEY1`–`14` / matching `GOOGLE_SEARCH_CSE_ID*` secrets; check `search_cli.py status` for rotation state.
- Content validation false positive/negative → check Layer 1 title-match logic in `search_engine.py`; confidence and `validation_layer` are recorded in the MD frontmatter for debugging.
- Google Sheets upload fails → verify `GOOGLE_SHEETS_CREDENTIALS` JSON in `.env` / repo secret.
- Search workflow ran but no quarantine issue followed → quarantine only opens an issue when >20 files are flagged; fewer files still get quarantined and committed, just silently.
- Quarantine commit push fails → workflow already retries `git pull --rebase -X ours` up to 10 times; a persistent failure usually means a conflicting concurrent push, not a code bug.

## Commit Message Conventions

- Watchlist: `📋 Update stock lists (Observation & Focus) - <date>`
- Search results: `🔍 Search Group v<ver> Results + CSV - <timestamp>`
- Quarantine: `chore: Daily quarantine - CSV-based detection`
- Process reports: `📊 Process Group v<ver> Reports - <timestamp>`

Match these when committing manually so history stays consistent with the automated runs.
