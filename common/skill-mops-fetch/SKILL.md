---
name: skill-mops-fetch
description: >-
  Fetch Taiwan MOPS data for the MOPS repo end to end: download quarterly
  financial-report PDFs (AI1/AI2/AI3/AE2), convert same-stem PDF sidecars to
  Markdown via the skill-mac-mini-ocr hybrid PDF/OCR pipeline, and orchestrate
  the repo's batch-all, early-filer-detection, watchlist-refresh, and
  health/matrix-report scripts as one fetch pipeline. Use when MOPS
  downloads/*.pdf files are missing Markdown, stale, or need auditable
  TODO:OCR repair, or when asked to run/extend any MOPS data-fetch step.
---

# MOPS Fetch Skill

## Role

You are the single maintained entry point for pulling and refreshing Taiwan MOPS data in the `MOPS` repo: financial-report PDFs, their Markdown sidecars, the stock watchlist, early-filer detection, and the resulting health/matrix reports. Previously this was split across ad hoc repo-local scripts; this skill (formerly `skill-company-mops-financialreport-pdf-md`) is the successor and covers the full fetch surface, not just PDF-to-MD.

## Boundary

This skill is separate from `skill-company-investorconference-ir-pdf-md`.

- `skill-mops-fetch`: fetches MOPS financial statement PDFs such as `AI1`, `AI2`, `AI3`, and `AE2` under `MOPS/downloads/<company_id>/`, plus the repo's watchlist/early-filer/health-report steps built around those downloads.
- `skill-company-investorconference-ir-pdf-md`: downloads InvestorConference/company IR presentation PDFs under the `InvestorConference` repo.
- Both skills use `skill-mac-mini-ocr` as the shared PDF-to-Markdown converter, but their PDF acquisition steps and source directories are different.

## Fetch Pipeline Overview

| Step | Purpose | Owner (source of truth) |
|---|---|---|
| PDF download + Markdown sidecar | Download a company/year/quarter's official MOPS filing and convert to Markdown | `scripts/run_mops_fetch.py` (this skill) → `mops_downloader` package |
| Batch-all download | Loop the download+convert step over every company in the watchlist CSV | `MOPS/DownloadAll.py` (calls this skill's runner per company) |
| Watchlist refresh | Refresh `StockID_TWSE_TPEX.csv` / `StockID_TWSE_TPEX_focus.csv` from the canonical watchlist source | `MOPS/Get觀察名單.py` |
| Early-filer detection | Find companies whose report is likely already filed ahead of the general deadline (e.g. TSMC), based on the InvestorConference earnings calendar | `MOPS/scripts/check_early_filers.py` |
| Health / matrix reporting | Summarize PDF/Markdown coverage, TODO:OCR backlog, and produce `mops_matrix_latest.csv` | `MOPS/scripts/generate_mops_health.py` |

The download+convert step is implemented inside this skill because it is the one step shared with the OCR pipeline. The other four steps stay as repo-local scripts under `MOPS/` — do not port their logic into this skill; call them directly, and document new fetch behavior here so the pipeline stays discoverable as one whole.

## Standard Workflow (download + convert)

Run from the `MOPS` repo root:

```bash
python ../skills/common/skill-mops-fetch/scripts/run_mops_fetch.py <company_id> <year> <quarter>
```

Examples:

```bash
python ../skills/common/skill-mops-fetch/scripts/run_mops_fetch.py 2382 2025 all
python ../skills/common/skill-mops-fetch/scripts/run_mops_fetch.py 2382 2026 1 --skip-download
python ../skills/common/skill-mops-fetch/scripts/run_mops_fetch.py 2330 2025 4 --only-missing-files
```

The runner does this in order:

1. Verify it is inside the `MOPS` repo.
2. Unless `--skip-download` is passed, run `python -m mops_downloader.cli --company_id <id> --year <year> --quarter <quarter>`.
3. Find target PDFs under `downloads/<company_id>/` matching the requested year/quarter.
4. Convert missing or stale Markdown sidecars through `skill-mac-mini-ocr/scripts/pdf_fallback.py`.
5. Unless `--no-refine` is passed, repair `TODO:OCR` pages with `skill-mac-mini-ocr/scripts/refine_todo_ocr.py` when the Mac-mini OCR API is reachable.
6. Report total PDFs, missing MD sidecars, invalid PDFs, converted files, and remaining `TODO:OCR` counts.

## Batch, watchlist, early-filer, and health steps

These are run directly (not through the runner script above), but are part of the same fetch pipeline this skill documents:

```bash
# Batch-all download+convert for a year/quarter across the whole watchlist
python DownloadAll.py --year 2025 --quarter 1 --only-missing-files

# Refresh the watchlist CSVs
python Get觀察名單.py

# Find and download early filers (e.g. run daily in CI ahead of the general deadline)
python scripts/check_early_filers.py --lookback-days 14

# Regenerate coverage/health summary + latest matrix CSV
python scripts/generate_mops_health.py
```

`.github/workflows/Download.yaml` and `.github/workflows/EarlyFilerDownload.yaml` wire these together on a schedule aligned to MOPS filing deadlines.

## Source Rules

- PDF acquisition belongs to the existing MOPS downloader package: `mops_downloader` (invoked via `python -m mops_downloader.cli`). Do not reimplement MOPS web navigation in scratch scripts.
- PDF-to-MD conversion belongs to `skill-mac-mini-ocr`; do not use ad hoc OCR clients or hard-coded local machine paths.
- Markdown files must be same-stem sidecars, e.g. `downloads/2382/202504_2382_AI1.pdf` -> `downloads/2382/202504_2382_AI1.md`.
- Preserve source filename, page markers, `TODO:OCR`, and `OCR:done` markers for downstream auditability.
- Treat annual reports (`AI3`) and quarterly financial reports (`AI1`/`AI2`) as target financial-report PDFs.
- Batch orchestration, watchlist refresh, early-filer detection, and health reporting stay as repo-local scripts (see table above); extend those scripts directly rather than duplicating their logic inside this skill.

## Replaces

This skill replaces `skill-company-mops-financialreport-pdf-md` (renamed and widened in scope to cover the full MOPS fetch pipeline, not just PDF-to-MD). Existing repo-local scripts `scripts/pdf_to_md.py`, `scripts/batch_convert.py`, `scripts/mops_downloader.py`, and `mops_downloader/skill_cli.py` are deprecated compatibility wrappers that delegate to this skill's runner; do not add new conversion or download logic to them.

## Expected Outputs

For each target PDF:

- `downloads/<company_id>/<YYYYQQ>_<company_id>_<report_type>.pdf`
- `downloads/<company_id>/<YYYYQQ>_<company_id>_<report_type>.md`

The Markdown should begin with provenance similar to:

```html
<!-- mac-mini-ocr:hybrid-base source="...pdf" extractor="fitz" generated="YYYY-MM-DD" -->
```

If OCR could not finish, the Markdown must retain machine-readable `TODO:OCR` markers so the file can be repaired later with `skill-mac-mini-ocr/scripts/refine_todo_ocr.py`.

## Validation

After running, check:

```bash
python ../skills/common/skill-mops-fetch/scripts/run_mops_fetch.py <company_id> <year> <quarter> --skip-download
rg "TODO:OCR|OCR:done|mac-mini-ocr:hybrid-base" downloads/<company_id>/*.md
python scripts/generate_mops_health.py
```

Successful output is not necessarily zero `TODO:OCR`; if Mac-mini is offline, a partial Markdown with TODO markers is acceptable and better than silently missing MD.
