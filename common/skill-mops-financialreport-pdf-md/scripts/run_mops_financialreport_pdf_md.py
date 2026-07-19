#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download MOPS financial-report PDFs and convert them to Markdown via Mac-mini OCR."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PDF_MAGIC = b"%PDF-"
REPORT_TYPES = {"AI1", "AI2", "AI3", "AE2"}


def find_mops_repo() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        if (candidate / "mops_downloader").is_dir() and (candidate / "scripts" / "mops_downloader.py").is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find MOPS repo root. Run inside the MOPS repo.")


def find_mac_mini_ocr_skill(repo: Path) -> Path:
    candidates = [
        repo / "skills" / "mac-mini-ocr",
        repo / "skills" / "skill-mac-mini-ocr",
        repo / "skills" / "common" / "skill-mac-mini-ocr",
        repo.parent / "skills" / "common" / "skill-mac-mini-ocr",
        Path(__file__).resolve().parents[2] / "skill-mac-mini-ocr",
        Path(__file__).resolve().parents[3] / "skill-mac-mini-ocr",
    ]
    for candidate in candidates:
        if (candidate / "scripts" / "pdf_fallback.py").is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find skill-mac-mini-ocr. Expected it in repo/skills or ../skills/common.")


def run_command(cmd: list[str], cwd: Path, allow_failure: bool = False) -> int:
    print("$ " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode and not allow_failure:
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result.returncode


def valid_pdf(path: Path) -> bool:
    try:
        return path.read_bytes()[:5] == PDF_MAGIC
    except OSError:
        return False


def quarter_prefixes(year: int, quarter: str) -> list[str]:
    q = str(quarter).lower().removeprefix("q")
    if q == "all":
        return [f"{year}0{i}" for i in range(1, 5)]
    return [f"{year}0{int(q)}"]


def target_pdfs(download_dir: Path, company_id: str, year: int, quarter: str) -> list[Path]:
    prefixes = quarter_prefixes(year, quarter)
    pdfs: list[Path] = []
    for pdf in sorted(download_dir.glob("*.pdf")):
        parts = pdf.stem.split("_")
        if len(parts) < 3:
            continue
        period, stock, report_type = parts[0], parts[1], parts[2]
        if stock == company_id and report_type in REPORT_TYPES and any(period.startswith(prefix) for prefix in prefixes):
            pdfs.append(pdf)
    return pdfs


def needs_conversion(pdf: Path, force: bool) -> bool:
    md = pdf.with_suffix(".md")
    if force or not md.is_file():
        return True
    try:
        return md.stat().st_mtime < pdf.stat().st_mtime
    except OSError:
        return True


def write_markdown_with_fallback(pdf: Path, md: Path, fallback_script: Path, min_chars: int) -> None:
    cmd = [sys.executable, str(fallback_script), str(pdf), "--min-chars", str(min_chars)]
    print("$ " + " ".join(cmd) + f" > {md}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    md.write_text(result.stdout, encoding="utf-8", newline="\n")


def count_todo(md: Path) -> int:
    try:
        return md.read_text(encoding="utf-8", errors="replace").count("TODO:OCR")
    except OSError:
        return 0


def summarize(download_dir: Path, pdfs: list[Path], converted: list[Path], invalid: list[Path]) -> int:
    missing_md = [pdf.with_suffix(".md") for pdf in pdfs if not pdf.with_suffix(".md").is_file()]
    todo_count = sum(count_todo(pdf.with_suffix(".md")) for pdf in pdfs if pdf.with_suffix(".md").is_file())

    print("\n=== MOPS Financial Report PDF to MD Summary ===")
    print(f"Downloads dir: {download_dir}")
    print(f"Target PDFs: {len(pdfs)}")
    print(f"Converted/updated MD files: {len(converted)}")
    print(f"Missing MD sidecars: {len(missing_md)}")
    print(f"Invalid PDFs: {len(invalid)}")
    print(f"Remaining TODO:OCR markers: {todo_count}")

    if pdfs:
        print("\nTargets:")
        for pdf in pdfs:
            md = pdf.with_suffix(".md")
            status = "md-ok" if md.is_file() else "md-missing"
            todo = count_todo(md) if md.is_file() else 0
            print(f"- {pdf.name} -> {md.name} [{status}, TODO:OCR={todo}]")
    else:
        print("\nNo target PDFs matched the requested company/year/quarter.")

    if invalid:
        print("\nInvalid PDFs:")
        for pdf in invalid:
            print(f"- {pdf.name}")
    if missing_md:
        print("\nMissing MD sidecars:")
        for md in missing_md:
            print(f"- {md.name}")

    return 1 if invalid or missing_md or not pdfs else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download MOPS financial-report PDFs and convert to Markdown via skill-mac-mini-ocr.")
    parser.add_argument("company_id", help="Taiwan stock company ID, e.g. 2382")
    parser.add_argument("year", type=int, help="Reporting year in Western format, e.g. 2025")
    parser.add_argument("quarter", help='Quarter: 1, 2, 3, 4, or "all"')
    parser.add_argument("--skip-download", action="store_true", help="Only convert existing PDFs and verify outputs.")
    parser.add_argument("--only-missing-files", action="store_true", help="Pass downloader skip mode for existing files >100KB.")
    parser.add_argument("--force-convert", action="store_true", help="Rebuild Markdown even if the sidecar is newer than the PDF.")
    parser.add_argument("--no-refine", action="store_true", help="Do not call refine_todo_ocr.py after fallback conversion.")
    parser.add_argument("--min-chars", type=int, default=20, help="Minimum page text length before marking TODO:OCR.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    repo = find_mops_repo()
    ocr_skill = find_mac_mini_ocr_skill(repo)
    download_dir = repo / "downloads" / args.company_id
    download_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_download:
        cmd = [
            sys.executable,
            "-m",
            "mops_downloader.cli",
            "--company_id",
            args.company_id,
            "--year",
            str(args.year),
            "--quarter",
            str(args.quarter),
            "--log_level",
            args.log_level,
        ]
        if args.only_missing_files:
            cmd.append("--only-missing-files")
        run_command(cmd, repo)

    pdfs = target_pdfs(download_dir, args.company_id, args.year, args.quarter)
    invalid = [pdf for pdf in pdfs if not valid_pdf(pdf)]
    fallback_script = ocr_skill / "scripts" / "pdf_fallback.py"
    refine_script = ocr_skill / "scripts" / "refine_todo_ocr.py"

    converted: list[Path] = []
    for pdf in pdfs:
        if pdf in invalid:
            continue
        md = pdf.with_suffix(".md")
        if not needs_conversion(pdf, args.force_convert):
            continue
        write_markdown_with_fallback(pdf, md, fallback_script, args.min_chars)
        converted.append(md)

        if not args.no_refine and count_todo(md):
            run_command([sys.executable, str(refine_script), str(md), "--pdf", str(pdf)], repo, allow_failure=True)

    return summarize(download_dir, pdfs, converted, invalid)


if __name__ == "__main__":
    raise SystemExit(main())
