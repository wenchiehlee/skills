#!/usr/bin/env python3
"""Download investor-conference materials through a real Playwright browser context.

Use this when direct curl/requests returns an anti-bot or JavaScript challenge page.
The script warms up the browser on a source page, then downloads one or more URLs
with the same browser request context and verifies content type / file magic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def parse_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("download must be OUT=URL")
    out, url = value.split("=", 1)
    if not out or not url:
        raise argparse.ArgumentTypeError("download must be OUT=URL")
    return out, url


def sniff_ok(body: bytes, kind: str | None) -> bool:
    if not kind:
        return True
    if kind == "pdf":
        return body.startswith(b"%PDF")
    if kind in {"m4a", "mp4"}:
        # ISO BMFF files start with a size then ftyp; keep this broader for variants.
        return b"ftyp" in body[:32]
    if kind == "mp3":
        return body.startswith(b"ID3") or body[:2] == bytes.fromhex("fffb")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup-url", required=True, help="Official page to open before downloading")
    parser.add_argument("--referer", help="Referer header; defaults to warmup URL")
    parser.add_argument("--kind", choices=["pdf", "mp3", "m4a", "mp4"], help="Expected file type for magic-byte validation")
    parser.add_argument("--timeout-ms", type=int, default=60000)
    parser.add_argument("--download", action="append", type=parse_pair, required=True, metavar="OUT=URL")
    args = parser.parse_args()

    referer = args.referer or args.warmup_url
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, user_agent=user_agent)
        page = context.new_page()
        page.goto(args.warmup_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        page.wait_for_timeout(3000)
        print(f"warmup: {page.title()}")

        failures = 0
        for out_name, url in args.download:
            out = Path(out_name)
            out.parent.mkdir(parents=True, exist_ok=True)
            resp = context.request.get(url, headers={"Referer": referer}, timeout=args.timeout_ms)
            body = resp.body()
            ctype = resp.headers.get("content-type", "")
            print(f"{out}: status={resp.status} content-type={ctype!r} bytes={len(body)} magic={body[:8]!r}")
            if not resp.ok or not sniff_ok(body, args.kind):
                failures += 1
                print(f"ERROR: validation failed for {url}", file=sys.stderr)
                continue
            out.write_bytes(body)
        browser.close()

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
