"""Codex execution — subprocess management, sandboxing, concurrency control."""

from __future__ import annotations

import logging
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_semaphore = threading.Semaphore(config.MAX_CONCURRENT)
_ocr_condition = threading.Condition()
_ocr_waiters: deque[object] = deque()
_ocr_active = False
_ocr_current_engine: str | None = None
_glm_vlm_process: subprocess.Popen | None = None
_glm_vlm_process_lock = threading.Lock()

_OCR_TIMING_PREFIX = "OCR_TIMING_JSON="


def _acquire_ocr_slot() -> float:
    """Wait for the sole OCR worker in FIFO order, with a bounded queue."""
    global _ocr_active
    ticket = object()
    queued_at = time.monotonic()
    deadline = time.monotonic() + config.OCR_QUEUE_WAIT_SECONDS

    with _ocr_condition:
        if len(_ocr_waiters) >= config.OCR_QUEUE_MAX_SIZE:
            raise ExecutionError("OCR queue is full. Try again later.", status_code=503,
                                 details={"queue_wait_s": 0.0})
        _ocr_waiters.append(ticket)
        queue_position = len(_ocr_waiters)
        try:
            while _ocr_waiters[0] is not ticket or _ocr_active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ExecutionError(
                        "Timed out waiting in the OCR queue.", status_code=503,
                        details={"queue_wait_s": round(time.monotonic() - queued_at, 3)},
                    )
                _ocr_condition.wait(remaining)
            _ocr_waiters.popleft()
            _ocr_active = True
        except Exception:
            try:
                _ocr_waiters.remove(ticket)
            except ValueError:
                pass
            _ocr_condition.notify_all()
            raise

    logger.info("OCR worker acquired — queued_position=%d", queue_position)
    return time.monotonic() - queued_at


def _release_ocr_slot() -> None:
    global _ocr_active, _ocr_current_engine
    with _ocr_condition:
        _ocr_active = False
        _ocr_current_engine = None
        _ocr_condition.notify_all()


def ocr_queue_status() -> dict[str, object]:
    with _ocr_condition:
        return {
            "active": _ocr_active,
            "active_engine": _ocr_current_engine,
            "queued": len(_ocr_waiters),
        }


class ExecutionError(Exception):
    """Raised when codex exec fails or times out."""
    def __init__(self, message: str, status_code: int = 502, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


MODEL_MAP = {
    "qwen3-mlx": "mlx-community/Qwen3.5-9B-MLX-4bit",
    "mlx-qwen3": "mlx-community/Qwen3.5-9B-MLX-4bit",
    "mlx-gemma4": "mlx-community/gemma-4-e4b-it-8bit",
}

# Gemma-4 models are VLMs — require mlx_vlm instead of mlx_lm
_VLM_REPOS = {"mlx-community/gemma-4-e4b-it-8bit"}

# Qwen3 is a thinking model — append /no_think to suppress chain-of-thought
_NOTHINK_REPOS = {"mlx-community/Qwen3.5-9B-MLX-4bit"}

_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


def _is_model_ready(repo_id: str) -> bool:
    """Return True only if the model is fully downloaded in HuggingFace cache."""
    folder = "models--" + repo_id.replace("/", "--")
    snapshots = _HF_CACHE / folder / "snapshots"
    if not snapshots.exists():
        return False
    # At least one snapshot must contain a weight file
    for snap in snapshots.iterdir():
        if any(snap.glob("*.safetensors")) or any(snap.glob("*.gguf")):
            return True
    return False


def run(prompt: str, model: str | None = None) -> tuple[str, str]:
    """
    Execute MLX inference non-interactively and return (output_text, actual_model_name).

    Raises:
        ExecutionError: on timeout, MLX failure, or server busy.
    """
    if not _semaphore.acquire(blocking=False):
        raise ExecutionError("Server busy, try again later.", status_code=503)

    target_model = MODEL_MAP.get(model, model or MODEL_MAP["mlx-qwen3"])

    # Fail fast if model is not fully downloaded yet
    if not _is_model_ready(target_model):
        _semaphore.release()
        raise ExecutionError(
            f"Model '{model}' is not ready (still downloading). Try again later.",
            status_code=503,
        )

    try:
        if target_model in _VLM_REPOS:
            cmd = [
                sys.executable, "-m", "mlx_vlm", "generate",
                "--model", target_model,
                "--prompt", prompt,
                "--max-tokens", "2048",
                "--temperature", "0.7",
            ]
        elif target_model in _NOTHINK_REPOS:
            # Qwen3: Python API with enable_thinking=False (verified 2.7s vs 200s+)
            # generate() signature: (model, tokenizer, prompt, verbose, **kwargs)
            # max_tokens is a valid kwarg; temperature/temp are NOT in this mlx_lm version
            script = (
                "import sys,os; os.environ['NO_COLOR']='1';"
                "from mlx_lm import load,generate;"
                "m,t=load(sys.argv[1]);"
                "msgs=[{'role':'user','content':sys.argv[2]}];"
                "txt=t.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=False);"
                "r=generate(m,t,prompt=txt,max_tokens=int(sys.argv[3]),verbose=False);"
                "print(r)"
            )
            cmd = [sys.executable, "-c", script, target_model, prompt, "2048"]
        else:
            cmd = [
                sys.executable, "-m", "mlx_lm", "generate",
                "--model", target_model,
                "--prompt", prompt,
                "--max-tokens", "2048",
                "--temp", "0.7",
            ]

        logger.info("Running MLX — model=%s prompt_len=%d", target_model, len(prompt))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.TIMEOUT_SECONDS,
            env={**os.environ, "NO_COLOR": "1"},  # suppress ANSI
        )

        output = result.stdout.strip()

        if not output and result.returncode != 0:
            stderr_tail = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
            err_msg = (
                f"MLX execution failed (rc={result.returncode}) "
                f"stderr_len={len(result.stderr)}. "
                f"TAIL: {stderr_tail}"
            )
            logger.error(err_msg)
            raise ExecutionError(err_msg)

        if result.returncode != 0:
            logger.warning("MLX returned rc=%d but output present (len=%d); stderr: %s",
                           result.returncode, len(output), result.stderr[:200])

        logger.info("MLX completed — model=%s output_len=%d rc=%d",
                    target_model, len(output), result.returncode)
        return output, target_model

    except subprocess.TimeoutExpired:
        logger.warning("MLX timed out after %ds", config.TIMEOUT_SECONDS)
        raise ExecutionError(f"Request timed out after {config.TIMEOUT_SECONDS}s.", status_code=504)

    finally:
        _semaphore.release()


def _glm_vlm_ready() -> bool:
    base_url = config.GLM_VLM_BASE_URL.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def _stop_process_group(process: subprocess.Popen | None, wait_seconds: float = 10) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=wait_seconds)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.error("Process group %d did not exit after SIGKILL", process.pid)


def _stop_glm_vlm() -> float:
    """Stop GLM-OCR's MLX-VLM process before Baidu runs, freeing memory."""
    global _glm_vlm_process
    started = time.monotonic()
    with _glm_vlm_process_lock:
        process = _glm_vlm_process
        _glm_vlm_process = None
        _stop_process_group(process)
    return time.monotonic() - started


def _ensure_glm_vlm(deadline: float) -> float:
    """Start or reuse the single GLM-OCR MLX-VLM process."""
    global _glm_vlm_process
    base_url = config.GLM_VLM_BASE_URL.rstrip("/")
    started = time.monotonic()
    with _glm_vlm_process_lock:
        if _glm_vlm_process is not None and _glm_vlm_process.poll() is not None:
            logger.error("GLM-OCR VLM process exited — rc=%s", _glm_vlm_process.returncode)
            _glm_vlm_process = None

        if _glm_vlm_process is None:
            glm_python = Path(config.GLM_VLM_PYTHON)
            if not glm_python.is_file():
                raise ExecutionError(
                    "GLM-OCR MLX runtime is not installed. Check the glm-mlx-venv deployment.",
                    status_code=503,
                )
            log_path = Path(config.GLM_VLM_LOG)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path.open("a", encoding="utf-8")
            cmd = [
                str(glm_python), "-m", "mlx_vlm.server",
                "--host", "127.0.0.1",
                "--port", str(config.GLM_VLM_PORT),
                "--model", "mlx-community/GLM-OCR-bf16",
                "--trust-remote-code",
            ]
            try:
                _glm_vlm_process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                log_file.close()
            logger.info("Started GLM-OCR VLM process pid=%d", _glm_vlm_process.pid)

        while time.monotonic() < deadline:
            if _glm_vlm_process is None or _glm_vlm_process.poll() is not None:
                rc = _glm_vlm_process.returncode if _glm_vlm_process else "unknown"
                raise ExecutionError(
                    f"GLM-OCR model server exited during startup (rc={rc}).",
                    status_code=503,
                )
            if _glm_vlm_ready():
                return time.monotonic() - started
            time.sleep(1)

    _stop_glm_vlm()
    raise ExecutionError(
        "GLM-OCR model server did not become ready before timeout.", status_code=504,
        details={"engine_ready_wait_s": round(time.monotonic() - started, 3)},
    )


def _timing_from_stderr(stderr: str) -> dict[str, float | int]:
    for line in reversed(stderr.splitlines()):
        if line.startswith(_OCR_TIMING_PREFIX):
            try:
                value = json.loads(line[len(_OCR_TIMING_PREFIX):])
                if isinstance(value, dict):
                    return value
            except (json.JSONDecodeError, TypeError):
                logger.warning("Ignoring malformed OCR timing record")
    return {}


def run_ocr(file_path: str, dpi: int = 200, engine: str = "baidu") -> tuple[str, dict[str, float | int | str]]:
    """
    Run Baidu Unlimited-OCR or GLM-OCR on a PDF or image file.
    Uses subprocess to isolate PyTorch and completely free memory on exit.
    """
    global _ocr_current_engine
    engine = engine.strip().lower()
    if engine not in config.OCR_ENGINES:
        raise ExecutionError(
            f"OCR engine '{engine}' is disabled. Enabled engines: {sorted(config.OCR_ENGINES)}",
            status_code=400,
        )
    queued_at = time.monotonic()
    queue_wait_s = _acquire_ocr_slot()
    started = time.monotonic()
    with _ocr_condition:
        _ocr_current_engine = engine

    timeout = config.GLM_OCR_TIMEOUT_SECONDS if engine == "glm" else config.TIMEOUT_SECONDS
    deadline = started + timeout
    runner_process: subprocess.Popen | None = None
    ready_wait_s = 0.0
    engine_release_s = 0.0
    try:
        if engine == "baidu":
            engine_release_s = _stop_glm_vlm()
            ocr_script = Path(__file__).parent / "ocr_run.py"
            cmd = [sys.executable, str(ocr_script), "--input", file_path, "--dpi", str(dpi)]
            model_repo = "baidu/Unlimited-OCR"
        elif engine == "glm":
            ready_wait_s = _ensure_glm_vlm(deadline)
            ocr_script = Path(__file__).parent / "glm_ocr_run.py"
            cmd = [sys.executable, str(ocr_script), "--input", file_path, "--dpi", str(dpi),
                   "--vlm-url", config.GLM_VLM_BASE_URL]
            model_repo = "mlx-community/GLM-OCR-bf16"
        else:  # defensive: the allowlist is the only supported source of engine names
            raise ExecutionError(f"Unsupported OCR engine: {engine}", status_code=400)

        logger.info("Running OCR — engine=%s file=%s dpi=%d", engine, Path(file_path).name, dpi)

        inference_started = time.monotonic()
        runner_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(cmd, timeout)
        stdout, stderr = runner_process.communicate(timeout=remaining)
        process_elapsed_s = time.monotonic() - inference_started

        output = stdout

        if runner_process.returncode != 0:
            stderr_tail = stderr[-1000:] if len(stderr) > 1000 else stderr
            err_msg = (
                f"OCR execution failed (rc={runner_process.returncode}) "
                f"stderr_len={len(stderr)}. "
                f"TAIL: {stderr_tail}"
            )
            logger.error(err_msg)
            raise ExecutionError(err_msg)

        runner_timings = _timing_from_stderr(stderr)
        timings: dict[str, float | int | str] = {
            "queue_wait_s": round(queue_wait_s, 3),
            "engine_ready_wait_s": round(ready_wait_s, 3),
            "engine_release_s": round(engine_release_s, 3),
            "process_elapsed_s": round(process_elapsed_s, 3),
            "total_elapsed_s": round(time.monotonic() - queued_at, 3),
            **runner_timings,
        }
        logger.info("OCR completed — engine=%s output_len=%d timings=%s", engine, len(output), timings)
        return output, {"engine": engine, "model": model_repo, **timings}

    except subprocess.TimeoutExpired:
        _stop_process_group(runner_process)
        if engine == "glm":
            _stop_glm_vlm()
        logger.warning("OCR timed out — engine=%s timeout=%ds", engine, timeout)
        raise ExecutionError(
            f"OCR request timed out after {timeout}s (engine={engine}).", status_code=504,
            details={
                "queue_wait_s": round(queue_wait_s, 3),
                "engine_ready_wait_s": round(ready_wait_s, 3),
                "process_elapsed_s": round(time.monotonic() - started, 3),
                "total_elapsed_s": round(time.monotonic() - queued_at, 3),
            },
        )
    except ExecutionError as error:
        error.details.update({
            "queue_wait_s": round(queue_wait_s, 3),
            "engine_ready_wait_s": round(ready_wait_s, 3),
            "engine_release_s": round(engine_release_s, 3),
            "process_elapsed_s": round(time.monotonic() - started, 3),
            "total_elapsed_s": round(time.monotonic() - queued_at, 3),
        })
        raise

    finally:
        _release_ocr_slot()


def shutdown_ocr_engines() -> None:
    """Free persistent OCR model memory when the API server is stopping."""
    _stop_glm_vlm()
