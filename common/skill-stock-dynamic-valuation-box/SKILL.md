---
name: skill-stock-dynamic-valuation-box
description: Render no-look-ahead Taiwan-stock price charts with dynamic TTM P/E valuation boxes, an optional forward-EPS overlay, optional buy/sell markers, and 2–5 year windows.
---

# Dynamic Valuation Box

## Output artifacts

For each requested stock, the renderer writes a PNG, an SVG using the same figure, and an auditable daily CSV. Use the SVG for Markdown/report embedding and the CSV as the numeric hand-off.
For environments without an installed CJK font, set `TW_CJK_FONT` to a Traditional Chinese
font file (for example, Noto Sans CJK TC) before rendering. The same selected font is used
for PNG and SVG output.
Panel 1 remains the valuation-price panel. Panel 2 is a technical price panel using the same close series as panel 1, with SMA20, SMA60, SMA120, SMA240, and 20-day Bollinger bands: middle SMA20, ±1σ, and ±2σ. The P/E panel and existing EPS, revenue, and profit panels follow after it, so the chart now has 12 panels.
`raw_revenue.csv` is preferred, with FinMind `TaiwanStockMonthRevenue` filling missing months.
The fourth, short panel shows YoY revenue growth for that reconciled series.
Pass `--analyzer-revenue-csv` to override the Analyzer CSV path.

Use this skill when a Taiwan stock needs a time-price diagram that separates valuation from technical timing.

## Output

For each requested stock, render a PNG and an auditable daily CSV containing:

- unadjusted daily close;
- SMA20, SMA60, SMA120, SMA240, and Bollinger middle/upper1/lower1/upper2/lower2 columns used by panel 2;
- TTM EPS that was available on that date;
- rolling PE mean, standard deviation, and price bands at `μ±1σ` and `μ±2σ`, computed over a trailing window of `--window` trading-day PE observations (default and minimum 120, i.e. roughly the last 6 months — pass a larger value for a longer-lookback, more stable band that reacts less to the current regime);
- when `--forward-eps-csv` is supplied, the matching forward-PE line (`forward_pe_mean` ± bands) computed the same way but on forward EPS instead of trailing TTM EPS;
- optional actual buy and sell markers.

The green region is the core valuation box (`μ±1σ`). The red outer range (`μ±2σ`) is an alert boundary, not an automatic target price. The dashed orange line/box is the forward-EPS equivalent, shown only when forward-EPS input is provided; it complements, and does not replace, the trailing box.

When a Yahoo/FactSet curve extends past today, the top panel also draws one future trend ray per source (colored to match that source's bottom-panel markers): today's forward-PE multiple (mean and ±1σ, held constant) applied to that source's own future-year EPS estimate — i.e. "what price today's multiple implies once this year's consensus is realized," not a new multiple assumption. Two sources with different future EPS trajectories produce two different rays from the same starting point.

## Data contract with other skills

This skill owns only the valuation layer. Its daily CSV is the stable hand-off:

- **Consumes:** unadjusted close, nominal quarterly EPS, and (optionally) actual matched trade events.
- **Emits:** daily `close`, date-available `ttm_eps`, `pe`, and `price_m2`/`price_m1`/`price_mean`/`price_p1`/`price_p2` bands.
- **Does not calculate:** dividend-adjusted technical indicators, business-quality scores, earnings forecasts, consensus targets, or a buy/sell recommendation.

Downstream technical and quality skills must reference this CSV by date; they must not recalculate the valuation box from adjusted prices or later financial statements.

Forward EPS is a distinct, optional layer with its own contract:

- **Consumes:** a dated consensus/forward-EPS feed — FinMind has none of its own, but Yahoo Finance and FactSet do. Point the script at either feed's native export directly (`--yahoo-consensus-csv`, `--factset-report-csv`), or at a CSV already reshaped into this skill's own `symbol,as_of_date,forward_eps` form (`--forward-eps-csv`). All three may be combined; rows are pooled and the backward merge just uses whichever source's estimate was newest as of each trading day.
- **Emits:** date-available `forward_eps`, `forward_pe`, and `forward_price_m2`/`forward_price_m1`/`forward_price_mean`/`forward_price_p1`/`forward_price_p2` bands, alongside the trailing-EPS columns, in the same daily CSV.
- **Does not calculate:** the forward EPS estimate itself, or any consensus/analyst reconciliation — that is Yahoo's/FactSet's job upstream of this skill.

## Required valuation rules

1. Use **unadjusted close** with nominal EPS for PE. Do not use dividend-adjusted prices to calculate a PE valuation box. The one exception is a stock dividend / capital-increase-from-earnings event (a share-count change, not a cash payout): the script rescales close before the ex-date and the affected quarterly EPS onto the post-event share basis via FinMind `TaiwanStockDividend`, otherwise a single such event makes the raw close series jump and any rolling window straddling it compares two incompatible share counts.
2. Use only the latest four quarterly EPS figures that were available on the relevant date. The bundled script applies conservative Taiwan statutory filing deadlines: Q1 5/15, Q2 8/14, Q3 11/14, and Q4 of the following year 3/31.
3. Calculate each date's PE distribution from the trailing `--window`-sized rolling window ending on that date. Never use a later EPS, price, or completed rolling window in a historical decision.
4. Treat the valuation box, quality review, and technical timing as separate layers. The chart supplies the valuation layer; use dividend-adjusted price only when separately calculating RSI, moving averages, or other technical signals.
5. Forward EPS must be merged on its `as_of_date` — the date the estimate was published/known, never the target fiscal period end. This is what keeps the forward-PE band no-look-ahead: on any given trading day the chart only ever sees the newest forward-EPS estimate that already existed by that day, exactly like the trailing-EPS `available_date` rule above. A revised or bumped consensus estimate is a new row with its own `as_of_date`, not an edit of the old one. Yahoo's `forecast_asof_date` already satisfies this directly. FactSet's `MD日期` (report date) is used the same way, but FactSet reports named fiscal-year columns (`2025EPS平均值` … `2028EPS平均值`) rather than a single rolling "next FY" figure, so `--factset-report-csv` derives the forward figure per report as the average-EPS column for calendar year(`MD日期`) + 1 — the same "next full fiscal year" concept as Yahoo's `earnings_1y_avg`, just read off a named-year column instead of a dedicated one.

## Run

```bash
python skills/skill-stock-dynamic-valuation-box/scripts/render_dynamic_valuation_box.py \
  --symbols 3045 2412 \
  --years 2 \
  --trades-csv data/trades.csv \
  --yahoo-consensus-csv ../biztrends.TW/data/Yahoo.Finance/raw_yahoo_finance_consensus_daily.csv \
  --factset-report-csv ../biztrends.TW/data/GoogleSearch.Factset/raw_factset_detailed_report.csv \
  --output-dir output/dynamic_valuation_box
```

`--years` accepts only `2`, `3`, `4`, or `5`. `--end-date YYYY-MM-DD` freezes a historical retrospective. `--window` defaults to 120 trading observations (the minimum); raise it for a longer, less reactive PE baseline. `--yahoo-consensus-csv`, `--factset-report-csv`, and `--forward-eps-csv` are all optional and independent — pass any subset (including none), and any combination; when none are given, the chart and CSV are unchanged from the trailing-only output.

## Price CSV gap-fill (FinMind quota saving)

`--price-csv` (default `../Python-Actions.FinMind/data/stage1_raw/raw_daily_k_chart_flow.csv`) points at a pre-fetched FinMind `TaiwanStockPrice` snapshot with `stock_code`, `交易_日期`, `收盤價_元` columns. `TaiwanStockPrice` is by far this skill's heaviest FinMind call — it pulls `--years + 3` years of daily closes on every run — so before calling it live, the renderer reads whatever the snapshot already covers for that symbol and only fetches the gap after its last date through `--end-date`. A snapshot that already reaches `--end-date` skips the live call entirely; a missing file, a symbol it doesn't have, or one whose last date is older than the requested start all fall back unchanged to fetching the full range live, same as if `--price-csv` had never been given — a stale or absent snapshot costs extra API calls, never wrong data. This only applies to `TaiwanStockPrice`; `TaiwanStockDividend` (no event-level CSV exists anywhere in this codebase, only GoodInfo-style annual rollups without ex-dividend dates), `TaiwanStockFinancialStatements` (the one candidate CSV, a monthly-cadence general-purpose financial-ratio table, is fragile to parse and cadence-mismatched with quarterly EPS), and `TaiwanStockInfo` (cheapest call of the four; not worth it) all stay live-fetched.

## Optional trade-event CSV

Provide the matched trade events rather than hard-coding a stock-specific history. Required columns are:

```text
symbol,date,side,price,lots
3045,2026-06-30,buy,116.5,9
3045,2026-09-15,sell,122.5,4
2412,2026-09-18,sell,145.5,1
```

`stock_id` may replace `symbol`; `qty` may replace `lots` and is converted from shares to lots. `side` accepts `buy`/`sell` or `買進`/`賣出`.

## Optional forward-EPS input

Three ways to supply forward/consensus EPS — the script does not fetch or forecast these itself, and any combination may be used together (see rule 5 for how sources are reconciled):

**`--yahoo-consensus-csv`** — Yahoo Finance's own dated feed, unmodified. Required columns: `stock_code`, `forecast_asof_date`, `earnings_1y_avg` (the `biztrends.TW/data/Yahoo.Finance/raw_yahoo_finance_consensus_daily.csv` synchronized artifact already has this shape).

**`--factset-report-csv`** — FactSet's own dated report feed, unmodified. Required columns: `代號` or `股票代號`, `MD日期`, and named-year `<year>EPS平均值` columns (the `biztrends.TW/data/GoogleSearch.Factset/raw_factset_detailed_report.csv` synchronized artifact already has this shape).

**`--forward-eps-csv`** — this skill's own normalized shape, for any other source once reshaped:

```text
symbol,as_of_date,forward_eps
3045,2026-01-15,7.20
3045,2026-04-15,7.45
2412,2026-08-14,5.60
```

`stock_id` may replace `symbol`. Add one row per re-estimate, dated by `as_of_date` (publication date, not fiscal-period end) — see rule 5 above.

On the top panel, the trailing TTM box stays the primary green/red region; a single pooled forward-PE mean and `±1σ` line overlay it in dashed orange (whichever source's estimate was newest as of that trading day — see rule 5).

On the bottom EPS panel, Yahoo and FactSet are **not** pooled. Each source has one curve segment for FY2025E, FY2026E, FY2027E, and FY2028E. Every released estimate is plotted at its actual release date as a circle (`●`), and the last known value is carried horizontally to that fiscal year's 12/31 terminal node shown as a triangle (`▲`) with the `Source FY202xE value` label. Line styles distinguish target years while source colors distinguish Yahoo and FactSet. The source files are consumed only from the canonical `biztrends.TW` synchronized artifacts, not directly from `Yahoo.Finance`.

## Data and validation

- The script uses FinMind `TaiwanStockPrice` and `TaiwanStockFinancialStatements`.
- Confirm that the chart cutoff date is the intended trading date; a market holiday may make the last plotted close earlier than `--end-date`.
- If the trade CSV is used for a retrospective, derive it from the matched buy/sell records, including the source lot's actual buy date. Do not infer a buy date from price alone.
- Compare the final close and band values against the CSV before calling a chart a decision record.

## FinMind token resolution

Reads a `.env` file (via `python-dotenv`, if installed) in addition to already-exported environment variables, then checks, in order: `FINMIND_TOKEN`, `FINMIND_API_TOKEN`, `FINMIND_TOKEN1`..`FINMIND_TOKEN6`, `FINDMIND_GMAIL_TOKEN`, `FINDMIND_GMAIL_TOKEN1`..`FINDMIND_GMAIL_TOKEN6` (the last group's "FINDMIND" spelling matches `skill-finmind-fetch`'s own convention, which this skill does not import — the name list is duplicated here instead of adding a hard dependency on that skill's heavier `requests`/`python-dotenv` fetch module). Every configured token is pooled: on an HTTP 402 or a `"reach the upper limit"`/`"token is illegal"` response the exhausted token is retired for the rest of the process and the next one is tried, so one run can outlast a single account's quota (FinMind's quota window resets hourly, not daily). With none configured, requests fall back to anonymous FinMind access (a small but real quota) and a one-time warning is printed to stderr; a run that also finds every token or anonymous access already exhausted raises a `RuntimeError` naming the checked env vars, rather than surfacing a bare `HTTP Error 402` deep in a traceback.

## Batch rendering

`scripts/render_dynamic_valuation_batch.py` wraps the per-symbol renderer for bulk runs: it scans a directory of company JSON files (`--json-dir`, default `data/enrichment_all`) for numeric tickers, skips ones whose three artifacts (`.png`/`.svg`/`.csv`) already exist unless `--force` is passed, runs the renderer as a subprocess per symbol with a configurable worker pool (`--workers`), and writes any failures to a TSV (`--failure-log`) with tokens redacted from the captured stderr/stdout — so a partial batch run is retryable without re-rendering everything or leaking a credential into the log. It inherits the parent process's full environment into each subprocess, so the same `TOKEN_ENV_NAMES` pool above governs every worker; `--token-env-prefix` (default `FINMIND_TOKEN`) and `--workers` only affect this wrapper's own worker-count heuristic, not which token a given subprocess actually uses.
