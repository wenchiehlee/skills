#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR Client Module for Mac-mini OCR API
This script can be imported as a module or executed directly from the command line.
"""

import os
import sys
import requests
import platform
import re
from pathlib import Path
from dotenv import load_dotenv

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency
    BeautifulSoup = None

# Fix Windows console encoding for Chinese characters
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables from .env file
load_dotenv()

SAVE_RESULTS_MARKER = "===============save results:==============="

HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


def _html_table_to_markdown(html: str) -> str:
    """Convert a single <table>...</table> block to a GFM pipe table.

    Baidu Unlimited-OCR emits detected tables as raw HTML <table> markup
    (correct row/column structure) rather than Markdown pipe syntax. GitHub
    renders embedded HTML tables fine, but downstream tooling that expects
    plain Markdown (digest/segment-weight extraction, grep-based pipelines)
    doesn't parse HTML — so normalize to a pipe table here.
    """
    if BeautifulSoup is None:
        return html

    try:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        if table is None:
            return html

        rows = []
        for tr in table.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                # Drop non-text placeholders (e.g. <img> markers for icons/checkmarks)
                # rather than losing the whole cell.
                text = cell.get_text(separator=" ", strip=True)
                cells.append(text.replace("|", "/").replace("\n", " ").strip())
            if any(cells):
                rows.append(cells)

        if len(rows) < 1:
            return html

        col_count = max(len(r) for r in rows)
        rows = [r + [""] * (col_count - len(r)) for r in rows]

        md_lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * col_count) + "|"]
        for r in rows[1:]:
            md_lines.append("| " + " | ".join(r) + " |")
        return "\n".join(md_lines)
    except Exception:
        return html


def _convert_html_tables(text: str) -> str:
    """Replace every HTML <table> block in *text* with a Markdown pipe table."""
    return HTML_TABLE_RE.sub(lambda m: _html_table_to_markdown(m.group(0)), text)


def clean_ocr_markdown(markdown_text: str) -> str:
    """Clean Mac-mini OCR debug/layout markup before saving Markdown."""
    if not markdown_text:
        return ""

    text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    if SAVE_RESULTS_MARKER in text:
        text = text.split(SAVE_RESULTS_MARKER, 1)[1]

    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if stripped == "<PAGE>":
            cleaned_lines.append("<!-- OCR_PAGE -->")
            continue
        if stripped == "[Non-Text]":
            continue
        if stripped.startswith("![](images/"):
            continue
        stripped = re.sub(r"<\|det\|>[^<]*<\|/det\|>", "", stripped).strip()
        if stripped:
            cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    text = _convert_html_tables(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def transcribe_document_to_markdown(file_path: str | Path, dpi: int = 200, clean: bool = True) -> str:
    """
    將本地的 PDF 或圖片發送到 Mac-mini OCR API 進行轉錄，並回傳 Markdown 文本。
    
    :param file_path: 本地檔案路徑 (PDF 或圖片)
    :param dpi: PDF 渲染解析度，預設 200
    :param clean: 是否清除 Mac-mini OCR 回傳中的 detector/debug 標記，預設 True
    :return: 轉錄後的 Markdown 文本
    :raises ValueError: 當缺少 API Key 時拋出
    :raises FileNotFoundError: 當檔案不存在時拋出
    :raises RuntimeError: 當 API 請求失敗、超時或網路錯誤時拋出
    """
    api_url = os.getenv("OCR_API_URL", "http://mac-mini.tail28f10.ts.net:5001/ocr")
    api_key = os.getenv("OCR_API_KEY")

    if not api_key:
        raise ValueError("Missing OCR_API_KEY environment variable. Please check your .env file.")

    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    headers = {
        "X-API-Key": api_key
    }

    # 依檔案類型開啟並上傳
    try:
        with open(path_obj, "rb") as f:
            files = {
                "file": (path_obj.name, f, "application/octet-stream")
            }
            data = {
                "dpi": str(dpi)
            }

            print(f"Sending {path_obj.name} to Mac-mini OCR API...", file=sys.stderr)
            # 設定連線與讀取超時時間，因為 OCR 處理可能需要較長時間，所以預設 timeout 設為 900 秒。
            timeout = int(os.getenv("OCR_TIMEOUT_SECONDS", "900"))
            response = requests.post(api_url, headers=headers, files=files, data=data, timeout=timeout)

        if response.status_code != 200:
            try:
                error_msg = response.json().get("error", "Unknown error")
            except Exception:
                error_msg = response.text or "Unknown error"
            raise RuntimeError(f"OCR request failed ({response.status_code}): {error_msg}")

        markdown = response.json().get("markdown", "")
        return clean_ocr_markdown(markdown) if clean else markdown
    except requests.exceptions.Timeout as e:
        raise RuntimeError(f"OCR request timed out: {e}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"OCR network request failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr_client.py <file_path> [dpi]", file=sys.stderr)
        sys.exit(1)
        
    file_p = sys.argv[1]
    dpi_val = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    
    try:
        result = transcribe_document_to_markdown(file_p, dpi_val)
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
