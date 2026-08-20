---
name: skill-investment-institutional-thesis-research
description: Maintain and extend the TW-institutional-investment-theses repository in Traditional Chinese. Use when Codex needs to add or update institutional sources, articles, theses, forecast ledgers, taxonomy mappings, cross-institution comparisons, consensus reports, or research TODOs for auditable investment thesis research.
---

# Institutional Thesis Research

Use this skill to operate the institutional thesis repository as a research database, not an article archive. Default generated repository Markdown to Traditional Chinese, while preserving official titles, URLs, entity names, taxonomy keys, schema field names, status values, and quotes in their original language when accuracy depends on it.

## Required Context

Before editing, read the local repository guidance that matches the task:

- `AGENTS.md` for non-negotiable research rules.
- `TAXONOMY.md` before adding or changing themes.
- `DATA_MODEL.md` before changing schemas or ledger structure.
- `RESEARCH_WORKFLOW.md` and `SOURCE_POLICY.md` when ingesting new sources.
- Existing institution files under `institutions/<institution>/` before creating a new thesis.

## Epistemic Rules

- Prefer primary institutional sources. If only secondary material is available, label it explicitly and add a TODO for primary-source verification.
- Never fabricate titles, authors, dates, URLs, forecasts, quotes, or institutional positions.
- Separate `fact`, `institution_interpretation`, and `repository_inference`.
- Preserve forecast revisions chronologically; never overwrite an earlier forecast with a newer one.
- Do not force consensus. Disagreement, missing scope, and non-comparable numbers are valid findings.
- Do not jump from article to ticker without documenting the transmission chain.

## Core Workflow

1. Verify the source identity, publication date, URL, institution, and source tier.
2. Check duplicates by URL, normalized title, institution/date, syndicated copies, and repeated claims.
3. Record article metadata under `institutions/<institution>/articles/<year>/`.
4. Extract key claims and quantitative forecasts, with confidence and epistemic layer.
5. Search existing thesis files for conceptual overlap before creating a new thesis.
6. Update thesis evidence, history, invalidation conditions, and theme mappings.
7. Add forecast observations to `data/<institution>-forecasts.yaml` when the source contains important numbers.
8. Update `comparisons/` or `reports/` only when the new evidence changes the cross-institution view, open questions, or reader navigation.

## Repository Maturity Map

- Goldman Sachs is the pilot with article records, multiple thesis files, forecast ledger, forecast summary, open questions and deeper reports.
- Morgan Stanley, J.P. Morgan, Bank of America and UBS are first-touch institutions; keep confidence lower until more primary sources accumulate.
- The current five-institution AI capex overview uses Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America and UBS.
- Current focus themes include `AI_CAPEX`, `AI_INFRASTRUCTURE`, `POWER_DEMAND`, `POWER_GRID`, `DATA_CENTERS`, `AI_ROI`, `PHYSICAL_AI`, `PRIVATE_CREDIT`, `RELEVERAGING` and `HALO_REAL_ASSETS`.
- BofA currently supports the power / physical-AI transmission layer but does not yet provide a comparable hyperscaler capex point forecast in this repo.
- UBS currently provides explicit AI capex anchors and the capex-discipline / capex-taper-tantrum lens; verify scope before averaging with narrower hyperscaler estimates.
- Treat `POWER_EQUIPMENT`, cooling, networking and AI infrastructure financing as candidate sub-theses until enough direct evidence supports separate thesis files.

## Output Patterns

- Article records: one source per Markdown file, preserving official metadata and separating claims from inference.
- Thesis records: recurring institutional interpretation with evidence, status, conviction, invalidation conditions, history, and taxonomy mapping.
- Forecast ledgers: append-only dated observations. Use `templates/forecast-ledger-template.yaml` for new ledgers.
- Comparisons: state scope mismatches clearly before presenting consensus or ranges; do not average Goldman, Morgan Stanley, J.P. Morgan and UBS capex anchors unless the metric scope is comparable.
- TODOs: use when evidence is missing, ambiguous, or not yet sufficient for a thesis split.

## Validation

Run the bundled script after editing forecast ledgers:

```bash
python3 skills/skill-investment-institutional-thesis-research/scripts/check_forecast_ledger.py data/goldman-forecasts.yaml data/morgan-stanley-forecasts.yaml data/jpmorgan-forecasts.yaml data/bank-of-america-forecasts.yaml data/ubs-forecasts.yaml
```

Also run `git diff --check` before committing Markdown/YAML changes.
