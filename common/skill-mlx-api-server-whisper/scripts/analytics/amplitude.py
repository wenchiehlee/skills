"""Amplitude event tracking for Whisper transcription（靜默降級：無 key 時不報錯）。

Sends events synchronously via httpx (no threads) to avoid Python 3.14
ThreadPoolExecutor shutdown ordering issues with the amplitude-analytics SDK.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_api_key: str | None = None   # None = not yet loaded, "" = unavailable
_app_name: str = "whisper-transcription-stage"

AMPLITUDE_URL = "https://api2.amplitude.com/2/httpapi"


def _get_api_key() -> str:
    global _api_key
    if _api_key is not None:
        return _api_key
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parents[4] / ".env")  # repo root /.env (analytics/ -> scripts/ -> skill-mlx-api-server-whisper/ -> skills/ -> repo root)
    except ImportError:
        pass
    _api_key = os.getenv("AMPLITUDE_API_KEY", "")
    return _api_key


def configure(app_name: str) -> None:
    global _app_name
    _app_name = app_name


def _classify_error(exc_type: type) -> str:
    name = exc_type.__name__.lower()
    if "import" in name or "module" in name:
        return "import_error"
    if "runtime" in name:
        return "runtime_error"
    if "file" in name or "notfound" in name or "os" in name:
        return "file_error"
    if "timeout" in name:
        return "timeout"
    if "value" in name or "type" in name:
        return "input_error"
    return "transcription_error"


def _first_n_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]) if words else ""


def _send(event_type: str, user_id: str, props: dict[str, Any]) -> None:
    """Send one event synchronously via httpx — no threads, no SDK worker."""
    api_key = _get_api_key()
    if not api_key:
        return
    try:
        import httpx
        payload = {
            "api_key": api_key,
            "events": [{
                "event_type":        event_type,
                "user_id":           user_id,
                "event_properties":  props,
                "time":              int(time.time() * 1000),
            }],
        }
        httpx.post(AMPLITUDE_URL, json=payload, timeout=10)
    except Exception as e:
        logger.debug("Amplitude send 失敗（靜默）：%s", e)


class WhisperCallTracker:
    """context manager：轉錄結束後送出單一 llm_call event。

    欄位與 llm repo 的 llm_call event 保持一致，額外增加 whisper 專屬欄位：
        language, audio_duration_sec, rtf, model_repo

    屬性（可在 with 區塊內設定）：
        result  (str)  — 轉錄結果文字，用於記錄前 100 words
        rtf     (float)— Real-Time Factor
    """

    def __init__(self, backend: str, model: str, audio_file: str,
                 language: str | None, audio_duration: float,
                 model_repo: str | None = None):
        self.backend = backend
        self.model = model
        self.model_repo = model_repo or ""
        self.audio_file = audio_file
        self.language = language or "auto"
        self.audio_duration = audio_duration
        self.result: str = ""
        self.rtf: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> "WhisperCallTracker":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_sec = round(time.monotonic() - self._start, 2)
        success = exc_type is None

        props: dict[str, Any] = {
            "provider":           self.backend,
            "model":              self.model,
            "model_repo":         self.model_repo,
            "app_name":           _app_name,
            "key_used":           "",
            "input_preview":      self.audio_file[:100],
            "output_preview":     _first_n_words(self.result, 100),
            "duration_sec":       duration_sec,
            "success":            1 if success else 0,
            "language":           self.language,
            "audio_duration_sec": round(self.audio_duration, 1),
            "rtf":                round(self.rtf, 3),
        }
        if not success and exc_type is not None:
            props["error_type"] = _classify_error(exc_type)

        _send("llm_call", _app_name, props)
        return False  # 不吃掉例外
