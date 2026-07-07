#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refine_todo_ocr.py — 補轉錄 Markdown 中標記 TODO:OCR 的頁面

掃描 pdf_fallback.py 產生的 Markdown，找出 TODO:OCR 標記的頁面，
從原始 PDF 抽出該頁成單頁 PDF，送 Mac-mini OCR API 轉錄，
並以 OCR 結果取代該頁內容（同時移除 TODO:OCR 標記）。

使用方式：

    # 只列出待補轉錄的頁面（離線可用）
    python scripts/refine_todo_ocr.py output.md --list

    # 補轉錄全部 TODO:OCR 頁面（需 Mac-mini 在線與 .env 設定）
    python scripts/refine_todo_ocr.py output.md --pdf path/to/report.pdf

    # 只補轉錄指定頁
    python scripts/refine_todo_ocr.py output.md --pdf report.pdf --pages 3,7

若未指定 --pdf，會以標記中的 source 檔名在 Markdown 檔所在目錄尋找。
"""
import argparse
import datetime
import platform
import re
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# Fix Windows console encoding for Chinese characters
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 讓 ocr_client 可以在「python scripts/refine_todo_ocr.py」與模組導入兩種情境下被找到
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_client import transcribe_document_to_markdown  # noqa: E402

TODO_RE = re.compile(r'<!-- TODO:OCR source="(?P<source>[^"]+)" page=(?P<page>\d+) reason=(?P<reason>[\w-]+) -->')
PAGE_SECTION_RE = r'<!-- PAGE:{page} -->.*?(?=<!-- PAGE:\d+ -->|\Z)'


def find_todo_pages(md_text: str) -> list[dict]:
    """回傳 Markdown 中所有 TODO:OCR 標記（source、page、reason）。"""
    return [
        {"source": m.group("source"), "page": int(m.group("page")), "reason": m.group("reason")}
        for m in TODO_RE.finditer(md_text)
    ]


def _extract_single_page_pdf(pdf_path: Path, page_num: int, dest_dir: Path) -> Path:
    """把 PDF 的第 page_num 頁（1-based）抽成單頁 PDF，回傳暫存檔路徑。"""
    reader = PdfReader(str(pdf_path))
    if not (1 <= page_num <= len(reader.pages)):
        raise ValueError(f"頁碼超出範圍：{page_num}（共 {len(reader.pages)} 頁）")
    writer = PdfWriter()
    writer.add_page(reader.pages[page_num - 1])
    out_path = dest_dir / f"{pdf_path.stem}.p{page_num}.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


def refine(md_path: Path, pdf_path: Path | None, pages: set[int] | None, dpi: int) -> int:
    """補轉錄 TODO:OCR 頁面，回傳成功補轉錄的頁數。"""
    md_text = md_path.read_text(encoding="utf-8")
    todos = find_todo_pages(md_text)
    if pages:
        todos = [t for t in todos if t["page"] in pages]
    if not todos:
        print("[refine] 沒有需要補轉錄的 TODO:OCR 頁面")
        return 0

    if pdf_path is None:
        pdf_path = md_path.parent / todos[0]["source"]
    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到原始 PDF：{pdf_path}（可用 --pdf 指定路徑）")

    today = datetime.date.today().isoformat()
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for todo in todos:
            page = todo["page"]
            print(f"[refine] OCR 第 {page} 頁（reason={todo['reason']}）…", file=sys.stderr)
            single = _extract_single_page_pdf(pdf_path, page, Path(tmp))
            ocr_md = transcribe_document_to_markdown(single, dpi=dpi).strip()

            new_section = (
                f"<!-- PAGE:{page} -->\n"
                f"## 第 {page} 頁\n\n"
                f'<!-- OCR:done source="{todo["source"]}" page={page} date="{today}" -->\n'
                f"{ocr_md}\n\n"
            )
            md_text, n = re.subn(
                PAGE_SECTION_RE.format(page=page), new_section, md_text, count=1, flags=re.DOTALL
            )
            if n == 0:
                # 沒有 PAGE 標記的 Markdown（非 pdf_fallback 產物）：只移除 TODO 標記行並附上結果
                print(f"[refine] 警告：找不到第 {page} 頁的 PAGE 標記，OCR 結果附加於文末", file=sys.stderr)
                md_text = TODO_RE.sub(
                    lambda m: "" if int(m.group("page")) == page else m.group(0), md_text
                )
                md_text += f"\n\n## 第 {page} 頁（OCR 補轉錄 {today}）\n\n{ocr_md}\n"
            done += 1

    md_path.write_text(md_text, encoding="utf-8", newline="\n")
    print(f"[refine] 完成：補轉錄 {done} 頁，已更新 {md_path}")
    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="補轉錄 Markdown 中標記 TODO:OCR 的頁面")
    parser.add_argument("markdown", help="pdf_fallback.py 產生的 Markdown 檔案")
    parser.add_argument("--pdf", help="原始 PDF 路徑（預設依標記中的 source 於 Markdown 同目錄尋找）")
    parser.add_argument("--pages", help="只處理指定頁碼，逗號分隔（例：3,7）")
    parser.add_argument("--dpi", type=int, default=200, help="OCR 渲染解析度（預設 200）")
    parser.add_argument("--list", action="store_true", help="只列出 TODO:OCR 頁面，不執行 OCR")
    args = parser.parse_args()

    md_file = Path(args.markdown)
    if not md_file.exists():
        print(f"Error: 找不到 {md_file}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        todos = find_todo_pages(md_file.read_text(encoding="utf-8"))
        if not todos:
            print("沒有 TODO:OCR 標記")
        for t in todos:
            print(f'{t["source"]} 第 {t["page"]} 頁（{t["reason"]}）')
        sys.exit(0)

    page_set = {int(p) for p in args.pages.split(",")} if args.pages else None
    try:
        refine(md_file, Path(args.pdf) if args.pdf else None, page_set, args.dpi)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
