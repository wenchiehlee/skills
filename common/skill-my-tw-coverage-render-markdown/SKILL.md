---
name: skill-my-tw-coverage-render-markdown
description: >-
  Render My-TW-Coverage canonical enrichment JSON into organized Markdown output.
  Use when the user asks to generate, regenerate, compare, or debug Markdown files
  from data/enrichment_all/*.json, especially output/enrichment_all_rendered/*.md.
  Keep Pilot_Reports out of the render source path; use it only as archived
  comparison material when explicitly needed.
---

# My-TW-Coverage Render Markdown Skill

Use this skill to render canonical enrichment JSON into Markdown for review or publication.

## Source Boundaries

- Canonical enrichment source: `data/enrichment_all/*.json`
- Rendered company output: `output/enrichment_all_rendered/*.md`
- Rendered theme output: `output/themes/*.md`
- Theme definitions: `data/themes/*.json`
- Comparison report: `output/enrichment_all_render_compare.csv`
- Revenue mix source when available: `../biztrends.TW/data/company_segment_weights.csv`
- Revenue amount fallback source: `../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv`
- Normalized consensus source: `../biztrends.TW/data/market_expectations/normalized_consensus.csv`
- Competitor financial source: repo-local `skills/skill-company-competitor-analysis` adapter, backed by `../biztrends.TW` financial CSVs
- Archived/legacy material: `Pilot_Reports/`

Do not use `Pilot_Reports/` as an active render source. Read it only for explicit comparison or migration audits. The intended future state is that `Pilot_Reports/` can be renamed or moved to an archived folder without breaking rendering.

## Standard Workflow

Run from the My-TW-Coverage repository root.

Render one ticker:

```bash
python3 skills/skill-my-tw-coverage-render-markdown/scripts/render_enrichment_markdown.py \
  --json-dir data/enrichment_all \
  --out output/enrichment_all_rendered \
  --compare output/enrichment_all_render_compare.csv \
  --segment-weights ../biztrends.TW/data/company_segment_weights.csv \
  --monthly-revenue ../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv \
  --biztrends-root ../biztrends.TW \
  --themes-dir data/themes \
  --ticker 2330
```

Render all canonical JSON files:

```bash
python3 skills/skill-my-tw-coverage-render-markdown/scripts/render_enrichment_markdown.py \
  --json-dir data/enrichment_all \
  --out output/enrichment_all_rendered \
  --compare output/enrichment_all_render_compare.csv \
  --segment-weights ../biztrends.TW/data/company_segment_weights.csv \
  --monthly-revenue ../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv \
  --biztrends-root ../biztrends.TW \
  --themes-dir data/themes
```

Rebuild theme pages through the same render skill:

```bash
python3 skills/skill-my-tw-coverage-render-markdown/scripts/build_themes.py
```

After rendering, inspect key files with `rg` or `sed` before committing:

```bash
rg -n "競爭同業|財務概況|營收平台佔比" output/enrichment_all_rendered/2330_台積電.md
git diff -- output/enrichment_all_rendered data/enrichment_all_render_compare.csv
```

## Rendering Rules

- Render `業務簡介`, `供應鏈位置`, `主要客戶`, `主要供應商`, `競爭同業`, `同業參照`, `替代關係`, and competitive-position sections from JSON.
- Keep relationship groups separate. Do not infer competitors from folder peers, chain peers, or same-industry fallbacks.
- Only render competitors that exist in `relationships.competitors`.
- Preserve explicit roles such as `晶圓代工競爭者`, `主要競爭對手`, `競爭同業`, or other curated labels from JSON.
- If a relationship array is empty, omit that Markdown subsection instead of fabricating content.
- If `evidence.segment_revenue_platforms` exists, render `營收平台佔比` from that JSON evidence object and replace any legacy `source_text.financial_md` copy of the same section.
- If no JSON evidence exists but `source_text.financial_md` already has `營收平台佔比`, preserve it and normalize its location after `季度關鍵財務數據`.
- If neither JSON evidence nor legacy section exists, inject `營收平台佔比` from `company_segment_weights.csv` for tickers with active rows.
- In `營收平台佔比` cells, include `percentage (revenue amount)` when a matching period revenue total exists; amounts are 百萬台幣. Prefer financial table revenue totals, then fall back to monthly revenue summed from GoodInfo Analyzer.
- Render `### 估值指標` from `financials.valuation` when present. Show market valuation and consensus valuation separately. Consensus revenue in My-TW-Coverage JSON and Markdown must be `百萬台幣`, matching the `財務概況` unit.
- Do not average Yahoo.Finance and FactSet consensus. Use Yahoo.Finance as primary and FactSet as cross-check / dispersion / target-price context. Downgrade confidence when cross-source differences are large.
- Insert `### 競爭同業 Revenue/Profit/GM` inside `## 財務概況` when competitors from JSON can be resolved to financial data. Place it after `營收平台佔比` when present, otherwise after `季度關鍵財務數據`.
- Insert a latest-period `主要平台` sentence under the downstream supply-chain section from `company_segment_weights.csv` for tickers with active rows, unless the source already has `主要平台`.
- Render annotator badges only from reviewed `annotations[]` entries. Do not infer badges from headings or keywords.
- First-wave annotator badge scope is limited to `主要平台`, `主要客戶`, `競爭同業`, and `估值/財務敘述` contexts.
- Evidence badge links must resolve through `evidence_ref` and the target evidence object's `render_section.anchor`. For a badge inside the same rendered company Markdown file, use a same-file anchor link.
- Entity badges are separate from evidence badges: in the final Markdown pass, convert any Obsidian-style wikilink that resolves to an existing `output/enrichment_all_rendered/{ticker}_{company}.md` into a shield badge whose visible label is only the entity name and whose link points to that rendered company context page.
- Do not render entity badges for unresolved entities; keep their original wikilinks. If a wikilink resolves to the current company page, render it as plain text instead of keeping `[[...]]`. Do not use entity badges as evidence unless the target page itself contains evidence-backed context.
- Normalize entity alias lookup for stable display variants such as spaces, underscores, hyphens, and case differences, so `[[LINE Pay]]` can resolve to `7722_LINEPAY.md` while unresolved real concepts remain wikilinks. Maintain a small curated alias table for high-confidence company short/full-name pairs such as `中華電信` -> `中華電`, `世界先進` -> `世界`, and `臻鼎` -> `臻鼎-KY`.
- Theme badges are separate from entity badges and evidence badges. Convert only wikilinks that resolve to `data/themes/*.json` theme `tag` or `aliases` into badges linking to `../themes/{output_filename}`.
- Do not use theme `anchor_entities` for badge conversion. `[[NVIDIA]]` is an entity/company mention; `[[NVIDIA 供應鏈]]` is a theme mention.
- Render theme pages with `python3 skills/skill-my-tw-coverage-render-markdown/scripts/build_themes.py`. The skill entry delegates to the repo-local `scripts/build_themes.py` implementation so theme rendering has one code path. Theme pages must be generated from `data/themes/*.json` plus `data/enrichment_all/*.json`, not from `Pilot_Reports/`.
- In rendered theme pages, company entries must use entity-style badge links to `output/enrichment_all_rendered/*.md`. Keep internal matching metadata such as `Theme ID`, `source_path`, and `match` out of presentation Markdown.

- Theme pages may define `theme_supply_chain` in `data/themes/*.json`. When present, `上游`, `中游`, and `下游/客戶關係` must be rendered from explicit criteria backed by `../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_*.csv`; free-text matches from company JSON should only contribute to `相關公司` so they do not distort the structured theme layers.
- In `theme_supply_chain`, each role contains IC taxonomy criteria such as `chain_code`, `chain_name`, `positions`, and `subcategories`. Rendered company rows should display the IC chain/subcategory as context, while internal provenance such as `source_path` and `match` stays out of presentation Markdown.
- Do not derive rendered theme company classification from `source_md` or `Pilot_Reports/` folder paths. Use JSON `profile.chain_name`, then `profile.industry`, then `profile.sector` for free-text related-company context.
- Render theme classification context as plain text; strip legacy wikilink markup from metadata fields such as `profile.industry` so strings like `[[Meta]]l Fabrication` display as `Metal Fabrication`.
- In taxonomy-backed theme sections, sort `上游`, `中游`, and `下游/客戶關係` entries by parsed JSON `profile.market_cap` descending, with unknown market cap last.
- Do not overwrite `Pilot_Reports/`.

## Financial Section Policy

`財務概況` is not enrichment content. Prefer generating it from financial functions or data adapters rather than storing it permanently in canonical enrichment JSON.

Current compatibility behavior may render `source_text.financial_md` when present in JSON. Treat that as transitional preservation, not the target architecture. `financials.valuation` is already atomic JSON and should override the legacy `source_text.financial_md` valuation subsection during rendering. Evidence-backed sections, starting with `evidence.segment_revenue_platforms`, should render from JSON evidence and replace same-named legacy Markdown sections. When implementing later renderer revisions, replace the remaining static financial text with direct financial generation and remove static financial text from `data/enrichment_all/*.json`.

## Validation

Before reporting completion:

1. Run Python syntax validation on the renderer:

```bash
python3 -m py_compile skills/skill-my-tw-coverage-render-markdown/scripts/render_enrichment_markdown.py
```

2. Render a known sample, usually `2330`, and rebuild themes when theme behavior changed:

```bash
python3 skills/skill-my-tw-coverage-render-markdown/scripts/build_themes.py
```

3. Confirm the rendered output comes from JSON and contains expected JSON-backed sections:

```bash
rg -n "競爭同業|財務概況|營收平台佔比" output/enrichment_all_rendered/2330_台積電.md
```

4. Check git status in both repositories when the shared skill changed:

```bash
git status --short
git -C ../skills status --short
```
