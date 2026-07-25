#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
heic_convert.py — HEIC 圖片轉錄工具（mac-mini-ocr 技能）

將 HEIC 圖片（常見於 iPhone 拍攝的文件照片）轉存為 PNG 後，
交給 ocr_client.transcribe_document_to_markdown() 送 Mac-mini OCR API 轉錄。

使用方式：

    python scripts/heic_convert.py path/to/photo.heic > output.md

也可作為模組導入：

    from scripts.heic_convert import transcribe_heic_to_markdown
    markdown_text = transcribe_heic_to_markdown("path/to/photo.heic")
"""
import platform
import sys
import tempfile
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from scripts.ocr_client import transcribe_document_to_markdown
except ImportError:
    from ocr_client import transcribe_document_to_markdown


def transcribe_heic_to_markdown(file_path: str | Path, dpi: int = 200, clean: bool = True) -> str:
    """
    將本地 HEIC 圖片轉為 PNG 後送 Mac-mini OCR API 轉錄，回傳 Markdown 文本。

    :param file_path: 本地 HEIC 檔案路徑
    :param dpi: 轉交 OCR API 的 dpi 參數（圖片本身不受影響，僅沿用介面一致性）
    :param clean: 是否清除 Mac-mini OCR 回傳中的 detector/debug 標記
    :raises FileNotFoundError: 當檔案不存在時拋出
    """
    from PIL import Image
    from pillow_heif import register_heif_opener

    register_heif_opener()

    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        png_path = Path(tmp_dir) / f"{path_obj.stem}.png"
        img = Image.open(path_obj)
        img.save(png_path)
        return transcribe_document_to_markdown(png_path, dpi=dpi, clean=clean)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python heic_convert.py <file_path.heic> [dpi]", file=sys.stderr)
        sys.exit(1)

    file_p = sys.argv[1]
    dpi_val = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    try:
        result = transcribe_heic_to_markdown(file_p, dpi_val)
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
