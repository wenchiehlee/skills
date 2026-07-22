# Market Expectations TODO

This TODO tracks the next improvements needed to move `conference-digest` from
company-guidance comparison toward fuller market-expectation analysis.

## Current Yahoo.Finance repo coverage

`../Yahoo.Finance` currently has more than one consensus file. Treat them as
different layers, not one generic market-consensus source.

| File | Useful for digest | Important fields / notes |
| :--- | :--- | :--- |
| `data/reports/raw_yahoo_finance_consensus_history.csv` | Historical revenue/EPS consensus snapshots reconstructed from Wayback | `earnings_0q_avg`, `earnings_1q_avg`, `earnings_0y_avg`, `earnings_1y_avg`, `revenue_0q_avg`, `revenue_1q_avg`, `revenue_0y_avg`, `revenue_1y_avg`; use latest `forecast_asof_date <= event_date` |
| `data/reports/raw_yahoo_finance_consensus_daily.csv` | Daily accumulated revenue/EPS and revision signal history | EPS/revenue yearly fields plus `eps_trend_*`, `eps_beat_count_4q`, `eps_surprise_avg_4q_pct`; currently lighter than `summary_latest` and does not retain quarter revenue columns |
| `data/reports/raw_yahoo_finance_summary_latest.csv` | Latest snapshot and cross-check context | Current Yahoo revenue/EPS consensus, EPS revision counts, last earnings surprise, FactSet cross-check, target-price context |
| `data/reports/raw_yahoo_finance.csv` | Long-format raw Yahoo analyst table | Includes mean/high/low/count style metrics for revenue/EPS and analyst target prices; useful to derive dispersion if normalized |
| `data/reports/raw_factset_detailed_report.csv` | FactSet annual EPS/revenue consensus and dispersion | Has analyst count, target price, annual EPS/revenue high/low/avg/median by year; no gross margin, operating margin, CapEx or segment fields observed |
| `data/reports/raw_yahoo_finance_daily_price.csv` | Pre/post event price reaction and valuation context input | Daily OHLCV for TW/US/macro symbols, about 10-year retention |
| `data/reports/raw_yahoo_finance_intraday_60m.csv` | Intraday event-window reaction where available | 60-minute OHLCV, roughly last 2-3 years depending on symbol |

Usage rule for non-lookahead consensus: select the latest row where
`forecast_asof_date <= event_date`. If the selected row is more than 45 days
before the event, lower confidence. For post-call estimate revision, compare the
last row before the event with the first reliable row after the event.

## Revised gap assessment

Yahoo.Finance repo already covers some items that were previously listed as
fully missing. Keep the distinction below:

| Need | Current status | Available source | Remaining gap |
| :--- | :--- | :--- | :--- |
| Revenue beat/miss | Supported | Yahoo consensus history / raw Yahoo / FactSet annual revenue | Quarter mapping and stale-date lint still needed |
| EPS beat/miss | Supported | Yahoo consensus history / raw Yahoo / FactSet annual EPS | EPS quality adjustment still requires company filings |
| Next-quarter revenue/EPS context | Supported, partial | Yahoo consensus history / summary latest | Needs automated cutoff and revision-window extraction |
| Annual analyst dispersion | Partly supported | FactSet high/low/avg/median and analyst count; raw Yahoo high/low/count | Mostly annual, not model-line or segment-level |
| Estimate revision path | Partly supported | `raw_yahoo_finance_consensus_daily.csv`, `summary_latest` history from append pipeline | Needs before/after event extractor and stable field set including quarter revenue |
| Market-implied expectation / price reaction | Partly supported | Daily price and 60m intraday price files | Needs event-window script, peer/market adjustment, valuation and options-implied move |
| Target-price context | Partly supported | Yahoo target price and FactSet target price | Target price is not the same as event-implied expectation |
| Gross margin beat/miss | Missing | None observed in Yahoo.Finance repo | Need FactSet/Bloomberg/Visible Alpha/Koyfin/Tikr, broker models, or internal consensus table |
| Operating margin beat/miss | Missing | None observed | Same as above |
| CapEx surprise | Missing | None observed | Need broker models, prior company guidance, capex tracker, supply-chain capacity data |
| Segment/platform surprise | Missing in Yahoo.Finance repo | ConceptStocks may have company segment metadata, but not analyst segment forecast | Need analyst models, historical segment mix, customer/supply-chain read-through |
| Individual analyst-level estimates | Missing | Current files store aggregates only | Need analyst-level rows or source report parsing with contributor identity |

## Proposed data additions

Add a repo-local expectation data layer under one of these locations:

| Path | Purpose |
| :--- | :--- |
| `data/Yahoo.Finance/raw_yahoo_finance_consensus_history.csv` | Source-synced revenue/EPS consensus history |
| `data/market_expectations/event_price_reactions.csv` | Derived from Yahoo daily/intraday price: pre/post event returns, volume, market/peer-adjusted reaction and valuation context |
| `data/market_expectations/company_guidance_history.csv` | Normalized prior company guidance ranges and midpoint deltas |
| `data/market_expectations/model_line_consensus.csv` | Gross margin, operating margin, CapEx, FCF and segment consensus |
| `data/market_expectations/estimate_revisions.csv` | Derived from Yahoo consensus daily/history: before/after EPS and revenue consensus revisions |
| `definitions/market_expectations_definition.md` | Column definitions for the new expectation layer |

## Proposed scripts

| Script | Responsibility |
| :--- | :--- |
| `scripts/extract_yahoo_consensus.py` | Given stock and event date, return the latest non-lookahead Yahoo consensus row |
| `scripts/build_event_price_reactions.py` | Build 1d/5d/20d pre-event and post-event returns, volume and valuation context |
| `scripts/normalize_company_guidance.py` | Convert prior guidance ranges into comparable midpoint/high/low records |
| `scripts/evaluate_expectation_delta.py` | Combine company guidance, Yahoo consensus, model-line consensus and price-implied data |
| `scripts/check_expectation_sources.py` | Lint for stale consensus rows, missing definitions and unsupported beat/miss claims |

## Digest behavior to implement

1. Add an `expectation_manifest` block to each digest:
   * `headline_consensus`: revenue/EPS source and date.
   * `model_line_consensus`: gross margin, operating margin, CapEx and segment coverage.
   * `price_implied_expectation`: price/valuation/options coverage.
   * `revision_window`: before/after dates used for estimate revisions.
2. Split Surprise Matrix result into:
   * `vs_prior_company_guidance`
   * `vs_market_consensus`
   * `vs_price_implied_expectation`
3. Require every beat/miss label to name its baseline.
4. Keep unsupported fields as `NA`, not inferred.
5. Add confidence rules:
   * High: current source row within 14 days, multiple metrics covered, no source conflict.
   * Medium: row within 45 days or only headline revenue/EPS covered.
   * Low: stale row, missing metric definition, or source mismatch.

## Priority order

1. Build `extract_yahoo_consensus.py` and make digest generation automatically
   populate revenue/EPS consensus when available.
2. Add `event_price_reactions.csv` to distinguish real surprise from already
   priced-in expectations.
3. Add company-guidance normalization so every quarter has clean prior guidance
   comparison.
4. Add model-line consensus only after a reliable source is available.
5. Add estimate revision tracking for post-call consensus changes.

## Acceptance criteria

For a completed enhanced expectation workflow:

* A digest can state revenue/EPS beat/miss from Yahoo consensus without manual lookup.
* Unsupported metrics remain `NA` and name the missing data source.
* Event-price analysis separates company beat/miss from what was already priced.
* All expectation fields have definitions and source timestamps.
* `evaluate_digest.py` warns when a digest claims market beat/miss without a
  valid baseline.
