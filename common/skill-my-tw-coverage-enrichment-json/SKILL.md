---
name: skill-my-tw-coverage-enrichment-json
description: >-
  Extract, review, validate, and later render My-TW-Coverage Markdown enrichment as atomic JSON,
  prioritized by biztrends.TW/StockID_TWSE_TPEX_focus.csv. Use when converting
  My-TW-Coverage Pilot_Reports Markdown into structured enrichment JSON, reviewing competitors,
  peers, customers, suppliers, moats, risks, technologies, products, applications, or planning
  JSON-canonical enrichment migration.
---

# My-TW-Coverage Enrichment JSON Skill

## Purpose

Convert `../My-TW-Coverage/Pilot_Reports/**/*.md` from presentation Markdown into atomic canonical JSON, using `data/enrichment_all` as the active JSON review universe.

Current state:

- `My-TW-Coverage` stores enrichment permanently in Markdown report sections.
- `scripts/update_enrichment.py` in `My-TW-Coverage` only applies three text blobs: `desc`, `supply_chain`, and `cust`.
- There is no current canonical enrichment JSON, claim table, evidence table, or review manifest.

Target state:

- Atomic JSON is canonical.
- Markdown is rendered presentation.
- Focus tickers are reviewed one by one before broad migration.

## Standard Workflow

Run from `../My-TW-Coverage` root:

```bash
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py
```

Equivalent explicit command:

```bash
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py \
  --focus ../biztrends.TW/StockID_TWSE_TPEX_focus.csv \
  --coverage-root . \
  --out data/enrichment_all \
  --manifest data/enrichment_all_manifest.csv
```

It can also run from `biztrends.TW` root:

```bash
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py \
  --focus StockID_TWSE_TPEX_focus.csv \
  --coverage-root ../My-TW-Coverage \
  --out ../My-TW-Coverage/data/enrichment_all \
  --manifest ../My-TW-Coverage/data/enrichment_all_manifest.csv
```

Useful scopes:

```bash
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py --ticker 2330
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py --limit 10
```

All-report migration preview:

```bash
python skills/skill-my-tw-coverage-enrichment-json/scripts/extract_enrichment_json.py \
  --all-reports \
  --out data/enrichment_all \
  --manifest data/enrichment_all_manifest.csv

python skills/skill-my-tw-coverage-render-markdown/scripts/render_enrichment_markdown.py \
  --json-dir data/enrichment_all \
  --out output/enrichment_all_rendered \
  --compare output/enrichment_all_render_compare.csv
```

## JSON Layering

Canonical JSON should keep both structured atoms and original Markdown snippets:

- `profile`: ticker, company name, sector, industry, market cap, enterprise value, source path.
- `business`: summary text plus extracted wikilinks.
- `supply_chain`: upstream, midstream, downstream, other rows.
- `relationships`: customers, suppliers, competitors, peers, substitutes.
- `competitive_position`: moats, risks, competitive notes.
- `entities`: all wikilinks with simple type classification.
- `source_text`: original section bodies, so migration is non-lossy.
- `evidence`: atomic source-backed facts and tables that rendered Markdown can cite.
- `annotations`: reviewed links from presentation claims to evidence objects, including badge-rendering intent.
- `themes`: reviewed links from company context to `data/themes/*.json` theme objects.
- `links`: optional resolved navigation links whose `kind` is `entity`, `theme`, or `evidence`.
- `quality`: parser status, review status, warnings, and counts.

Do not treat the first parsed JSON as approved. It remains a review artifact until its atoms are approved.

## Atomic Relationship Rules

Normalize competitive language into structured keys:

- `競爭對手`, `主要競爭對手`, `競爭同業`, `競爭:` -> `relationships.competitors`.
- `同業`, `同業包括`, `同業比較` -> `relationships.peers` unless direct competition is explicit.
- `避開紅海競爭`, `利基`, `技術領先`, `成本優勢`, `良率`, `客戶黏著` -> `competitive_position.moats` or `competitive_position.notes`.
- `替代`, `取代`, `外包轉自製`, `自研` -> `relationships.substitutes`.

When extraction is ambiguous, preserve text in `source_text` and add a `quality.warnings` entry instead of inventing a precise atom.

Do not auto-fill `relationships.competitors` from same-folder or same-industry peers. If competitors are not explicit in source or reviewed JSON, leave the array empty and review it manually. Folder peers are classification context, not validated competitors.

## Theme Link Rules

Themes are not company entities. `Apple`, `NVIDIA`, and `Tesla` refer to companies when used as entity mentions; `Apple 供應鏈`, `NVIDIA 供應鏈`, and `Tesla 供應鏈` refer to theme pages under `output/themes/`.

Theme definitions are canonical in `data/themes/*.json`. Brand supply-chain themes may define `anchor_entities` such as `Apple` or `NVIDIA`, but those anchors are only used to classify customer, supplier, or supply-chain contexts. Do not add plain company names such as `NVIDIA` to theme `aliases`; keep them in the entity/company universe.

Backfill/review theme links from My-TW-Coverage root:

```bash
python3 skills/skill-my-tw-coverage-enrichment-json/scripts/backfill_theme_links.py \
  --json-dir data/enrichment_all \
  --themes-dir data/themes \
  --review-out output/theme_link_review_queue.csv
```

After reviewing the queue, write additions with `--write`. New links should be stored in `themes[]` with `id`, `tag`, `role`, `source_path`, `matched_text`, `confidence`, and `status`. Use `status=needs_review` for derived matches until reviewed.

## Evidence and Annotation Rules

JSON should fully describe rendered Markdown context. Rendered Markdown is output, not storage. When a presentation claim has source-backed data, add an `evidence` object and an `annotations[]` entry rather than hardcoding Markdown badges.

First-wave evidence objects:

- `evidence.segment_revenue_platforms`: platform revenue mix and revenue amounts, sourced from `../biztrends.TW/data/company_segment_weights.csv` and matching revenue totals.
- `evidence.customer_relationships`: reviewed customer claims and supporting source documents.
- `evidence.peer_revenue`, `evidence.peer_profitability`, `evidence.peer_valuation`: competitor comparison data rendered as Revenue / Profit / GM / P/E.
- `evidence.market_valuation`, `evidence.quarterly_financials`, `evidence.consensus_estimates`: valuation, actual financials, and consensus evidence.

Only these high-value presentation contexts should receive first-wave annotator badges:

- `主要平台` -> `evidence.segment_revenue_platforms`
- `主要客戶` -> `evidence.customer_relationships`
- `競爭同業` -> peer evidence objects
- `估值/財務敘述` -> valuation, quarterly financial, or consensus evidence objects

Example annotation shape:

```json
{
  "id": "ann-2330-platform-revenue-001",
  "presentation_path": "supply_chain.downstream[category=主要平台]",
  "presentation_match": "主要平台",
  "claim_type": "segment_exposure",
  "evidence_ref": "evidence.segment_revenue_platforms",
  "render": {
    "badge": true,
    "label": "前10季-營收平台佔比",
    "color": "blue"
  },
  "confidence": "high",
  "status": "linked_supported"
}
```

Extractor/backfill logic may create `annotations[]`, but renderer must not invent annotations. If evidence is missing or only partially linked, set `status` to `missing_evidence_source`, `missing_evidence_structure`, `linked_partial`, or another explicit trust status instead of rendering a supported badge.

## Review Rules

For each focus ticker:

1. Confirm filename identity: `Ticker_公司名.md` must match `StockID_TWSE_TPEX_focus.csv`.
2. Check all customers, suppliers, competitors, peers, technologies, products, and applications are specific named entities where possible.
3. Keep generic labels as labels, not wikilink entities.
4. Preserve original Markdown snippets until rendered Markdown diff is clean.
5. Mark reviewed files by updating manifest status from `parsed` to `needs_review`, `reviewed`, or `approved`.

## Boundaries

- This skill does not render Markdown; use `skill-my-tw-coverage-render-markdown` for JSON-to-Markdown output.
- This skill does not update upstream financial CSVs.
- This skill may define or backfill JSON `evidence` and `annotations`, but it does not render Markdown badges directly.
- This skill does not directly update `biztrends.TW/data/company_segment_weights.csv`.
- This skill does not render `output/themes`; use `skill-my-tw-coverage-render-markdown` / `skills/skill-my-tw-coverage-render-markdown/scripts/build_themes.py` after theme links are reviewed.
- Do not treat legacy `source_text.*_md` as final storage for evidence; use it only as transitional non-lossy preservation until atomic evidence is complete.
