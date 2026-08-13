---
name: skill-my-tw-coverage-theme-groups
description: >-
  Curate accurate within-theme competitor groupings for output/themes/*.md by editing
  data/themes/*.json (`competitive_groups`, `extra_entities`). Use when a theme page groups
  companies that are not actually competitors (e.g. by GICS sector or raw IC-taxonomy
  subcategory instead of by real product/business-model overlap), when a theme is missing a
  company that the source taxonomy simply never tagged, or when a theme's groupings disagree
  with a company's own `relationships.competitors` in data/enrichment_all/*.json.
---

# My-TW-Coverage Theme Groups Skill

## Purpose

`output/themes/*.md` pages (built by `scripts/build_themes.py` from `data/themes/*.json` +
`data/enrichment_all/*.json`) exist to show, within one theme, which companies are actual
competitors of each other. The raw grouping signals available by default are too coarse for
that:

- IC-taxonomy subcategories (e.g. `其他電腦及週邊設備之零組件`) are catch-all buckets that mix
  unrelated business models.
- GICS/yfinance `profile.industry` sector labels (e.g. `Computer Hardware`) are even broader.
- The upstream TPEx `ic.tpex.org.tw` supply-chain pages this data is scraped from have real,
  confirmed gaps — a company can be a major player in a segment and simply not be tagged into
  the matching subcategory (see `references/known_gaps.md`).

This skill curates `data/themes/*.json`'s `competitive_groups` (regroup companies already in
the theme's dataset by real competitive segment) and `extra_entities` (inject a company the
source taxonomy omits entirely) so the rendered page groups true competitors together, and
keeps that grouping consistent with each company's own canonical competitor list maintained by
[skill-company-competitor-analysis](../skill-company-competitor-analysis/SKILL.md) /
[skill-my-tw-coverage-enrichment-json](../skill-my-tw-coverage-enrichment-json/SKILL.md)
(`data/enrichment_all/{ticker}.json` → `relationships.competitors`).

## Standard Workflow

Run from the My-TW-Coverage repository root.

0. **Check `references/curation_status.md`** for which themes are already cooked (have real
   `competitive_groups`) and which are still on the TODO list, sorted by size. Update it when
   you finish a theme. Some un-cooked themes heavily overlap already-cooked ones (e.g. 矽光子/
   CPO/磷化銦 overlap 資料中心's optical groups) — reuse that research instead of starting over.

1. **Pick a target.** Render or re-render the theme and look at its largest fallback buckets
   (group headers that are still a raw subcategory or GICS label, not a curated name):

   ```bash
   python scripts/build_themes.py "<theme tag>"
   rg -n "^\*\*" output/themes/<theme_file>.md
   ```

2. **Research each company in the bucket — never guess.** For every ticker in the bucket, read
   its actual business description and decide whether it genuinely competes with others in the
   bucket:

   ```bash
   sed -n '9,12p' output/enrichment_all_rendered/<ticker>_<company>.md   # 業務簡介
   ```

   Group by **real product/business-model overlap** (who bids for the same orders), not by
   supply-chain adjacency. A supplier to a company is not that company's competitor. If a
   company's true business is unrelated to the theme (e.g. a components distributor, an
   unrelated consumer-electronics maker), leave it in the fallback bucket — do not force a
   grouping that isn't backed by evidence.

3. **Check for a source-data gap.** If a company you know belongs in the theme is missing from
   the whole page, check whether the raw TPEx CSV actually has it tagged under a matching
   chain/subcategory:

   ```bash
   grep -n ",<ticker>," ../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_<chain_code>.csv
   ```

   If the company is tagged under a *different* subcategory only (a real gap, not a wrong
   assumption on your part), add it via `extra_entities` (step 5) instead of forcing it into
   `theme_supply_chain` criteria it doesn't actually match.

4. **Cross-check against canonical competitor data before finalizing.** Run:

   ```bash
   python skills/skill-my-tw-coverage-theme-groups/scripts/check_group_consistency.py --theme "<theme tag>"
   ```

   This is a pure comparison tool — it never edits anything. It flags two kinds of findings:

   - **Actionable**: a company's `relationships.competitors` names another company that IS in
     this theme's dataset but sits in a *different* group (or an ungrouped fallback bucket).
     This is a real disagreement between the theme grouping and canonical competitor data.
   - **Informational**: a group member has `relationships.competitors` entries, but none
     overlap this group (e.g. its listed competitor is a foreign private company not in the
     dataset, or its competitor data just hasn't been reviewed yet). Not necessarily wrong.

   It also prints a third, purely informational section — AI-canonical-cycle segment weights
   (from `../biztrends.TW/output/company_cycle_major_weights.csv`, the same data
   `skill-company-competitor-analysis` uses) for any curated group member that happens to have
   them. This is context only, never a grouping signal: coverage is far too sparse (a handful
   of tickers total have disclosed that granularity of revenue mix) and there is no reliable
   theme-level revenue total to normalize against, so a missing or low weight does not mean a
   company doesn't belong — see the discussion in `references/curation_status.md` if this needs
   revisiting later.

   **When the tool reports an actionable finding, stop and ask the user how to resolve it.**
   Verify the suggested addition against the company's own business summary first (step 2)
   before proposing it — the competitor list can itself be stale or `needs_review`. Do not
   silently pick a side. Possible resolutions:

   - Add the missing ticker to the `competitive_groups` entry (most common — the theme
     grouping was just incomplete).
   - Leave the theme grouping as-is if the two companies compete in the parent company's core
     business but not specifically in this theme's product/segment (e.g. a company can be a
     canonical competitor overall while only one of them participates in this particular
     AI-server/CoWoS/whatever product line).
   - Flag `relationships.competitors` itself as needing a fix — that data belongs to
     `skill-my-tw-coverage-enrichment-json`, not this skill; do not edit
     `data/enrichment_all/*.json` from this skill without the user's explicit go-ahead.

5. **Edit `data/themes/<theme>.json`.**

   - `competitive_groups`: an ordered list of `{"name": "...", "tickers": [...]}`. Order
     controls display order (curated groups always render before fallback groups, which sort
     by descending total group market cap). A ticker can only belong to one group per theme.
   - `extra_entities`: a list of `{"ticker", "company", "role", "sector", "note"}` for
     companies the source taxonomy never tagged into this theme at all. Always fill `note`
     with what you actually verified (which raw CSV/subcategory you checked and what you found
     missing) — see the existing `聯想` entry in `data/themes/AI_伺服器.json` for the pattern.
     `role` should be `upstream`/`midstream`/`downstream` to match how comparable companies in
     the same segment are tagged, or `related` if there's no clean match.
   - Group names should be a real segment name in Traditional Chinese (e.g. `ODM/系統整合 (AI
     伺服器代工)`, `散熱模組/液冷`), not a copy of the raw subcategory/GICS string.

6. **Rebuild the full site, not just one theme.** `build_themes.py "<tag>"` (single-theme mode)
   overwrites `output/themes/README.md` with only that one theme's entry, wiping every other
   theme from the index. Always finish with a full rebuild:

   ```bash
   python scripts/build_themes.py
   ```

7. **Validate.**

   ```bash
   python -m py_compile scripts/build_themes.py
   python skills/skill-my-tw-coverage-theme-groups/scripts/check_group_consistency.py --theme "<theme tag>"
   git status --short output/themes/
   ```

   Confirm: the curated group renders with the expected member count and companies; no
   unresolved actionable conflicts remain (or the remaining ones were explicitly left as-is per
   step 4); all themes rebuilt without error; `output/themes/README.md` still lists all themes.

## Rules

- **Never guess group membership.** Every addition must be backed by reading the company's own
  business description (`output/enrichment_all_rendered/*.md`), per the project's "never guess,
  never fill generically" rule in `CLAUDE.md`.
- **Render text stays Traditional Chinese.** Fallback grouping labels come from
  `profile.industry`/`profile.sector`, which are often raw English GICS/yfinance strings (e.g.
  `Computer Hardware`, `Semiconductors`). `scripts/build_themes.py` translates known values via
  `GICS_INDUSTRY_ZH`. If you encounter a new untranslated English label surfacing as a group
  header, add it to that dict rather than leaving it in English.
- **`competitive_groups` groups by product/business-model competition, not supply-chain
  position.** The rendered theme page no longer splits companies into 上游/中游/下游 chapters —
  everything renders under one `## 相關公司` list, grouped only by `competitive_groups` (then
  fallback subcategory/sector). Do not try to reintroduce a positional split; the underlying
  TPEx position tagging was confirmed unreliable enough (see `references/known_gaps.md`) that
  it isn't worth the confusion of splitting a real competitor group across sections.
- **`extra_entities` is for genuine source-data gaps only**, confirmed by grepping the raw CSV,
  not a shortcut for "I couldn't be bothered to check the taxonomy criteria."
- **Reconcile with `relationships.competitors`, don't override it silently.** This skill reads
  that field to sanity-check groupings; it does not write to `data/enrichment_all/*.json`. If a
  conflict looks like `relationships.competitors` is the one that's wrong or stale, say so to
  the user and hand off to `skill-my-tw-coverage-enrichment-json` rather than fixing it here.

## Data Sources

1. `data/themes/*.json` — theme definitions (`competitive_groups`, `extra_entities`,
   `theme_supply_chain`).
2. `data/enrichment_all/*.json` — canonical company data, including
   `relationships.competitors`.
3. `output/enrichment_all_rendered/*.md` — rendered business summaries used to verify group
   membership before adding a company anywhere.
4. `../biztrends.TW/data/ic.tpex.org.tw/raw_SupplyChain_*.csv` — the raw TPEx industry-chain
   source; grep this before claiming a company is missing due to a source-data gap.
5. `scripts/build_themes.py` — the renderer; `competitive_groups`/`extra_entities` handling
   lives in `build_theme_page()` / `scan_theme_links()` / `iter_extra_entities()`.

## Validation

After editing theme JSON or the consistency checker:

```bash
python -c "import json; json.load(open('data/themes/<theme>.json', encoding='utf-8'))"
python scripts/build_themes.py
python skills/skill-my-tw-coverage-theme-groups/scripts/check_group_consistency.py --all
git status --short data/themes/ output/themes/
```
