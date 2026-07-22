# Market Expectations TODO

This TODO tracks the next improvements needed to move `conference-digest` from
company-guidance comparison toward fuller market-expectation analysis.

## Current coverage

`data/Yahoo.Finance/raw_yahoo_finance_consensus_history.csv` is usable as a
repo-synced market consensus source for:

| Need | Current support | Source fields |
| :--- | :--- | :--- |
| Current-quarter revenue consensus | Supported | `revenue_0q_avg` |
| Current-quarter EPS consensus | Supported | `earnings_0q_avg` |
| Next-quarter revenue context | Supported, partial | `revenue_1q_avg` |
| Next-quarter EPS context | Supported, partial | `earnings_1q_avg` |
| Current-year revenue/EPS consensus | Supported | `revenue_0y_avg`, `earnings_0y_avg` |
| Next-year revenue/EPS consensus | Supported | `revenue_1y_avg`, `earnings_1y_avg` |

Usage rule: select the latest row where `forecast_asof_date <= event_date`.
If the selected row is more than 45 days before the event, lower confidence.

## Known gaps

Yahoo consensus history is not enough for a full conference-digest expectation
framework. Keep these fields as `NA` unless another source is explicitly
available:

| Gap | Why Yahoo consensus is insufficient | Needed data |
| :--- | :--- | :--- |
| Gross margin beat/miss | No gross margin consensus field | FactSet/Bloomberg/Visible Alpha/Koyfin/Tikr, broker models, or an internal consensus table |
| Operating margin beat/miss | No operating margin consensus field | Same as above |
| CapEx surprise | No CapEx consensus field | Broker models, company prior guidance, capex tracker, supply-chain capacity data |
| Segment/platform surprise | No segment-level forecast | Analyst models, company historical segment mix, customer/supply-chain read-through |
| Market-implied expectation | Consensus does not show what price already discounts | Pre-event price, valuation, volume, options implied move, peer moves, news sentiment |
| Estimate revision path | Need before/after time series around the event | Consensus snapshots before and after event date |
| Individual analyst dispersion | Yahoo file only stores averages | Analyst-level estimates, high/low/median/count/stdev |

## Proposed data additions

Add a repo-local expectation data layer under one of these locations:

| Path | Purpose |
| :--- | :--- |
| `data/Yahoo.Finance/raw_yahoo_finance_consensus_history.csv` | Source-synced revenue/EPS consensus history |
| `data/market_expectations/event_price_reactions.csv` | Pre/post event stock returns, volume, valuation and implied move |
| `data/market_expectations/company_guidance_history.csv` | Normalized prior company guidance ranges and midpoint deltas |
| `data/market_expectations/model_line_consensus.csv` | Gross margin, operating margin, CapEx, FCF and segment consensus |
| `data/market_expectations/estimate_revisions.csv` | Before/after EPS and revenue consensus revisions |
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
