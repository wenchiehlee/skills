"""Codex API Server — entry point and routes."""

from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import threading

import waitress
from flask import Flask, jsonify, request

import config
from auth import require_api_key
from executor import ExecutionError, ocr_queue_status, run, run_ocr, shutdown_ocr_engines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

_TAIWAN_TZ = timezone(timedelta(hours=8))
_STATS_FILE = Path(__file__).parent / "stats.jsonl"


_PROMPT_PREVIEW_LEN = 60
_OCR_STATS_LOCK = threading.Lock()
_PHOTO_OCR_TASKS: dict[str, dict] = {}
_PHOTO_OCR_TASKS_LOCK = threading.Lock()
_PHOTO_OCR_TASK_TTL_SECONDS = 900


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


def _record_ocr_stat(
    filename: str,
    engine: str,
    model: str,
    elapsed: float,
    output_len: int,
    status_code: int,
    timings: dict | None = None,
) -> None:
    """Record latency and outcome without storing OCR text or source content."""
    entry = {
        "time": datetime.now(_TAIWAN_TZ).strftime("%Y-%m-%d %H:%M:%S CST"),
        "service": "ocr",
        "engine": engine,
        "model": model,
        "filename": Path(filename).name,
        "duration_s": round(elapsed, 3),
        "output_len": output_len,
        "status_code": status_code,
        "success": 200 <= status_code < 300,
        "timings": timings or {},
    }
    try:
        with _OCR_STATS_LOCK, _STATS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write OCR stats")


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


def _photo_format(path: Path) -> str | None:
    """Detect supported image types from file bytes, not the upload MIME header."""
    with path.open("rb") as image_file:
        header = image_file.read(32)
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "WebP"
    if len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] in {
        b"heic", b"heix", b"hevc", b"hevx", b"heif", b"mif1", b"msf1",
    }:
        return "HEIC/HEIF"
    return None


def _photo_needs_ocr(output: str) -> bool:
    """Detect likely document scans from the structured vision-analysis output."""
    hints = (
        "文件", "掃描", "表格", "收據", "發票", "單據", "合約", "表單", "報告",
        "document", "scan", "receipt", "invoice", "form", "table",
    )
    normalized = output.casefold()
    return any(hint in normalized for hint in hints)


def _prune_photo_ocr_tasks() -> None:
    now = time.time()
    with _PHOTO_OCR_TASKS_LOCK:
        expired = [
            task_id for task_id, task in _PHOTO_OCR_TASKS.items()
            if task.get("finished_at") and now - task["finished_at"] > _PHOTO_OCR_TASK_TTL_SECONDS
        ]
        for task_id in expired:
            _PHOTO_OCR_TASKS.pop(task_id, None)


def _expire_photo_ocr_task(task_id: str) -> None:
    with _PHOTO_OCR_TASKS_LOCK:
        task = _PHOTO_OCR_TASKS.get(task_id)
        if (
            task is not None
            and task.get("finished_at")
            and time.time() - task["finished_at"] >= _PHOTO_OCR_TASK_TTL_SECONDS
        ):
            _PHOTO_OCR_TASKS.pop(task_id, None)


def _run_photo_ocr_task(
    task_id: str, image_path: str, temp_dir: str, filename: str, engine: str, app_name: str
) -> None:
    model_repo = "baidu/Unlimited-OCR" if engine == "baidu" else "mlx-community/GLM-OCR-bf16"
    started = time.monotonic()
    with _PHOTO_OCR_TASKS_LOCK:
        task = _PHOTO_OCR_TASKS.get(task_id)
        if task is not None:
            task["status"] = "running"
    try:
        markdown_output, timings = run_ocr(image_path, dpi=200, engine=engine)
        elapsed = time.monotonic() - started
        timings["request_total_s"] = round(elapsed, 3)
        _record_ocr_stat(filename, engine, model_repo, elapsed, len(markdown_output), 200, timings)
        _send_amplitude_event_async(
            model_repo, elapsed, len(markdown_output), app_name,
            stage="ocr", provider=f"{engine}-ocr", model_repo=model_repo,
        )
        result = {
            "text": markdown_output.strip(),
            "engine": engine,
            "elapsed_s": timings.get("request_total_s"),
        }
        status = "complete"
    except ExecutionError as exc:
        elapsed = time.monotonic() - started
        timings = dict(exc.details)
        timings["request_total_s"] = round(elapsed, 3)
        _record_ocr_stat(filename, engine, model_repo, elapsed, 0, exc.status_code, timings)
        _send_amplitude_event_async(
            model_repo, elapsed, 0, app_name, stage="ocr",
            provider=f"{engine}-ocr", model_repo=model_repo, success=False,
        )
        logger.warning("Photo OCR task failed: %s", exc)
        result = {"error": "OCR 文字擷取失敗；視覺分析建議仍可使用。", "engine": engine}
        status = "failed"
    except Exception:
        elapsed = time.monotonic() - started
        _record_ocr_stat(
            filename, engine, model_repo, elapsed, 0, 500,
            {"request_total_s": round(elapsed, 3)},
        )
        _send_amplitude_event_async(
            model_repo, elapsed, 0, app_name, stage="ocr",
            provider=f"{engine}-ocr", model_repo=model_repo, success=False,
        )
        logger.exception("Unexpected error in photo OCR task")
        result = {"error": "OCR 文字擷取失敗；視覺分析建議仍可使用。", "engine": engine}
        status = "failed"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    with _PHOTO_OCR_TASKS_LOCK:
        task = _PHOTO_OCR_TASKS.get(task_id)
        if task is not None:
            task.update({"status": status, "ocr": result, "finished_at": time.time()})
    expiry_timer = threading.Timer(
        _PHOTO_OCR_TASK_TTL_SECONDS, _expire_photo_ocr_task, args=(task_id,)
    )
    expiry_timer.daemon = True
    expiry_timer.start()


@app.route("/exec", methods=["POST"])
@require_api_key
def execute():
    """
    Request:  {"prompt": "...", "model": "o3"}   (model is optional)
    Response: {"output": "..."}
    Errors:   {"error": "..."}  +  HTTP 400 / 401 / 500 / 503 / 504 / 502
    """
    if not config.AMPLITUDE_API_KEY:
        logger.error("AMPLITUDE_API_KEY is not configured on server")
        return jsonify({"error": "AMPLITUDE_API_KEY is not configured on server"}), 500

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


@app.route("/photo-analyze", methods=["POST"])
@require_api_key
def photo_analyze():
    """Analyze one uploaded image with an enabled MLX vision-language model."""
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    if len(prompt) > config.MAX_PROMPT_LENGTH:
        return jsonify({"error": f"Prompt exceeds {config.MAX_PROMPT_LENGTH} character limit"}), 400

    model = request.form.get("model", "mlx-gemma4").strip()
    if model not in config.ALLOWED_MODELS:
        return jsonify({"error": f"Model not allowed. Choose from: {sorted(config.ALLOWED_MODELS)}"}), 400
    ocr_engine = request.form.get("ocr_engine", "").strip().lower()
    if ocr_engine and ocr_engine not in config.OCR_ENGINES:
        return jsonify({
            "error": f"OCR engine not enabled. Choose from: {sorted(config.OCR_ENGINES)}"
        }), 400

    started = time.monotonic()
    temp_dir = tempfile.mkdtemp(prefix="mlx_photo_")
    background_ocr_started = False
    try:
        source_path = Path(temp_dir) / "source-image"
        file.save(source_path)
        input_format = _photo_format(source_path)
        if input_format is None:
            return jsonify({"error": "Unsupported or invalid image. Use JPEG, PNG, WebP, or HEIC/HEIF."}), 415

        inference_path = source_path
        converted = False
        if input_format == "HEIC/HEIF":
            # sips relies on the filename extension for some HEIF variants.
            heic_path = Path(temp_dir) / "source-image.heic"
            source_path.replace(heic_path)
            source_path = heic_path
            inference_path = Path(temp_dir) / "image.jpg"
            try:
                conversion = subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(source_path), "--out", str(inference_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return jsonify({"error": "HEIC conversion failed on the MLX server."}), 415
            if conversion.returncode != 0 or not inference_path.is_file():
                return jsonify({"error": "HEIC conversion failed on the MLX server."}), 415
            converted = True

        output, actual_model = run(prompt, model=model, image_path=str(inference_path))
        elapsed = time.monotonic() - started
        _record_stat(prompt, actual_model, len(output), elapsed)
        _send_amplitude_event_async(
            model,
            elapsed,
            len(output),
            request.headers.get("X-App-Name") or "Photo-Analyzer",
            stage="photo-analyze",
            provider="mlx-vlm",
            model_repo=actual_model,
        )

        ocr_result = None
        if ocr_engine and _photo_needs_ocr(output):
            _prune_photo_ocr_tasks()
            task_id = uuid.uuid4().hex
            with _PHOTO_OCR_TASKS_LOCK:
                _PHOTO_OCR_TASKS[task_id] = {
                    "status": "queued", "ocr": None, "created_at": time.time(),
                    "finished_at": None,
                }
            try:
                worker = threading.Thread(
                    target=_run_photo_ocr_task,
                    args=(
                        task_id, str(inference_path), str(temp_dir), file.filename,
                        ocr_engine, request.headers.get("X-App-Name") or "Photo-Analyzer",
                    ),
                    name=f"photo-ocr-{task_id[:8]}",
                    daemon=True,
                )
                worker.start()
                background_ocr_started = True
                ocr_result = {"status": "queued", "task_id": task_id, "engine": ocr_engine}
            except Exception:
                with _PHOTO_OCR_TASKS_LOCK:
                    _PHOTO_OCR_TASKS[task_id] = {
                        "status": "failed", "ocr": {"error": "無法啟動 OCR 工作。", "engine": ocr_engine},
                        "finished_at": time.time(),
                    }
                logger.exception("Could not start photo OCR task")
                ocr_result = {"error": "無法啟動 OCR 工作；視覺分析建議仍可使用。", "engine": ocr_engine}

        return jsonify({
            "output": output,
            "model": actual_model,
            "input_format": input_format,
            "converted": converted,
            "elapsed_s": round(time.monotonic() - started, 3),
            "temporary_file_deleted": not background_ocr_started,
            "ocr": ocr_result,
        })

    except ExecutionError as e:
        return jsonify({"error": str(e)}), e.status_code
    except Exception:
        logger.exception("Unexpected error in photo analysis")
        return jsonify({"error": "Internal server error"}), 500

    finally:
        if not background_ocr_started:
            shutil.rmtree(temp_dir, ignore_errors=True)

@app.route("/photo-analyze/ocr-status/<task_id>", methods=["GET"])
@require_api_key
def photo_ocr_status(task_id: str):
    if len(task_id) != 32 or any(ch not in "0123456789abcdef" for ch in task_id):
        return jsonify({"error": "Invalid OCR task ID"}), 400
    _prune_photo_ocr_tasks()
    with _PHOTO_OCR_TASKS_LOCK:
        task = _PHOTO_OCR_TASKS.get(task_id)
        if task is None:
            return jsonify({"error": "OCR task not found or expired"}), 404
        return jsonify({"status": task["status"], "ocr": task.get("ocr")})


@app.route("/ocr", methods=["POST"])
@require_api_key
def ocr():
    """
    Request: Multipart-form upload:
             - "file": PDF or image file
             - "dpi" (optional): DPI for PDF rendering, default 200
             - "engine" (optional): "baidu" (default) or "glm"
    Response: {"markdown": "...", "engine": "...", "timings": {...}}
    """
    if not config.AMPLITUDE_API_KEY:
        logger.error("AMPLITUDE_API_KEY is not configured on server")
        return jsonify({"error": "AMPLITUDE_API_KEY is not configured on server"}), 500

    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    engine = request.form.get("engine", "baidu").strip().lower()
    if engine not in config.OCR_ENGINES:
        return jsonify({
            "error": f"OCR engine not enabled. Choose from: {sorted(config.OCR_ENGINES)}"
        }), 400

    dpi = request.form.get('dpi', '200')
    try:
        dpi_val = int(dpi)
    except ValueError:
        return jsonify({"error": "DPI must be an integer"}), 400

    # Save uploaded file to a temporary location
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        tmp_path = Path(tmp.name)
    temp_paths = [tmp_path]
    ocr_path = tmp_path

    t0 = time.monotonic()
    timings: dict = {}
    model_repo = (
        "baidu/Unlimited-OCR" if engine == "baidu" else "mlx-community/GLM-OCR-bf16"
    )
    try:
        if _photo_format(ocr_path) == "HEIC/HEIF":
            heic_path = ocr_path.with_suffix(".heic")
            if heic_path != ocr_path:
                ocr_path.replace(heic_path)
                ocr_path = heic_path
                temp_paths.append(ocr_path)
            jpeg_path = ocr_path.with_suffix(".jpg")
            temp_paths.append(jpeg_path)
            conversion_started = time.monotonic()
            try:
                conversion = subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(ocr_path), "--out", str(jpeg_path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return jsonify({"error": "HEIC conversion failed on the OCR server."}), 415
            if conversion.returncode != 0 or not jpeg_path.is_file():
                return jsonify({"error": "HEIC conversion failed on the OCR server."}), 415
            ocr_path = jpeg_path
            timings["heic_conversion_s"] = round(time.monotonic() - conversion_started, 3)

        markdown_output, ocr_timings = run_ocr(str(ocr_path), dpi=dpi_val, engine=engine)
        timings.update(ocr_timings)
        elapsed = time.monotonic() - t0
        timings["request_total_s"] = round(elapsed, 3)
        _record_ocr_stat(file.filename, engine, model_repo, elapsed, len(markdown_output), 200, timings)
        _send_amplitude_event_async(
            model_repo,
            elapsed,
            len(markdown_output),
            request.headers.get("X-App-Name") or "Baidu-OCR",
            stage="ocr",
            provider=f"{engine}-ocr",
            model_repo=model_repo,
        )
        return jsonify({"markdown": markdown_output, "engine": engine, "timings": timings})
    except ExecutionError as e:
        elapsed = time.monotonic() - t0
        timings = dict(e.details)
        timings["request_total_s"] = round(elapsed, 3)
        _record_ocr_stat(file.filename, engine, model_repo, elapsed, 0, e.status_code, timings)
        return jsonify({"error": str(e)}), e.status_code
    except Exception:
        logger.exception("Unexpected error in OCR")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        # Clean up the temporary file
        for temp_path in temp_paths:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove request-scoped OCR temp file")


@app.route("/health", methods=["GET"])
def health():
    """Unauthenticated health check for Synology reverse proxy monitoring."""
    with _PHOTO_OCR_TASKS_LOCK:
        photo_ocr_tasks = sum(
            task.get("status") in {"queued", "running"}
            for task in _PHOTO_OCR_TASKS.values()
        )
    return jsonify({
        "status": "ok",
        "ocr": ocr_queue_status(),
        "photo_ocr_tasks": photo_ocr_tasks,
    }), 200


if __name__ == "__main__":
    config.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    def _shutdown(signum, _frame):
        logger.info("Received signal %s; stopping OCR engine processes", signum)
        shutdown_ocr_engines()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    logger.info("Starting MLX API Server (Waitress) on %s:%d", config.HOST, config.PORT)
    # Keep enough request threads for queued OCR callers while preserving
    # capacity for health checks and regular /exec requests.
    waitress.serve(
        app,
        host=config.HOST,
        port=config.PORT,
        threads=config.MAX_CONCURRENT + config.OCR_QUEUE_MAX_SIZE + 2,
    )
