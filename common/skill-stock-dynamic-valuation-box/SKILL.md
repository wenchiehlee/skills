---
name: skill-stock-dynamic-valuation-box
description: Render no-look-ahead Taiwan-stock price charts with dynamic TTM P/E valuation boxes, an optional forward-EPS overlay, optional buy/sell markers, and 2–5 year windows.
---

# Dynamic Valuation Box

Use this skill when a Taiwan stock needs a time-price diagram that separates valuation from technical timing.

## Output

For each requested stock, render a PNG and an auditable daily CSV containing:

- unadjusted daily close;
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
  --yahoo-consensus-csv ../Yahoo.Finance/data/reports/raw_yahoo_finance_consensus_daily.csv \
  --factset-report-csv ../Yahoo.Finance/data/reports/raw_factset_detailed_report.csv \
  --output-dir output/dynamic_valuation_box
```

`--years` accepts only `2`, `3`, `4`, or `5`. `--end-date YYYY-MM-DD` freezes a historical retrospective. `--window` defaults to 120 trading observations (the minimum); raise it for a longer, less reactive PE baseline. `--yahoo-consensus-csv`, `--factset-report-csv`, and `--forward-eps-csv` are all optional and independent — pass any subset (including none), and any combination; when none are given, the chart and CSV are unchanged from the trailing-only output.

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

**`--yahoo-consensus-csv`** — Yahoo Finance's own dated feed, unmodified. Required columns: `stock_code`, `forecast_asof_date`, `earnings_1y_avg` (a sibling `Yahoo.Finance` repo's `data/reports/raw_yahoo_finance_consensus_daily.csv` already has this shape).

**`--factset-report-csv`** — FactSet's own dated report feed, unmodified. Required columns: `代號` or `股票代號`, `MD日期`, and named-year `<year>EPS平均值` columns (a sibling repo's `data/reports/raw_factset_detailed_report.csv` already has this shape).

**`--forward-eps-csv`** — this skill's own normalized shape, for any other source once reshaped:

```text
symbol,as_of_date,forward_eps
3045,2026-01-15,7.20
3045,2026-04-15,7.45
2412,2026-08-14,5.60
```

`stock_id` may replace `symbol`. Add one row per re-estimate, dated by `as_of_date` (publication date, not fiscal-period end) — see rule 5 above.

On the top panel, the trailing TTM box stays the primary green/red region; a single pooled forward-PE mean and `±1σ` line overlay it in dashed orange (whichever source's estimate was newest as of that trading day — see rule 5).

On the bottom EPS panel, Yahoo and FactSet are **not** pooled: each source's own markers (diamond = Yahoo, square = FactSet) are positioned at the calendar year they actually forecast, not at publish date. The two sources routinely disagree on the same target year (sometimes by 20–40%+); this deliberately keeps that spread visible instead of silently picking whichever is newest. Every known revision for a given (source, target year) is plotted, not just the latest — older revisions render smaller and fainter, with a thin dotted vertical line tracing the revision path at that year's fixed x-position, so a consensus that moved from 64 to 99 across several reports reads as a visible climb rather than a single static number. Only the latest value per year gets a text label. A second thin dotted line then connects each source's latest-known value across consecutive target years (e.g. FY2026E → FY2027E → FY2028E), tracing the shape of its forward curve. The two panels share one x-axis, so a forward-EPS point's position is directly comparable to the price panel's date grid; when a target year runs past the requested `--years` window (e.g. FactSet's FY2028E), both panels' x-range extends together, compressing the visible price history rather than desynchronizing the two timelines.

## Data and validation

- The script uses FinMind `TaiwanStockPrice` and `TaiwanStockFinancialStatements`.
- Confirm that the chart cutoff date is the intended trading date; a market holiday may make the last plotted close earlier than `--end-date`.
- If the trade CSV is used for a retrospective, derive it from the matched buy/sell records, including the source lot's actual buy date. Do not infer a buy date from price alone.
- Compare the final close and band values against the CSV before calling a chart a decision record.
