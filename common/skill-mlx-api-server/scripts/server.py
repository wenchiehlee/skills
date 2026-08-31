"""Codex API Server — entry point and routes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import threading

import waitress
from flask import Flask, jsonify, request

import config
from auth import require_api_key
from executor import ExecutionError, run, run_ocr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_TAIWAN_TZ = timezone(timedelta(hours=8))
_STATS_FILE = Path(__file__).parent / "stats.jsonl"


_PROMPT_PREVIEW_LEN = 60


def _record_stat(prompt: str, model: str | None, output_len: int, elapsed: float) -> None:
    """Append one stats record to stats.jsonl (Taiwan time)."""
    preview = prompt[:_PROMPT_PREVIEW_LEN].replace("\n", " ")
    if len(prompt) > _PROMPT_PREVIEW_LEN:
        preview += "…"
    entry = {
        "time": datetime.now(_TAIWAN_TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "model": model,
        "prompt_preview": preview,
        "prompt_len": len(prompt),
        "output_len": output_len,
        "elapsed_s": round(elapsed, 2),
    }
    try:
        with _STATS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write stats")


def _send_amplitude_event_async(
    model: str,
    elapsed: float,
    output_len: int,
    app_name: str | None,
    *,
    service: str = "mlx-api-server",
    stage: str = "exec",
    provider: str = "mlx",
    model_repo: str = "",
    success: bool = True,
) -> None:
    """Asynchronously send one normalized llm_call event to Amplitude."""
    api_key = config.AMPLITUDE_API_KEY
    if not api_key:
        return

    def worker():
        url = "https://api2.amplitude.com/2/httpapi"
        payload = {
            "api_key": api_key,
            "events": [
                {
                    "user_id": "mac-mini-server",
                    "device_id": "mac-mini-server",
                    "event_type": "llm_call",
                    "event_properties": {
                        "service": service,
                        "stage": stage,
                        "provider": provider,
                        "model": model,
                        "model_repo": model_repo,
                        "duration_sec": elapsed,
                        "output_len": output_len,
                        "app_name": app_name or "Baidu-OCR",
                        "success": success,
                    }
                }
            ]
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status != 200:
                    logger.error("Amplitude status: %d", response.status)
        except Exception as e:
            logger.error("Failed to send Amplitude event: %s", e)

    threading.Thread(target=worker, daemon=True).start()


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max request body


@app.route("/exec", methods=["POST"])
@require_api_key
def execute():
    """
    Request:  {"prompt": "...", "model": "o3"}   (model is optional)
    Response: {"output": "..."}
    Errors:   {"error": "..."}  +  HTTP 400 / 401 / 503 / 504 / 502
    """
    data = request.get_json(silent=True)
    if not data or not data.get("prompt"):
        return jsonify({"error": "No prompt provided"}), 400

    prompt: str = data["prompt"]
    model: str | None = data.get("model")

    # Input validation
    if len(prompt) > config.MAX_PROMPT_LENGTH:
        return jsonify({"error": f"Prompt exceeds {config.MAX_PROMPT_LENGTH} character limit"}), 400

    if model and model not in config.ALLOWED_MODELS:
        allowed = sorted(config.ALLOWED_MODELS)
        return jsonify({"error": f"Model not allowed. Choose from: {allowed}"}), 400

    t0 = time.monotonic()
    try:
        output, actual_model = run(prompt, model=model)
        elapsed = time.monotonic() - t0
        report_model = model or "mlx-qwen3"
        _record_stat(prompt, actual_model, len(output), elapsed)
        _send_amplitude_event_async(
            report_model,
            elapsed,
            len(output),
            request.headers.get("X-App-Name") or "MLX-Exec",
            stage="exec",
            provider="mlx",
            model_repo=actual_model,
        )
        return jsonify({"output": output})
    except ExecutionError as e:
        return jsonify({"error": str(e)}), e.status_code
    except Exception:
        logger.exception("Unexpected error")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/ocr", methods=["POST"])
@require_api_key
def ocr():
    """
    Request: Multipart-form upload:
             - "file": PDF or image file
             - "dpi" (optional): DPI for PDF rendering, default 200
    Response: {"markdown": "..."}
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    dpi = request.form.get('dpi', '200')
    try:
        dpi_val = int(dpi)
    except ValueError:
        return jsonify({"error": "DPI must be an integer"}), 400

    # Save uploaded file to a temporary location
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    t0 = time.monotonic()
    try:
        markdown_output = run_ocr(tmp_path, dpi=dpi_val)
        elapsed = time.monotonic() - t0
        _record_stat(f"OCR File: {file.filename}", "baidu/Unlimited-OCR", len(markdown_output), elapsed)
        _send_amplitude_event_async(
            "baidu/Unlimited-OCR",
            elapsed,
            len(markdown_output),
            request.headers.get("X-App-Name") or "Baidu-OCR",
            stage="ocr",
            provider="baidu-ocr",
            model_repo="baidu/Unlimited-OCR",
        )
        return jsonify({"markdown": markdown_output})
    except ExecutionError as e:
        return jsonify({"error": str(e)}), e.status_code
    except Exception:
        logger.exception("Unexpected error in OCR")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        # Clean up the temporary file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.route("/health", methods=["GET"])
def health():
    """Unauthenticated health check for Synology reverse proxy monitoring."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    config.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting MLX API Server (Waitress) on %s:%d", config.HOST, config.PORT)
    waitress.serve(app, host=config.HOST, port=config.PORT, threads=config.MAX_CONCURRENT + 2)
