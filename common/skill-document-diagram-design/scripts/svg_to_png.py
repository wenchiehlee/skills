#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svg_to_png.py — 把原生管線產出的自含 HTML+SVG 圖表截圖成 PNG

用於 PowerPoint 匯出（PPTX 不能內嵌動態 SVG，一律先落地成點陣圖）。
依賴 playwright（需先 `pip install playwright && playwright install chromium`）。

用法：
  python scripts/svg_to_png.py flowchart.html --out flowchart.png
  python scripts/svg_to_png.py flowchart.html --out flowchart.png --scale 2 --selector "#diagram-root"
"""
from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def render(html_path: Path, out_path: Path, scale: float, selector: str | None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[svg_to_png] 缺少 playwright，請先執行：\n"
            "  pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    if not html_path.exists():
        print(f"[svg_to_png] 找不到來源檔：{html_path}", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=scale)
        page.goto(html_path.resolve().as_uri())
        page.wait_for_load_state("networkidle")

        if selector:
            locator = page.locator(selector)
            if locator.count() == 0:
                print(f"[svg_to_png] 找不到 selector：{selector}，改用整頁截圖", file=sys.stderr)
                page.screenshot(path=str(out_path), full_page=True)
            else:
                locator.first.screenshot(path=str(out_path))
        else:
            page.screenshot(path=str(out_path), full_page=True)

        browser.close()

    print(f"[svg_to_png] 已輸出：{out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="把自含 HTML+SVG 圖表截圖成 PNG")
    parser.add_argument("html", help="輸入 HTML 檔案路徑")
    parser.add_argument("--out", required=True, help="輸出 PNG 檔案路徑")
    parser.add_argument("--scale", type=float, default=2.0, help="device scale factor（預設 2x，PPT 投影用）")
    parser.add_argument("--selector", default=None, help="只截圖指定 CSS selector 範圍，預設整頁")
    args = parser.parse_args()

    render(Path(args.html), Path(args.out), args.scale, args.selector)


if __name__ == "__main__":
    main()
