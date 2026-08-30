#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_fallback.py — PDF text-layer extraction with TODO:OCR markers.

The converter keeps clean embedded PDF text first. Pages with little/no text are
marked TODO:OCR so refine_todo_ocr.py can send only those pages to Mac-mini OCR.
"""
import argparse
import datetime
import platform
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional dependency
    fitz = None


if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PAGE_MARKER = "<!-- PAGE:{page} -->"
TODO_MARKER = '<!-- TODO:OCR source="{source}" page={page} reason={reason} -->'


def _page_has_images(page) -> bool:
    try:
        return len(page.images) > 0
    except Exception:
        return False


def _extract_with_pypdf(path_obj: Path, min_chars: int, mark_embedded_images: bool) -> tuple[list[str], int, int]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install pypdf for fallback PDF text extraction") from exc

    reader = PdfReader(str(path_obj))
    parts: list[str] = []
    todo_count = 0
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""

        parts.extend([PAGE_MARKER.format(page=idx), f"## 第 {idx} 頁", ""])
        if len(text) < min_chars:
            todo_count += 1
            parts.append(TODO_MARKER.format(source=path_obj.name, page=idx, reason="scanned-page"))
            parts.append("> TODO:OCR - 此頁幾乎沒有可抽取的文字層，待 Mac-mini OCR 補轉錄。")
        else:
            parts.append(text)
            if mark_embedded_images and _page_has_images(page):
                todo_count += 1
                parts.append("")
                parts.append(TODO_MARKER.format(source=path_obj.name, page=idx, reason="embedded-images"))
                parts.append("> TODO:OCR - 此頁含內嵌圖片，圖中文字可能未包含在上方抽取結果。")
        parts.append("")
    return parts, len(reader.pages), todo_count


def _table_cell_to_text(value) -> str:
    """Render one extracted table cell. None means "part of a merged cell
    above/left" per PyMuPDF's table.extract() convention — must stay blank,
    not be filled in, or every row in a vertically-merged column ends up
    showing a duplicate copy of the first row's text (a real bug we hit in
    table.to_markdown(), which fills merged cells instead of leaving them
    blank)."""
    if value is None:
        return ""
    return str(value).replace("\n", "; ").replace("|", "/").strip()


def _find_tables(page):
    """find_tables() wrapper; returns a list of table objects (possibly empty)."""
    try:
        return list(page.find_tables().tables)
    except Exception:
        return []


def _tables_markdown(tables) -> list[str]:
    """Render already-detected tables as Markdown tables.

    Numeric financial tables (monthly sales, income statements, etc.) come out
    of plain fitz text extraction as an unstructured flat list of numbers with
    no row/column alignment. find_tables() recovers the grid so downstream
    readers (and digest/segment-weight extraction) get an actual table instead
    of having to guess which number belongs to which row.

    Renders from table.extract() (raw cell values) rather than
    table.to_markdown(), because to_markdown() incorrectly back-fills merged
    cells with a repeated copy of a neighboring row's text.
    """
    out: list[str] = []
    for i, table in enumerate(tables, start=1):
        try:
            rows = table.extract()
        except Exception:
            continue
        if not rows or len(rows) < 2:
            continue
        col_count = max(len(r) for r in rows)
        md_rows = [
            "| " + " | ".join(_table_cell_to_text(r[c]) if c < len(r) else "" for c in range(col_count)) + " |"
            for r in rows
        ]
        header = md_rows[0]
        sep = "|" + "|".join(["---"] * col_count) + "|"
        out.append(f"**表格 {i}（自動偵測，儲存格合併已保留空白,不做重複填值)：**")
        out.append(header)
        out.append(sep)
        out.extend(md_rows[1:])
        out.append("")
    return out


def _bbox_overlap_ratio(block_bbox, table_bbox) -> float:
    """Fraction of block_bbox's area covered by table_bbox."""
    bx0, by0, bx1, by1 = block_bbox
    tx0, ty0, tx1, ty1 = table_bbox
    ix0, iy0 = max(bx0, tx0), max(by0, ty0)
    ix1, iy1 = min(bx1, tx1), min(by1, ty1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    block_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
    return inter / block_area


def _non_table_text(page, tables) -> str:
    """Page text with blocks that fall inside a detected table's bbox removed.

    Prevents the same numbers appearing twice in the Markdown: once as a flat
    unstructured text dump, once as the structured Markdown table. Only
    surrounding prose (titles, captions, notes) stays in the plain-text part.
    """
    if not tables:
        return (page.get_text("text") or "").strip()

    table_bboxes = [tuple(t.bbox) for t in tables]
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return (page.get_text("text") or "").strip()

    kept = []
    for b in blocks:
        x0, y0, x1, y1, block_text = b[0], b[1], b[2], b[3], b[4]
        if any(_bbox_overlap_ratio((x0, y0, x1, y1), tb) > 0.5 for tb in table_bboxes):
            continue
        if block_text.strip():
            kept.append(block_text.strip())
    return "\n".join(kept).strip()


def _extract_with_fitz(path_obj: Path, min_chars: int, mark_embedded_images: bool) -> tuple[list[str], int, int]:
    if fitz is None:
        raise RuntimeError("PyMuPDF/fitz is not available")

    doc = fitz.open(str(path_obj))
    parts: list[str] = []
    todo_count = 0
    for idx, page in enumerate(doc, start=1):
        text = (page.get_text("text") or "").strip()
        image_count = len(page.get_images(full=True))

        parts.extend([PAGE_MARKER.format(page=idx), f"## 第 {idx} 頁", ""])
        if len(text) < min_chars:
            todo_count += 1
            reason = "scanned-page" if image_count else "low-text"
            parts.append(TODO_MARKER.format(source=path_obj.name, page=idx, reason=reason))
            parts.append("> TODO:OCR - 此頁文字層不足，待 Mac-mini OCR 補轉錄。")
        else:
            tables = _find_tables(page)
            display_text = _non_table_text(page, tables) if tables else text
            if display_text:
                parts.append(display_text)
            table_md = _tables_markdown(tables)
            if table_md:
                if display_text:
                    parts.append("")
                parts.extend(table_md)
            if mark_embedded_images and image_count:
                todo_count += 1
                parts.append("")
                parts.append(TODO_MARKER.format(source=path_obj.name, page=idx, reason="embedded-images"))
                parts.append("> TODO:OCR - 此頁含內嵌圖片，圖中文字可能未包含在上方抽取結果。")
        parts.append("")
    return parts, doc.page_count, todo_count


def extract_pdf_to_markdown(
    pdf_path: str | Path,
    min_chars: int = 20,
    mark_embedded_images: bool = False,
) -> str:
    """Extract PDF text-layer Markdown and mark only pages that need OCR."""
    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    today = datetime.date.today().isoformat()
    extractor = "fitz"
    try:
        body_parts, page_count, todo_count = _extract_with_fitz(path_obj, min_chars, mark_embedded_images)
    except Exception as fitz_error:
        extractor = "pypdf"
        try:
            body_parts, page_count, todo_count = _extract_with_pypdf(path_obj, min_chars, mark_embedded_images)
        except Exception as pypdf_error:
            raise RuntimeError(f"PDF text extraction failed: fitz={fitz_error}; pypdf={pypdf_error}") from pypdf_error

    parts = [
        f'<!-- mac-mini-ocr:hybrid-base source="{path_obj.name}" extractor="{extractor}" generated="{today}" -->',
        "",
        f"# {path_obj.name}（文字層抽取，必要頁面以 Mac-mini OCR 補轉錄）",
        "",
    ]
    parts.extend(body_parts)

    if todo_count:
        print(f"[pdf_fallback] {path_obj.name}：{page_count} 頁，其中 {todo_count} 頁標記 TODO:OCR（extractor={extractor}）", file=sys.stderr)
    else:
        print(f"[pdf_fallback] {path_obj.name}：{page_count} 頁，全部成功抽取文字層（extractor={extractor}）", file=sys.stderr)

    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF 文字層抽取 + TODO:OCR 標記")
    parser.add_argument("pdf", help="PDF 檔案路徑")
    parser.add_argument("--min-chars", type=int, default=20, help="頁面文字少於此字元數即標記 TODO:OCR（預設 20）")
    parser.add_argument("--mark-embedded-images", action="store_true", help="含圖片且已有文字層的頁面也標記 TODO:OCR（預設不標記）")
    args = parser.parse_args()

    try:
        print(extract_pdf_to_markdown(args.pdf, min_chars=args.min_chars, mark_embedded_images=args.mark_embedded_images))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
