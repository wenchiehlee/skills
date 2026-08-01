---
name: skill-company-competitor-analysis
description: >-
  Analyze a specified stock's competitors and peers by combining supply-chain product peer seeds,
  relationship-type rules, and quarterly financial performance. Use when the user asks to identify
  competitors for a stock id, avoid confusing suppliers with competitors, compare peers such as
  brand competitors / foundry competitors / ODM peers / server peers, or produce quarterly Revenue, Revenue YoY, Profit,
  Profit YoY, and Gross Margin tables for the most recent three years.
---

# Company Competitor Analysis Skill

## Role

Act as a cross-market equity research analyst. Treat competitor analysis as a two-layer problem:

1. `supply*.csv` provides product / supply-chain peer candidates.
2. Relationship rules decide whether a candidate is a `brand_competitor`, `chip_competitor`, `foundry_competitor`, `odm_peer`, `server_peer`, or `supplier_or_component`.

Do not use `Canonical cycle` alone as a competitor filter. It is an exposure/theme field, not a product-market competitor field.

## Standard Workflow

Run from the `biztrends.TW` repo root:

```bash
python3 skills/skill-company-competitor-analysis/scripts/run_company_competitor_analysis.py --stock 2357 --years 3
```

Optional filters:

```bash
python3 skills/skill-company-competitor-analysis/scripts/run_company_competitor_analysis.py --stock 2357 --relationship brand_competitor
python3 skills/skill-company-competitor-analysis/scripts/run_company_competitor_analysis.py --stock 2357 --relationship brand_competitor,server_peer
```

The runner writes:

- `output/focus/{stock}/company_competitor_analysis_{stock}.csv`
- `output/focus/{stock}/company_competitor_analysis_{stock}.md`

## Data Sources

Use these sources in this order:

1. `data/ic.tpex.org.tw/raw_SupplyChain_F000.csv`: Taiwan computer/peripheral product categories and peer seeds.
2. `data/ic.tpex.org.tw/raw_SupplyChain_D000.csv`: semiconductor supply-chain categories, including `IC/晶圓製造` foundry peer seeds.
3. `data/ic.tpex.org.tw/raw_SupplyChainMap.csv`: broader supply-chain context and supplier exclusion clues.
4. `data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv`: Taiwan quarterly actual financials.
5. `data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv`: Taiwan monthly revenue fallback for not-yet-reported quarters; fill only Revenue and Revenue YoY.
6. `data/InvestorConference/raw_ir_quarterly_financials.csv`: official IR quarterly rows for non-Taiwan peers; prefer this over provider fallback when symbol/quarter overlaps.
7. `data/ConceptStocks/raw_conceptstock_company_income.csv`: US/international quarterly actual financials; align `Q1`-`Q4` rows by `end_date` calendar quarter, not fiscal-year label.
7. `output/company_canonical_cycle_performance_details.csv`: latest cycle exposure only for context, not as the primary competitor filter.
8. `output/company_cycle_major_weights.csv`: latest Taiwan company revenue segment weights rolled up to canonical cycles; use this for AI canonical-cycle exposure context in markdown reports.
9. `data/company_segment_weights.csv` + `data/cycle_mapping.csv`: latest US active segment weights mapped to canonical or demand AI cycles when US peers are not present in `output/company_cycle_major_weights.csv`.

Read [references/competitor_rules.md](references/competitor_rules.md) before changing relationship rules or explaining why a company is included/excluded.

## Interpretation Rules

- Use `Stock` / `stock_code` / `symbol` only to identify companies.
- Use `位置` + `子分類` in supply-chain CSVs to find product peers.
- Use `relationship_type` to decide whether a peer should be shown as a competitor.
- For `2330 台積電`, classify dedicated wafer-foundry peers such as `2303` UMC, `GFS` GlobalFoundries, `INTC` Intel Foundry, `0981.HK` SMIC, and `005930.KS` Samsung Foundry as `foundry_competitor` when financial data exists. Do not classify IC design customers, packaging houses, equipment vendors, or materials suppliers as competitors.
- Exclude `supplier_or_component` and generic `product_peer` from default competitor tables unless the user explicitly asks for broader supply-chain adjacency.
- For `2357 華碩`, do not classify `2330 台積電` as a competitor. It is a semiconductor/foundry exposure or supplier-chain company, not a PC/server brand competitor.
- Mark international peers such as `DELL`, `HPQ`, and `0992.HK` as `brand_competitor` when the target is a PC brand and data exists.
- For IC design / connectivity chip targets such as `2379` Realtek, mark direct chip competitors such as `2454` MediaTek, `6526` Airoha, `AVGO` Broadcom, and `QCOM` Qualcomm as `chip_competitor` when financial data exists.

## Output Requirements

For each selected peer, show quarterly data for the most recent requested years. For Taiwan, include the latest month-revenue-only quarter when monthly revenue is available but quarterly financial statements are not yet released:

- `Revenue`
- `Revenue YoY`
- `Profit`
- `Profit YoY`
- `GM`

If a Taiwan quarter is based only on monthly revenue, label the markdown period header as `YYYYQn（月營收）`, fill `Revenue` and `Revenue YoY`, and leave `Profit`, `Profit YoY`, and `GM` blank. Keep CSV period values machine-readable, for example `2026Q2`.

For US rows, exclude annual `FY` rows from quarterly tables. Use `end_date` to convert fiscal quarters into calendar-quarter labels such as `2025Q4`; for example, a US fiscal `2026-Q1` row ending in December 2025 belongs under `2025Q4`. Prefer SEC rows over AlphaVantage rows when both map to the same company and calendar quarter, then recompute YoY against the selected prior-year same calendar quarter.

For Taiwan rows, use `TWD 億`. For non-Taiwan rows, preserve native currency units such as `USD 十億`, `HKD 十億`, or `KRW 十億`; the My-TW adapter converts supported foreign currencies to `百萬台幣`.

When writing markdown reports, use this top-level section order:

1. `Revenue/Profit/GM`
   - `1.1 Taiwan`
   - `1.2 US`
2. `AI Canonical Cycle Revenue Weights`
   - `2.1 Taiwan`
   - `2.2 US`

Pivot the Revenue/Profit/GM presentation table so `Period` is the major column and each period contains these subcolumns:

```text
Revenue | Rev YoY | Profit | Profit YoY | GM
```

For Taiwan monthly-revenue-only quarters, keep the `YYYYQn（月營收）` period free of financial-report event dates. If a matching `財報公告` or `法說會` date exists in `data/InvestorEvents/raw_event_upcoming_earnings.csv` and the full `YYYYQn` financial row is not available yet, render a plain `YYYYQn` placeholder period and show the event date in its first otherwise-empty financial cell, normally `Profit`.

Use HTML tables with `colspan` when needed, because standard Markdown pipe tables cannot express grouped period headers. Keep CSV output in long format for machine processing. In markdown reports, display `Relationship` cells in Traditional Chinese while preserving machine-readable relationship enums in CSV.

After the quarterly performance table, include an `AI Canonical Cycle Revenue Weights` markdown section sourced from `output/company_cycle_major_weights.csv`, and for US peers from `data/company_segment_weights.csv` plus `data/cycle_mapping.csv`. This section is a competition-context lens, not a competitor filter: among competitors, AI-related cycles are the strongest growth trend, so segment weights help distinguish whether revenue/profit momentum comes from AI exposure or from non-AI PC/ODM/base businesses. Show the latest available segment-weight period, confidence, source, total AI weight, and these AI-related canonical cycles when available: `AI_Server_Rack`, `AI_Foundry_Packaging`, `AI_Network_Infra`, `AI_Accelerator`, `AI_CPU_Orchestration`, `AI_Memory_HBM`, and `Cloud_AI_Compute`. For US peers, a mapped AI `demand_cycle` may be used as AI exposure context when the direct segment canonical cycle is non-AI. Leave blank cells for peers without active segment-weight allocations; do not use canonical-cycle fallback exposure as if it were segment-weight revenue mix.

State clearly when a row is a `brand_competitor`, `chip_competitor`, `foundry_competitor`, `odm_peer`, or `server_peer`. If a result is based only on supply-chain adjacency and not direct product competition, say so.

## My-TW-Coverage Adapter

When used inside the `My-TW-Coverage` repository, the render adapter is:

```bash
python3 skills/skill-company-competitor-analysis/scripts/render_competitor_financial_section.py \
  --json-dir data/enrichment_all \
  --ticker 2330
```

The adapter reads canonical competitors from `data/enrichment_all/{ticker}.json`, resolves competitor entity names to Taiwan stock IDs or US/international symbols, then renders a `### 競爭同業 Revenue/Profit/GM` markdown subsection. It uses `../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv`, `../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv`, and `../biztrends.TW/data/InvestorConference/raw_ir_quarterly_financials.csv` and `../biztrends.TW/data/ConceptStocks/raw_conceptstock_company_income.csv` for financial data.

The My-TW renderer imports this adapter directly from the repo-local `skills/skill-company-competitor-analysis` folder. Keep this local skill in sync with `../skills/common/skill-company-competitor-analysis` when changing the adapter.

## Validation

After editing the skill or runner, run:

```bash
python3 -m py_compile skills/skill-company-competitor-analysis/scripts/run_company_competitor_analysis.py
python3 /root/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/skill-company-competitor-analysis
python3 skills/skill-company-competitor-analysis/scripts/run_company_competitor_analysis.py --stock 2357 --years 3
```

Check that `2330` is not included for `2357` unless the user asks for supplier/component exposure. Check that Taiwan reports include the newest monthly-revenue-only quarter when available, for example `2026Q2` after April-June monthly revenue exists while Q2 financial statements are not yet available.
