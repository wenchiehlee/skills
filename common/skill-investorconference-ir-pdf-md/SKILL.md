---
name: skill-investorconference-ir-pdf-md
description: >-
  Fetch official InvestorConference IR PDF materials for a target stock/year/quarter using the
  InvestorConference ingest skill, then convert those PDFs to Markdown through the repo-local
  Mac-mini OCR hybrid PDF pipeline. Use when IR PDF sidecar Markdown is missing, stale, or needs
  repair before digest, segment-weight, or research extraction workflows.
---

# InvestorConference IR PDF to MD Skill

## Role

You maintain `InvestorConference` source material quality. The goal is not just to create an `.md` file; it is to ensure the official IR PDF exists, the Markdown sidecar traces back to that PDF, and any OCR gaps are explicit through `TODO:OCR` / `OCR:done` markers.

## Standard Workflow

Run from the `InvestorConference` repo root:

```bash
python skills/skill-investorconference-ir-pdf-md/scripts/run_ir_pdf_to_md.py <stock_id> <year> <quarter>
```

Examples:

```bash
python skills/skill-investorconference-ir-pdf-md/scripts/run_ir_pdf_to_md.py 2354 2026 1
python skills/skill-investorconference-ir-pdf-md/scripts/run_ir_pdf_to_md.py 2330 2026 2 --skip-ingest
```

The runner does this in order:

1. Verify it is inside the `InvestorConference` repo.
2. Unless `--skip-ingest` is passed, run `skills/skill-investorconference-ingest/scripts/ingest.py <stock_id> <year> <quarter>` to fetch official IR PDFs and refresh material metadata.
3. Run `skills/mac-mini-ocr/scripts/convert_ir_pdfs.py <stock_id>` to convert company PDFs to Markdown via the Mac-mini OCR hybrid pipeline.
4. Verify target quarter PDF/MD sidecars under `data/{stock_id}/`.
5. Report missing PDF, missing MD, invalid PDF, and remaining `TODO:OCR` counts.

## Source Rules

- PDF acquisition belongs to `skill-investorconference-ingest`; do not reimplement company IR/MOPS/Playwright download logic in scratch scripts.
- PDF-to-MD conversion belongs to `skills/mac-mini-ocr`; do not call ad hoc OCR clients or hard-coded local Windows paths.
- Markdown files must be same-stem sidecars for PDFs, e.g. `data/2357/2357_2026_q1_ir.pdf` -> `data/2357/2357_2026_q1_ir.md`.
- Prefer official company IR / MOPS / TWSE materials. Third-party transcripts do not replace official IR PDF sidecars.
- Keep `source_md`, PDF filename, page markers, `TODO:OCR`, and `OCR:done` markers intact for downstream auditability.

## Replaces

This skill is the maintained path for IR PDF fetch and PDF-to-MD work. Avoid using repo-local scratch scripts such as one-off OCR tests, hard-coded per-company OCR scripts, or direct imports from a user-machine path. If a one-off repair is needed, implement it by extending this skill or `skills/mac-mini-ocr`, not by adding new scratch OCR scripts.

## Expected Outputs

For each target PDF:

- `data/{stock_id}/{stock_id}_{year}_q{quarter}_*_ir*.pdf`
- `data/{stock_id}/{stock_id}_{year}_q{quarter}_*_ir*.md`

The Markdown should begin with provenance similar to:

```html
<!-- mac-mini-ocr:hybrid-base source="...pdf" extractor="fitz" generated="YYYY-MM-DD" -->
```

If OCR could not finish, the Markdown must retain machine-readable `TODO:OCR` markers so `skills/mac-mini-ocr/scripts/refine_todo_ocr.py` can repair only those pages later.

## Validation

After running, check:

```bash
python skills/skill-investorconference-ir-pdf-md/scripts/run_ir_pdf_to_md.py <stock_id> <year> <quarter> --skip-ingest
rg "TODO:OCR|OCR:done|mac-mini-ocr:hybrid-base" data/<stock_id>/*.md
```

Successful output is not necessarily zero `TODO:OCR`; if Mac-mini is offline, a partial Markdown with TODO markers is acceptable and more useful than silently missing MD.
