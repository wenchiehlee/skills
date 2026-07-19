#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch InvestorConference IR PDFs and convert them to Markdown via Mac-mini OCR."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PDF_MAGIC = b"%PDF-"


def find_mac_mini_converter(repo: Path) -> Path | None:
    for skill_dir in ("skill-mac-mini-ocr", "mac-mini-ocr"):
        converter = repo / "skills" / skill_dir / "scripts" / "convert_ir_pdfs.py"
        if converter.is_file():
            return converter
    return None


def find_repo_root() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        ingest = candidate / "skills" / "skill-investorconference-ingest" / "scripts" / "ingest.py"
        if (candidate / "audio_manifest.json").exists() or (ingest.is_file() and find_mac_mini_converter(candidate)):
            return candidate.resolve()
    raise SystemExit("Cannot find InvestorConference repo root. Run inside InvestorConference.")


def run_command(cmd: list[str], cwd: Path) -> None:
    print("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def quarter_prefix(stock_id: str, year: str, quarter: str) -> str:
    q = str(quarter).lower().removeprefix("q")
    return f"{stock_id}_{year}_q{q}"


def is_valid_pdf(path: Path) -> bool:
    try:
        return path.read_bytes()[:5] == PDF_MAGIC
    except OSError:
        return False


def target_pdfs(data_dir: Path, prefix: str) -> list[Path]:
    return sorted(
        p for p in data_dir.glob(f"{prefix}*.pdf")
        if "ir" in p.stem.lower() or "presentation" in p.stem.lower() or "deck" in p.stem.lower()
    )


def stage_tmp_pdfs(repo: Path, data_dir: Path, prefix: str) -> list[Path]:
    """Move IR PDFs left in tmp/ by ingest.py into data/<stock>/ for OCR."""
    tmp_dir = repo / "tmp"
    staged: list[Path] = []
    if not tmp_dir.is_dir():
        return staged

    for src in sorted(tmp_dir.glob(f"{prefix}*.pdf")):
        if "ir" not in src.stem.lower() and "presentation" not in src.stem.lower() and "deck" not in src.stem.lower():
            continue
        dest = data_dir / src.name
        if dest.exists():
            src.unlink()
            staged.append(dest)
            continue
        shutil.move(str(src), str(dest))
        staged.append(dest)

    if staged:
        print("\n=== Staged IR PDFs from tmp/ into data dir ===")
        for pdf in staged:
            print(f"- {pdf.name}")
    return staged


def summarize_outputs(data_dir: Path, prefix: str) -> int:
    pdfs = target_pdfs(data_dir, prefix)
    all_quarter_pdfs = sorted(data_dir.glob(f"{prefix}*.pdf"))
    mds = sorted(data_dir.glob(f"{prefix}*.md"))
    missing_md = []
    invalid_pdf = []
    todo_count = 0

    for pdf in pdfs:
        if not is_valid_pdf(pdf):
            invalid_pdf.append(pdf)
        md = pdf.with_suffix(".md")
        if not md.is_file():
            missing_md.append(md)
        else:
            todo_count += md.read_text(encoding="utf-8", errors="replace").count("TODO:OCR")

    print("\n=== IR PDF to MD Summary ===")
    print(f"Data dir: {data_dir}")
    print(f"Quarter PDFs: {len(all_quarter_pdfs)}")
    print(f"Target IR/deck PDFs: {len(pdfs)}")
    print(f"Quarter MD files: {len(mds)}")
    print(f"Missing MD sidecars: {len(missing_md)}")
    print(f"Invalid PDFs: {len(invalid_pdf)}")
    print(f"Remaining TODO:OCR markers: {todo_count}")

    if pdfs:
        print("\nTarget PDFs:")
        for pdf in pdfs:
            md = pdf.with_suffix(".md")
            status = "md-ok" if md.is_file() else "md-missing"
            print(f"- {pdf.name} -> {md.name} [{status}]")
    else:
        print("\nNo target IR/deck PDFs found for this quarter prefix.")

    if missing_md:
        print("\nMissing MD sidecars:")
        for md in missing_md:
            print(f"- {md.name}")
    if invalid_pdf:
        print("\nInvalid PDFs:")
        for pdf in invalid_pdf:
            print(f"- {pdf.name}")

    return 1 if invalid_pdf or missing_md or not pdfs else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch InvestorConference IR PDFs and convert them to Markdown via Mac-mini OCR.")
    parser.add_argument("stock_id")
    parser.add_argument("year")
    parser.add_argument("quarter")
    parser.add_argument("--skip-ingest", action="store_true", help="Only convert existing PDFs and verify outputs.")
    parser.add_argument("--push", action="store_true", help="Pass --push to ingest.py when fetching materials.")
    args = parser.parse_args()

    repo = find_repo_root()
    stock_id = args.stock_id.upper() if not args.stock_id.isdigit() else args.stock_id
    q = str(args.quarter).lower().removeprefix("q")
    prefix = quarter_prefix(stock_id, args.year, q)
    data_dir = repo / "data" / stock_id
    data_dir.mkdir(parents=True, exist_ok=True)

    ingest = repo / "skills" / "skill-investorconference-ingest" / "scripts" / "ingest.py"
    converter = find_mac_mini_converter(repo)
    if converter is None:
        raise SystemExit("Cannot find skill-mac-mini-ocr converter under repo/skills.")

    if not args.skip_ingest:
        cmd = [sys.executable, str(ingest), stock_id, str(args.year), q]
        if args.push:
            cmd.append("--push")
        run_command(cmd, repo)

    stage_tmp_pdfs(repo, data_dir, prefix)
    run_command([sys.executable, str(converter), stock_id], repo)
    return summarize_outputs(data_dir, prefix)


if __name__ == "__main__":
    raise SystemExit(main())
