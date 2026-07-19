---
name: skill-mops-financialreport-pdf-md
description: >-
  Download Taiwan MOPS quarterly financial-report PDFs for a stock/year/quarter
  from the MOPS repo, then convert same-stem PDF sidecars to Markdown using the
  skill-mac-mini-ocr hybrid PDF/OCR pipeline. Use when MOPS downloads/*.pdf files
  are missing Markdown, stale, or need auditable TODO:OCR repair.
---

# MOPS Financial Report PDF to MD Skill

## Role

You maintain source quality for Taiwan MOPS financial reports in the `MOPS` repo. The goal is to ensure each downloaded official financial-report PDF has a same-stem Markdown sidecar, with provenance and explicit `TODO:OCR` / `OCR:done` markers when OCR is incomplete.

## Boundary

This skill is separate from `skill-investorconference-ir-pdf-md`.

- `skill-mops-financialreport-pdf-md`: downloads MOPS financial statement PDFs such as `AI1`, `AI2`, `AI3`, and `AE2` under `MOPS/downloads/<company_id>/`.
- `skill-investorconference-ir-pdf-md`: downloads InvestorConference/company IR presentation PDFs under the `InvestorConference` repo.
- Both skills use `skill-mac-mini-ocr` as the shared PDF-to-Markdown converter, but their PDF acquisition steps and source directories are different.

## Standard Workflow

Run from the `MOPS` repo root:

```bash
python ../skills/common/skill-mops-financialreport-pdf-md/scripts/run_mops_financialreport_pdf_md.py <company_id> <year> <quarter>
```

Examples:

```bash
python ../skills/common/skill-mops-financialreport-pdf-md/scripts/run_mops_financialreport_pdf_md.py 2382 2025 all
python ../skills/common/skill-mops-financialreport-pdf-md/scripts/run_mops_financialreport_pdf_md.py 2382 2026 1 --skip-download
python ../skills/common/skill-mops-financialreport-pdf-md/scripts/run_mops_financialreport_pdf_md.py 2330 2025 4 --only-missing-files
```

The runner does this in order:

1. Verify it is inside the `MOPS` repo.
2. Unless `--skip-download` is passed, run `scripts/mops_downloader.py --company_id <id> --year <year> --quarter <quarter>`.
3. Find target PDFs under `downloads/<company_id>/` matching the requested year/quarter.
4. Convert missing or stale Markdown sidecars through `skill-mac-mini-ocr/scripts/pdf_fallback.py`.
5. Unless `--no-refine` is passed, repair `TODO:OCR` pages with `skill-mac-mini-ocr/scripts/refine_todo_ocr.py` when the Mac-mini OCR API is reachable.
6. Report total PDFs, missing MD sidecars, invalid PDFs, converted files, and remaining `TODO:OCR` counts.

## Source Rules

- PDF acquisition belongs to the existing MOPS downloader package: `scripts/mops_downloader.py` / `mops_downloader`. Do not reimplement MOPS web navigation in scratch scripts.
- PDF-to-MD conversion belongs to `skill-mac-mini-ocr`; do not use ad hoc OCR clients or hard-coded local machine paths.
- Markdown files must be same-stem sidecars, e.g. `downloads/2382/202504_2382_AI1.pdf` -> `downloads/2382/202504_2382_AI1.md`.
- Preserve source filename, page markers, `TODO:OCR`, and `OCR:done` markers for downstream auditability.
- Treat annual reports (`AI3`) and quarterly financial reports (`AI1`/`AI2`) as target financial-report PDFs.

## Replaces

This skill is the maintained path for MOPS financial-report PDF fetch and PDF-to-MD conversion. Existing repo-local scripts such as `scripts/pdf_to_md.py` and `scripts/batch_convert.py` document legacy behavior, but new automation should call this skill or extend `skill-mac-mini-ocr` instead of adding another converter.

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
python ../skills/common/skill-mops-financialreport-pdf-md/scripts/run_mops_financialreport_pdf_md.py <company_id> <year> <quarter> --skip-download
rg "TODO:OCR|OCR:done|mac-mini-ocr:hybrid-base" downloads/<company_id>/*.md
```

Successful output is not necessarily zero `TODO:OCR`; if Mac-mini is offline, a partial Markdown with TODO markers is acceptable and better than silently missing MD.
