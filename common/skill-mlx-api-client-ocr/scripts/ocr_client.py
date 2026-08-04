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

# Fix Windows console encoding for Chinese characters
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables from .env file
load_dotenv()

SAVE_RESULTS_MARKER = "===============save results:==============="


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
            # 設定連線與讀取超時時間，因為 OCR 處理可能需要較長時間，所以 timeout 設為 900 秒
            response = requests.post(api_url, headers=headers, files=files, data=data, timeout=900)

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
