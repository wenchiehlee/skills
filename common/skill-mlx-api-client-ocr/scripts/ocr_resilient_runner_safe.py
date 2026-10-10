#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Strict entry point for the queue-aware OCR runner.

This wrapper keeps the runner's retry, circuit-breaker, cache, and quality
gate behavior while requiring both an empty queue and an inactive OCR worker
before every submission.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ocr_resilient_runner as runner

runner.QueueGuard = runner.StrictQueueGuard

if __name__ == "__main__":
    raise SystemExit(runner.main())
