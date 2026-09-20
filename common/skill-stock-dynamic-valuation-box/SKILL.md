---
name: skill-stock-dynamic-valuation-box
description: Render no-look-ahead Taiwan-stock price charts with dynamic TTM P/E valuation boxes, optional buy/sell markers, and 2–5 year windows.
---

# Dynamic Valuation Box

Use this skill when a Taiwan stock needs a time-price diagram that separates valuation from technical timing.

## Output

For each requested stock, render a PNG and an auditable daily CSV containing:

- unadjusted daily close;
- TTM EPS that was available on that date;
- rolling PE mean, standard deviation, and price bands at `μ±1σ` and `μ±2σ`, computed over a trailing window of `--window` trading-day PE observations (default and minimum 120, i.e. roughly the last 6 months — pass a larger value for a longer-lookback, more stable band that reacts less to the current regime);
- optional actual buy and sell markers.

The green region is the core valuation box (`μ±1σ`). The red outer range (`μ±2σ`) is an alert boundary, not an automatic target price.

## Data contract with other skills

This skill owns only the valuation layer. Its daily CSV is the stable hand-off:

- **Consumes:** unadjusted close, nominal quarterly EPS, and (optionally) actual matched trade events.
- **Emits:** daily `close`, date-available `ttm_eps`, `pe`, and `price_m2`/`price_m1`/`price_mean`/`price_p1`/`price_p2` bands.
- **Does not calculate:** dividend-adjusted technical indicators, business-quality scores, earnings forecasts, consensus targets, or a buy/sell recommendation.

Downstream technical and quality skills must reference this CSV by date; they must not recalculate the valuation box from adjusted prices or later financial statements.

## Required valuation rules

1. Use **unadjusted close** with nominal EPS for PE. Do not use dividend-adjusted prices to calculate a PE valuation box.
2. Use only the latest four quarterly EPS figures that were available on the relevant date. The bundled script applies conservative Taiwan statutory filing deadlines: Q1 5/15, Q2 8/14, Q3 11/14, and Q4 of the following year 3/31.
3. Calculate each date's PE distribution from the trailing `--window`-sized rolling window ending on that date. Never use a later EPS, price, or completed rolling window in a historical decision.
4. Treat the valuation box, quality review, and technical timing as separate layers. The chart supplies the valuation layer; use dividend-adjusted price only when separately calculating RSI, moving averages, or other technical signals.

## Run

```bash
python skills/skill-stock-dynamic-valuation-box/scripts/render_dynamic_valuation_box.py \
  --symbols 3045 2412 \
  --years 2 \
  --trades-csv data/trades.csv \
  --output-dir output/dynamic_valuation_box
```

`--years` accepts only `2`, `3`, `4`, or `5`. `--end-date YYYY-MM-DD` freezes a historical retrospective. `--window` defaults to 120 trading observations (the minimum); raise it for a longer, less reactive PE baseline.

## Optional trade-event CSV

Provide the matched trade events rather than hard-coding a stock-specific history. Required columns are:

```text
symbol,date,side,price,lots
3045,2026-06-30,buy,116.5,9
3045,2026-09-15,sell,122.5,4
2412,2026-09-18,sell,145.5,1
```

`stock_id` may replace `symbol`; `qty` may replace `lots` and is converted from shares to lots. `side` accepts `buy`/`sell` or `買進`/`賣出`.

## Data and validation

- The script uses FinMind `TaiwanStockPrice` and `TaiwanStockFinancialStatements`.
- Confirm that the chart cutoff date is the intended trading date; a market holiday may make the last plotted close earlier than `--end-date`.
- If the trade CSV is used for a retrospective, derive it from the matched buy/sell records, including the source lot's actual buy date. Do not infer a buy date from price alone.
- Compare the final close and band values against the CSV before calling a chart a decision record.
