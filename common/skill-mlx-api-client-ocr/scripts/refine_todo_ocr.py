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
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# Fix Windows console encoding for Chinese characters
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 讓 ocr_client 可以在「python scripts/refine_todo_ocr.py」與模組導入兩種情境下被找到
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_client import (  # noqa: E402
    clean_ocr_markdown,
    transcribe_document_to_markdown,
)

TODO_RE = re.compile(r'<!-- TODO:OCR source="(?P<source>[^"]+)" page=(?P<page>\d+) reason=(?P<reason>[\w-]+) -->')
LEGACY_TODO_RE = re.compile(
    r'^> \*\*TODO:OCR\*\* - Page (?P<page>\d+) .*$|^> TODO:OCR - .*$',
    re.MULTILINE,
)
PAGE_SECTION_RE = r'<!-- PAGE:{page} -->.*?(?=<!-- PAGE:\d+ -->|\Z)'
OCR_TIMEOUT_RE = re.compile(
    r'<!-- OCR:timeout page=(?P<page>\d+) count=(?P<count>\d+) '
    r'last="(?P<last>[^"]+)" kind="(?P<kind>[\w-]+)" -->'
)


def _record_ocr_timeout(md_text: str, page: int, kind: str, timestamp: str) -> tuple[str, int]:
    """Persist a per-page timeout counter beside its TODO marker immediately."""
    section_re = re.compile(PAGE_SECTION_RE.format(page=page), re.DOTALL)
    section_match = section_re.search(md_text)
    section = section_match.group(0) if section_match else ""

    scope = section if section else md_text
    previous = next(
        (m for m in OCR_TIMEOUT_RE.finditer(scope) if int(m.group("page")) == page),
        None,
    )
    count = int(previous.group("count")) + 1 if previous else 1
    marker = (
        f'<!-- OCR:timeout page={page} count={count} '
        f'last="{timestamp}" kind="{kind}" -->'
    )

    if previous and section:
        updated_section = section[:previous.start()] + marker + section[previous.end():]
    elif previous:
        md_text = md_text[:previous.start()] + marker + md_text[previous.end():]
        updated_section = ""
    else:
        todo_match = next(
            (m for m in TODO_RE.finditer(section) if int(m.group("page")) == page),
            None,
        )
        if todo_match:
            insert_at = todo_match.end()
        else:
            page_marker = re.search(rf"<!-- PAGE:{page} -->", section)
            insert_at = page_marker.end() if page_marker else 0
        updated_section = section[:insert_at] + "\n" + marker + section[insert_at:]

    if section_match:
        md_text = md_text[:section_match.start()] + updated_section + md_text[section_match.end():]
    elif previous:
        pass
    else:
        # Support TODO comments in Markdown files without PAGE section wrappers.
        todo_match = next(
            (m for m in TODO_RE.finditer(md_text) if int(m.group("page")) == page),
            None,
        )
        if todo_match:
            md_text = md_text[:todo_match.end()] + "\n" + marker + md_text[todo_match.end():]
        else:
            md_text += f"\n{marker}\n"
    return md_text, count


def _timeout_metadata(md_text: str, page: int) -> tuple[int, str, str]:
    section_match = re.search(PAGE_SECTION_RE.format(page=page), md_text, re.DOTALL)
    scope = section_match.group(0) if section_match else md_text
    previous = next(
        (m for m in OCR_TIMEOUT_RE.finditer(scope) if int(m.group("page")) == page),
        None,
    )
    if not previous:
        return 0, "", ""
    return int(previous.group("count")), previous.group("last"), previous.group("kind")


def find_todo_pages(md_text: str) -> list[dict]:
    """回傳 Markdown 中所有 TODO:OCR 標記（source、page、reason）。"""
    todos = [
        {"source": m.group("source"), "page": int(m.group("page")), "reason": m.group("reason")}
        for m in TODO_RE.finditer(md_text)
    ]
    seen_pages = {todo["page"] for todo in todos}
    source_match = re.search(r'<!-- mac-mini-ocr:hybrid-base source="(?P<source>[^"]+)"', md_text)
    source = source_match.group("source") if source_match else ""

    current_page = None
    for line in md_text.splitlines():
        page_match = re.match(r'<!-- PAGE:(\d+) -->', line)
        if page_match:
            current_page = int(page_match.group(1))
            continue

        legacy_match = LEGACY_TODO_RE.match(line)
        if not legacy_match:
            continue

        page = int(legacy_match.group("page") or current_page or 0)
        if page and page not in seen_pages:
            todos.append({"source": source, "page": page, "reason": "legacy-todo"})
            seen_pages.add(page)
    return todos


def _remove_legacy_todo_for_page(md_text: str, page: int) -> str:
    def replace_section(match: re.Match) -> str:
        return LEGACY_TODO_RE.sub("", match.group(0))

    return re.sub(
        PAGE_SECTION_RE.format(page=page),
        replace_section,
        md_text,
        count=1,
        flags=re.DOTALL,
    )


def _render_single_page_png(pdf_path: Path, page_num: int, dest_dir: Path, dpi: int) -> Path:
    """把 PDF 的第 page_num 頁（1-based）渲染成 PNG，回傳暫存檔路徑。"""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install PyMuPDF to render OCR page images") from exc

    doc = fitz.open(str(pdf_path))
    if not (1 <= page_num <= doc.page_count):
        raise ValueError(f"頁碼超出範圍：{page_num}（共 {doc.page_count} 頁）")
    page = doc.load_page(page_num - 1)
    out_path = dest_dir / f"{pdf_path.stem}.p{page_num}.png"
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    pix.save(str(out_path))
    doc.close()
    return out_path


def _ocr_image_with_tesseract(image_path: Path) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError("Missing dependency: install tesseract for local OCR fallback")

    cmd = ["tesseract", str(image_path), "stdout", "-l", "chi_tra+eng", "--psm", "6"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"Tesseract OCR failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _extract_single_page_pdf(pdf_path: Path, page_num: int, dest_dir: Path) -> Path:
    """把 PDF 的第 page_num 頁（1-based）抽成單頁 PDF，回傳暫存檔路徑。"""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install pypdf to refine TODO:OCR pages") from exc

    reader = PdfReader(str(pdf_path))
    if not (1 <= page_num <= len(reader.pages)):
        raise ValueError(f"頁碼超出範圍：{page_num}（共 {len(reader.pages)} 頁）")
    writer = PdfWriter()
    writer.add_page(reader.pages[page_num - 1])
    out_path = dest_dir / f"{pdf_path.stem}.p{page_num}.pdf"
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path


def refine(md_path: Path, pdf_path: Path | None, pages: set[int] | None, dpi: int,
           engine: str | None = None) -> int:
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
            local_fallback = False
            try:
                single = _render_single_page_png(pdf_path, page, Path(tmp), dpi)
            except Exception as render_error:
                print(f"[refine] PNG 渲染失敗，改用單頁 PDF：{render_error}", file=sys.stderr)
                single = _extract_single_page_pdf(pdf_path, page, Path(tmp))

            if os.getenv("OCR_ENGINE", "").lower() == "tesseract":
                if single.suffix.lower() != ".png":
                    raise RuntimeError("OCR_ENGINE=tesseract requires a rendered PNG page")
                ocr_md = _ocr_image_with_tesseract(single).strip()
                local_fallback = True
            else:
                try:
                    ocr_md = clean_ocr_markdown(
                        transcribe_document_to_markdown(single, dpi=dpi, engine=engine)
                    ).strip()
                except Exception as remote_error:
                    timeout_kind = getattr(remote_error, "timeout_kind", None)
                    if timeout_kind:
                        timestamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
                        md_text, timeout_count = _record_ocr_timeout(
                            md_text, page, timeout_kind, timestamp
                        )
                        # Save before local fallback so the attempt remains recorded
                        # even if fallback fails or the process is interrupted.
                        md_path.write_text(md_text, encoding="utf-8", newline="\n")
                        print(
                            f"[refine] 第 {page} 頁 Mac-mini timeout 次數：{timeout_count} ({timeout_kind})",
                            file=sys.stderr,
                        )
                    if single.suffix.lower() != ".png":
                        raise
                    print(f"[refine] Mac-mini OCR 失敗，改用本機 Tesseract：{remote_error}", file=sys.stderr)
                    ocr_md = _ocr_image_with_tesseract(single).strip()
                    local_fallback = True

            if not ocr_md:
                ocr_md = "> OCR completed; no text recognized on this page."

            result_engine = "local-tesseract" if local_fallback else f"mac-mini-{engine or os.getenv('OCR_ENGINE', 'baidu')}"
            timeout_count, last_timeout, timeout_kind = _timeout_metadata(md_text, page)
            timeout_fields = (
                f' mac_mini_timeouts={timeout_count} '
                f'last_timeout="{last_timeout}" timeout_kind="{timeout_kind}"'
                if timeout_count
                else ""
            )
            new_section = (
                f"<!-- PAGE:{page} -->\n"
                f"## 第 {page} 頁\n\n"
                f'<!-- OCR:done source="{todo["source"]}" page={page} date="{today}" engine="{result_engine}"{timeout_fields} -->\n'
                f"{ocr_md}\n\n"
            )
            md_text, n = re.subn(
                PAGE_SECTION_RE.format(page=page),
                lambda _match: new_section,
                md_text,
                count=1,
                flags=re.DOTALL,
            )
            if n == 0:
                # 沒有 PAGE 標記的 Markdown（非 pdf_fallback 產物）：只移除 TODO 標記行並附上結果
                print(f"[refine] 警告：找不到第 {page} 頁的 PAGE 標記，OCR 結果附加於文末", file=sys.stderr)
                md_text = TODO_RE.sub(
                    lambda m: "" if int(m.group("page")) == page else m.group(0), md_text
                )
                md_text = LEGACY_TODO_RE.sub(
                    lambda m: "" if int(m.group("page") or 0) == page else m.group(0), md_text
                )
                md_text += f"\n\n## 第 {page} 頁（OCR 補轉錄 {today}）\n\n{ocr_md}\n"
            else:
                md_text = _remove_legacy_todo_for_page(md_text, page)
            done += 1
            # 每頁完成即存檔，中斷後重跑只會處理剩餘的 TODO:OCR 頁面
            md_path.write_text(md_text, encoding="utf-8", newline="\n")

    print(f"[refine] 完成：補轉錄 {done} 頁，已更新 {md_path}")
    return done


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="補轉錄 Markdown 中標記 TODO:OCR 的頁面")
    parser.add_argument("markdown", help="pdf_fallback.py 產生的 Markdown 檔案")
    parser.add_argument("--pdf", help="原始 PDF 路徑（預設依標記中的 source 於 Markdown 同目錄尋找）")
    parser.add_argument("--pages", help="只處理指定頁碼，逗號分隔（例：3,7）")
    parser.add_argument("--dpi", type=int, default=200, help="OCR 渲染解析度（預設 200）")
    parser.add_argument("--engine", choices=("baidu", "paddle"), help="Mac-mini OCR 引擎（預設使用 OCR_ENGINE 或 baidu）")
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
        refine(md_file, Path(args.pdf) if args.pdf else None, page_set, args.dpi, args.engine)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
