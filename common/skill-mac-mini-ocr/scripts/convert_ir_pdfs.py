#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_ir_pdfs.py — 批次將各股票資料夾中的 *.pdf 轉為 *.md

轉錄一律透過 skills/mac-mini-ocr 技能（與其他 repo 的用法一致）：
- 先保留 PDF 內建文字層，產生乾淨 Markdown。
- 只有無文字層或文字層不足的頁面才標記 TODO:OCR，並嘗試用 Mac-mini OCR 補轉錄。
- Mac-mini 離線或 OCR 失敗時，保留文字層 Markdown 與 TODO:OCR 標記，之後可用以下指令補轉錄：

      python skills/mac-mini-ocr/scripts/refine_todo_ocr.py <md檔> --pdf <pdf檔>

使用方式：
    python scripts/convert_ir_pdfs.py             # 掃描全部股票資料夾
    python scripts/convert_ir_pdfs.py 2301 DELL   # 只處理指定資料夾
"""
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv

# Enforce UTF-8 console output for Chinese characters
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

_curr = Path(__file__).resolve()
REPO_ROOT = None
for p in _curr.parents:
    if (p / "audio_manifest.json").exists() or (p / ".git").exists():
        REPO_ROOT = p
        break
if not REPO_ROOT:
    REPO_ROOT = _curr.parents[3]
load_dotenv(REPO_ROOT / ".env")

# 透過 skills/mac-mini-ocr 技能進行轉錄
SKILL_SCRIPTS = REPO_ROOT / "skills" / "mac-mini-ocr" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from ocr_client import transcribe_document_to_markdown  # noqa: E402
from pdf_fallback import extract_pdf_to_markdown  # noqa: E402
from refine_todo_ocr import find_todo_pages, refine  # noqa: E402

def is_company_dir(path):
    if not path.is_dir():
        return False
    name = path.name
    if name in (".git", ".github", ".claude", "__pycache__", "definitions", "spec", "tmp", "tools", "web", "logs", "scripts", "skills"):
        return False
    return name.isdigit() or (name.isupper() and name.isalpha())

def is_valid_pdf(pdf_path):
    try:
        with open(pdf_path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False

def convert_pdf_to_md(pdf_path, md_path):
    print(f"Converting {pdf_path.name} -> {md_path.name}...")

    if not is_valid_pdf(pdf_path):
        print(f"  [INVALID PDF] {pdf_path.name} 內容不是 PDF（可能是下載失敗的 HTML 錯誤頁），請重新下載")
        return False

    try:
        base_md = extract_pdf_to_markdown(pdf_path, mark_embedded_images=False)
        md_path.write_text(base_md, encoding="utf-8", newline="\n")
    except Exception as e:
        print(f"  [TEXT EXTRACTION FAILED] {e}")
        try:
            md_text = transcribe_document_to_markdown(pdf_path, dpi=200)
            if md_text:
                md_path.write_text(md_text, encoding="utf-8", newline="\n")
                print(f"  [FULL OCR SUCCESS] Saved {md_path.name} (Chars: {len(md_text)})")
                return True
            print("  [FULL OCR EMPTY] API 回傳空白內容")
        except Exception as ocr_error:
            print(f"  [FULL OCR FAILED] {ocr_error}")
        return False

    todos = find_todo_pages(base_md)
    if not todos:
        print(f"  [TEXT SUCCESS] Saved {md_path.name}；PDF 文字層足夠，未做 OCR")
        return True

    try:
        refined = refine(md_path, pdf_path, pages={t["page"] for t in todos}, dpi=200)
        remaining = find_todo_pages(md_path.read_text(encoding="utf-8"))
        if not remaining:
            print(f"  [HYBRID SUCCESS] Saved {md_path.name}；OCR 補轉錄 {refined} 頁")
            return True
        print(f"  [HYBRID PARTIAL] Saved {md_path.name}；仍有 {len(remaining)} 頁 TODO:OCR")
        return True
    except Exception as e:
        print(f"  [HYBRID OCR UNAVAILABLE] {e}")
        print(f"  [TEXT PARTIAL] Saved {md_path.name}；保留 {len(todos)} 頁 TODO:OCR，可稍後補轉錄")
        return True

def main():
    print("=== Converting Investor Presentation PDFs to Markdown (via skills/mac-mini-ocr) ===")
    targets = set(sys.argv[1:])
    data_dir = REPO_ROOT / "data"
    company_dirs = [d for d in data_dir.iterdir() if is_company_dir(d)]
    if targets:
        company_dirs = [d for d in company_dirs if d.name in targets]
        unknown = targets - {d.name for d in company_dirs}
        if unknown:
            print(f"警告：找不到資料夾 {sorted(unknown)}")

    converted_count = 0
    skipped_count = 0
    failed_count = 0

    for c_dir in sorted(company_dirs):
        for file in sorted(c_dir.iterdir()):
            if file.is_file() and file.name.endswith(".pdf"):
                md_path = c_dir / f"{file.stem}.md"

                # Check if MD already exists
                if md_path.exists():
                    skipped_count += 1
                    continue

                if convert_pdf_to_md(file, md_path):
                    converted_count += 1
                else:
                    failed_count += 1

    print(f"\nFinished! Converted: {converted_count}, Already Exists (Skipped): {skipped_count}, Failed: {failed_count}")
    return 1 if failed_count else 0

if __name__ == "__main__":
    sys.exit(main())
