#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_fallback.py — 非 OCR 的本地 PDF → Markdown 退援轉換

當 Mac-mini OCR API 無法使用（離線、不在 Tailscale 網內）時，
使用 pypdf 直接抽取 PDF 內嵌的文字層轉為 Markdown。

無法抽取文字的頁面（通常是掃描影像頁）會插入 TODO:OCR 標記，
之後 Mac-mini 恢復連線時，可用 refine_todo_ocr.py 只補做這些頁面。

TODO:OCR 標記格式（機器可讀，供 refine_todo_ocr.py 解析）：

    <!-- TODO:OCR source="report.pdf" page=3 reason=scanned-page -->

reason 值：
- scanned-page    ：整頁幾乎無文字層，需要 OCR
- embedded-images ：頁面有文字層但含內嵌圖片，圖中文字可能遺漏

使用方式：

    pip install pypdf
    python scripts/pdf_fallback.py <file.pdf> [--min-chars 20] > output.md
"""
import argparse
import datetime
import platform
import sys
from pathlib import Path

from pypdf import PdfReader

# Fix Windows console encoding for Chinese characters
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
        # 圖片列舉失敗（例如缺少 Pillow 支援的格式）時視為未知，不標記
        return False


def extract_pdf_to_markdown(pdf_path: str | Path, min_chars: int = 20) -> str:
    """
    以 pypdf 抽取 PDF 文字層轉為 Markdown（非 OCR）。

    :param pdf_path: PDF 檔案路徑
    :param min_chars: 頁面文字少於此字元數即視為掃描頁，標記 TODO:OCR
    :return: Markdown 文本（含 PAGE 與 TODO:OCR 標記）
    """
    path_obj = Path(pdf_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    reader = PdfReader(str(path_obj))
    source = path_obj.name
    today = datetime.date.today().isoformat()

    parts = [
        f'<!-- mac-mini-ocr:fallback source="{source}" generated="{today}" -->',
        "",
        f"# {source}（非 OCR 文字抽取，Mac-mini 離線退援模式）",
        "",
    ]

    todo_count = 0
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""

        parts.append(PAGE_MARKER.format(page=idx))
        parts.append(f"## 第 {idx} 頁")
        parts.append("")

        if len(text) < min_chars:
            todo_count += 1
            parts.append(TODO_MARKER.format(source=source, page=idx, reason="scanned-page"))
            parts.append("> ⚠️ TODO:OCR — 此頁幾乎沒有可抽取的文字層（可能為掃描影像），"
                         "待 Mac-mini 恢復連線後以 refine_todo_ocr.py 補轉錄。")
        else:
            parts.append(text)
            if _page_has_images(page):
                todo_count += 1
                parts.append("")
                parts.append(TODO_MARKER.format(source=source, page=idx, reason="embedded-images"))
                parts.append("> ⚠️ TODO:OCR — 此頁含內嵌圖片，圖中文字未包含在上方抽取結果。")
        parts.append("")

    if todo_count:
        print(f"[pdf_fallback] {source}：{len(reader.pages)} 頁，其中 {todo_count} 頁標記 TODO:OCR",
              file=sys.stderr)
    else:
        print(f"[pdf_fallback] {source}：{len(reader.pages)} 頁，全部成功抽取文字層", file=sys.stderr)

    return "\n".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="非 OCR 的本地 PDF → Markdown 退援轉換")
    parser.add_argument("pdf", help="PDF 檔案路徑")
    parser.add_argument("--min-chars", type=int, default=20,
                        help="頁面文字少於此字元數即標記 TODO:OCR（預設 20）")
    args = parser.parse_args()

    try:
        print(extract_pdf_to_markdown(args.pdf, min_chars=args.min_chars))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
