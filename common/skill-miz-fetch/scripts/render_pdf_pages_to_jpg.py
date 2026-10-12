#!/usr/bin/env python3
"""Render selected 1-based PDF pages as JPGs for a book's images/ directory."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_pages(value: str, page_count: int) -> list[int]:
    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = (int(v.strip()) for v in part.split("-", 1))
            if first > last:
                raise ValueError(f"Invalid page range: {part}")
            pages.update(range(first, last + 1))
        else:
            pages.add(int(part))
    if not pages:
        raise ValueError("Specify at least one page, e.g. 1,18,42 or 1-3,18")
    invalid = sorted(page for page in pages if page < 1 or page > page_count)
    if invalid:
        raise ValueError(f"Pages outside PDF range 1-{page_count}: {invalid}")
    return sorted(pages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--pages", required=True, help="1-based pages/ranges, e.g. 1,18,42 or 1-3,18")
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--overwrite", action="store_true", help="replace JPGs that already exist")
    args = parser.parse_args()
    if args.dpi < 36 or args.dpi > 600:
        parser.error("--dpi must be between 36 and 600")
    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError as exc:
            parser.error("PyMuPDF is required; install it with: pip install PyMuPDF")

    try:
        document = pymupdf.open(args.pdf)
        pages = parse_pages(args.pages, document.page_count)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    destinations = [args.out_dir / f"page_{number:03d}.jpg" for number in pages]
    collisions = [path for path in destinations if path.exists()]
    if collisions and not args.overwrite:
        parser.error(
            "refusing to overwrite existing JPGs: "
            + ", ".join(str(path) for path in collisions)
            + "; pass --overwrite to replace them"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    scale = args.dpi / 72
    matrix = pymupdf.Matrix(scale, scale)
    for number in pages:
        page = document[number - 1]
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        destination = args.out_dir / f"page_{number:03d}.jpg"
        pixmap.save(destination)
        print(f"Saved {destination}")


if __name__ == "__main__":
    main()
