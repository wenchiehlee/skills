#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-repair every downloads/<company>/*.md that still has TODO:OCR markers,
across the whole MOPS repo -- not scoped to one company/year/quarter like
run_mops_fetch.py. Reuses the same refine_todo_ocr.py call run_mops_fetch.py
makes per-file, so behavior (including graceful degradation when Mac-mini OCR
is offline, leaving TODO:OCR markers in place) is identical.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_mops_fetch import count_todo, find_mac_mini_ocr_skill, find_mops_repo, run_command  # noqa: E402


def find_pending(repo: Path) -> list[Path]:
    return sorted(md for md in repo.glob("downloads/*/*.md") if count_todo(md))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-repair all TODO:OCR markers across downloads/ via skill-mlx-api-client-ocr's refine_todo_ocr.py."
    )
    parser.add_argument("--dry-run", action="store_true", help="List pending files without calling the OCR API.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only repair the first N pending files (useful if the OCR API is slow/rate-limited).",
    )
    args = parser.parse_args()

    repo = find_mops_repo()
    pending = find_pending(repo)
    print(f"Found {len(pending)} Markdown file(s) with TODO:OCR markers under downloads/.")
    for md in pending:
        print(f"- {md.relative_to(repo)} (TODO:OCR x{count_todo(md)})")

    if args.dry_run or not pending:
        return 0

    ocr_skill = find_mac_mini_ocr_skill(repo)
    refine_script = ocr_skill / "scripts" / "refine_todo_ocr.py"

    targets = pending[: args.limit] if args.limit else pending
    repaired: list[Path] = []
    still_pending: list[Path] = []
    for md in targets:
        pdf = md.with_suffix(".pdf")
        if not pdf.is_file():
            print(f"  ! skip {md.name}: no matching PDF at {pdf.name}")
            still_pending.append(md)
            continue
        run_command([sys.executable, str(refine_script), str(md), "--pdf", str(pdf)], repo, allow_failure=True)
        (repaired if count_todo(md) == 0 else still_pending).append(md)

    print("\n=== Batch OCR refine summary ===")
    print(f"Attempted: {len(targets)}")
    print(f"Fully repaired (0 remaining TODO:OCR): {len(repaired)}")
    print(f"Still pending: {len(still_pending)}")
    for md in still_pending:
        print(f"- {md.relative_to(repo)} (TODO:OCR x{count_todo(md)})")

    return 1 if still_pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
