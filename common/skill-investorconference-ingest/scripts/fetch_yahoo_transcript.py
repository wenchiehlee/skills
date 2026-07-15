#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a Yahoo Finance earnings call transcript via browser rendering.",
    )
    parser.add_argument("url", help="Yahoo Finance earnings transcript URL")
    parser.add_argument(
        "--output",
        required=True,
        help="Output text/markdown file path",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def extract_transcript_text(page) -> str:
    body = page.locator("body").inner_text(timeout=15000)
    marker = "Powered by Yahoo Scout"
    idx = body.find(marker)
    if idx != -1:
        body = body[idx + len(marker):].strip()
    else:
        marker = "Powered by Quartr"
        idx = body.find(marker)
        if idx != -1:
            body = body[idx:].strip()

    body = re.sub(r"\nADVERTISEMENT\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return normalize_text(body)


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(5000)
            text = extract_transcript_text(page)
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise SystemExit(f"Timed out loading Yahoo transcript page: {exc}") from exc
        finally:
            browser.close()

    output_path.write_text(text, encoding="utf-8")
    print(f"Saved transcript to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
