"""Codex execution — subprocess management, sandboxing, concurrency control."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_semaphore = threading.Semaphore(config.MAX_CONCURRENT)


class ExecutionError(Exception):
    """Raised when codex exec fails or times out."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


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


def run_ocr(file_path: str, dpi: int = 200) -> str:
    """
    Run Baidu Unlimited-OCR on a PDF or image file and return the transcribed markdown.
    Uses subprocess to isolate PyTorch and completely free memory on exit.
    """
    if not _semaphore.acquire(blocking=False):
        raise ExecutionError("Server busy, try again later.", status_code=503)

    try:
        ocr_script = Path(__file__).parent / "ocr_run.py"
        cmd = [
            sys.executable, str(ocr_script),
            "--input", file_path,
            "--dpi", str(dpi)
        ]

        logger.info("Running OCR — file=%s dpi=%d", file_path, dpi)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.TIMEOUT_SECONDS,
        )

        output = result.stdout

        if result.returncode != 0:
            stderr_tail = result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr
            err_msg = (
                f"OCR execution failed (rc={result.returncode}) "
                f"stderr_len={len(result.stderr)}. "
                f"TAIL: {stderr_tail}"
            )
            logger.error(err_msg)
            raise ExecutionError(err_msg)

        logger.info("OCR completed — output_len=%d", len(output))
        return output

    except subprocess.TimeoutExpired:
        logger.warning("OCR timed out after %ds", config.TIMEOUT_SECONDS)
        raise ExecutionError(f"OCR request timed out after {config.TIMEOUT_SECONDS}s.", status_code=504)

    finally:
        _semaphore.release()

