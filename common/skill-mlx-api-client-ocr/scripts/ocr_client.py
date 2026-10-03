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

OCR_ENDPOINT = "http://mac-mini.tail28f10.ts.net:5001/ocr"
OCR_HEALTH_URL = "http://mac-mini.tail28f10.ts.net:5001/health"

HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)


class OCRRequestError(RuntimeError):
    """OCR API failure with HTTP status or timeout provenance for callers."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        timeout_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.timeout_kind = timeout_kind


def check_ocr_server_live(timeout: float = 5.0) -> dict:
    """Check the unauthenticated Mac-mini health endpoint before OCR upload."""
    try:
        response = requests.get(OCR_HEALTH_URL, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise OCRRequestError(
            f"OCR server live check timed out after {timeout}s: {exc}",
            timeout_kind="health-check-timeout",
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise OCRRequestError(f"OCR server live check failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code != 200:
        raise OCRRequestError(
            f"OCR server live check failed ({response.status_code}): "
            f"{response.text or 'no response body'}",
            status_code=response.status_code,
        )
    if payload.get("status") != "ok":
        raise OCRRequestError(
            f"OCR server is not ready: {payload or 'missing status=ok'}",
            status_code=response.status_code,
        )
    return payload


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


def transcribe_document_to_markdown(
    file_path: str | Path, dpi: int = 200, clean: bool = True,
    engine: str | None = None, return_metadata: bool = False,
    app_name: str | None = None,
) -> str | dict:
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
    api_url = OCR_ENDPOINT
    api_key = os.getenv("OCR_API_KEY")
    engine = (engine or os.getenv("OCR_ENGINE", "baidu")).strip().lower()
    if engine not in {"baidu", "paddle"}:
        raise ValueError("engine must be 'baidu' or 'paddle'")

    if not api_key:
        raise ValueError("Missing OCR_API_KEY environment variable. Please check your .env file.")

    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    check_ocr_server_live()

    headers = {
        "X-API-Key": api_key
    }
    if app_name:
        headers["X-App-Name"] = app_name

    # 依檔案類型開啟並上傳
    try:
        with open(path_obj, "rb") as f:
            files = {
                "file": (path_obj.name, f, "application/octet-stream")
            }
            data = {"dpi": str(dpi), "engine": engine}

            print(f"Sending {path_obj.name} to Mac-mini OCR API...", file=sys.stderr)
            # 設定連線與讀取超時時間，因為 OCR 處理可能需要較長時間，所以預設 timeout 設為 900 秒。
            timeout = int(os.getenv("OCR_TIMEOUT_SECONDS", "900"))
            response = requests.post(
                api_url,
                headers=headers,
                files=files,
                data=data,
                timeout=(15, timeout),
            )

        if response.status_code != 200:
            try:
                error_msg = response.json().get("error", "Unknown error")
            except Exception:
                error_msg = response.text or "Unknown error"
            raise OCRRequestError(
                f"OCR request failed ({response.status_code}): {error_msg}",
                status_code=response.status_code,
                timeout_kind="http-504" if response.status_code == 504 else None,
            )

        payload = response.json()
        markdown = payload.get("markdown", "")
        markdown = clean_ocr_markdown(markdown) if clean else markdown
        if return_metadata:
            return {"markdown": markdown, "engine": payload.get("engine", engine),
                    "timings": payload.get("timings", {})}
        return markdown
    except requests.exceptions.ReadTimeout as e:
        raise OCRRequestError(
            f"OCR response timed out after {timeout}s: {e}",
            timeout_kind="client-read-timeout",
        ) from e
    except requests.exceptions.ConnectTimeout as e:
        raise OCRRequestError(f"OCR connection timed out: {e}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"OCR network request failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ocr_client.py <file_path> [dpi] [baidu|paddle]", file=sys.stderr)
        sys.exit(1)

    file_p = sys.argv[1]
    dpi_val = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    engine_val = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = transcribe_document_to_markdown(file_p, dpi_val, engine=engine_val)
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
