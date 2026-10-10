#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Queue-aware, resumable OCR page runner.

The runner deliberately submits one page at a time and caches successful
results by source-PDF hash, page, engine, and DPI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from ocr_client import OCRRequestError, OCR_ENDPOINT, clean_ocr_markdown, transcribe_document_to_markdown  # noqa: E402
from refine_todo_ocr import _extract_single_page_pdf  # noqa: E402


def _health_url(api_url: str) -> str:
    return api_url.rsplit("/", 1)[0] + "/health"


def _source_key(pdf: Path, page: int, engine: str, dpi: int) -> str:
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:20]
    return f"{digest}-p{page}-d{dpi}-{engine}"


class QueueGuard:
    def __init__(self, api_url: str, api_key: str, poll_seconds: int, max_queued: int):
        self.url = _health_url(api_url)
        self.headers = {"X-API-Key": api_key}
        self.poll_seconds = poll_seconds
        self.max_queued = max_queued
        self.consecutive_failures = 0

    def wait_until_ready(self) -> dict:
        while True:
            response = requests.get(self.url, headers=self.headers, timeout=15)
            response.raise_for_status()
            health = response.json()
            ocr = health.get("ocr", {})
            queued = int(ocr.get("queued", 0) or 0)
            active = bool(ocr.get("active", False))
            if health.get("status") == "ok" and queued < self.max_queued:
                return health
            print(f"[queue] waiting: active={active} queued={queued}", file=sys.stderr, flush=True)
            time.sleep(self.poll_seconds)

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            cooldown = min(300, self.poll_seconds * (2 ** min(self.consecutive_failures - 3, 4)))
            print(f"[queue] circuit breaker: pausing {cooldown}s after repeated failures", file=sys.stderr)
            time.sleep(cooldown)


class StrictQueueGuard(QueueGuard):
    def wait_until_ready(self) -> dict:
        while True:
            response = requests.get(self.url, headers=self.headers, timeout=15)
            response.raise_for_status()
            health = response.json()
            ocr = health.get("ocr", {})
            queued = int(ocr.get("queued", 0) or 0)
            active = bool(ocr.get("active", False))
            if health.get("status") == "ok" and not active and queued < self.max_queued:
                return health
            print(f"[queue] waiting: active={active} queued={queued}", file=sys.stderr, flush=True)
            time.sleep(self.poll_seconds)


def transcribe_cached(pdf: Path, page: int, engine: str, dpi: int, cache: Path,
                      guard: QueueGuard, retries: int) -> tuple[str, bool]:
    key = _source_key(pdf, page, engine, dpi)
    cache_file = cache / f"{key}.md"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file.read_text(encoding="utf-8"), True

    for attempt in range(retries + 1):
        guard.wait_until_ready()
        try:
            from tempfile import TemporaryDirectory
            with TemporaryDirectory() as tmp:
                single = _extract_single_page_pdf(pdf, page, Path(tmp))
                result = transcribe_document_to_markdown(single, dpi=dpi, engine=engine)
            markdown = clean_ocr_markdown(result if isinstance(result, str) else result.get("markdown", ""))
            if not markdown.strip() or "no text recognized" in markdown.lower():
                raise RuntimeError("OCR returned empty or placeholder text")
            cache_file.write_text(markdown, encoding="utf-8")
            guard.record_success()
            return markdown, False
        except OCRRequestError as exc:
            guard.record_failure()
            if exc.status_code != 503 or attempt >= retries:
                raise
            delay = min(300, 10 * (2 ** attempt))
            print(f"[queue] 503 on page {page}; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue-aware, resumable OCR page runner.")
    parser.add_argument("pdf", type=Path, help="Path to PDF file")
    parser.add_argument("pages", help="comma-separated 1-based page numbers (e.g. 1,2,3)")
    parser.add_argument("--engine", default=os.getenv("OCR_ENGINE", "baidu"))
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--cache", type=Path, default=Path.cwd() / ".ocr-cache")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--max-queued", type=int, default=1)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--strict", action="store_true", help="Strict mode: require inactive worker before submitting")
    args = parser.parse_args()

    api_url = os.getenv("OCR_API_URL") or OCR_ENDPOINT
    api_key = os.getenv("OCR_API_KEY")
    if not api_key:
        parser.error("OCR_API_KEY is required")
    args.cache.mkdir(parents=True, exist_ok=True)
    guard_cls = StrictQueueGuard if args.strict else QueueGuard
    guard = guard_cls(api_url, api_key, args.poll_seconds, args.max_queued)
    for page in (int(value) for value in args.pages.split(",")):
        markdown, cached = transcribe_cached(args.pdf, page, args.engine, args.dpi, args.cache, guard, args.retries)
        print(json.dumps({"page": page, "cached": cached, "chars": len(markdown)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
