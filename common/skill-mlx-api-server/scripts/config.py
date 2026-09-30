"""Configuration — loaded from .env file, then environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Production: deploy-mlx-api.yml flattens scripts/*.py into ~/mlx-api/, so in
# production __file__ sits directly next to .env there.
# Local dev: this file lives at skills/skill-mlx-api-server/scripts/config.py,
# four levels below the repo root, where the single-source-of-truth .env lives.
load_dotenv(Path(__file__).parent / ".env")             # production path
load_dotenv(Path(__file__).parents[3] / ".env")          # local dev fallback (no-op if above succeeded)


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


AMPLITUDE_API_KEY: str = _get("AMPLITUDE_API_KEY", "")

# ── Authentication ────────────────────────────────────────────────────────────
API_KEY: str = _require("MLX_SERVER_API_KEY")

if len(API_KEY) < 32:
    raise RuntimeError(
        "MLX_SERVER_API_KEY must be at least 32 characters. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Server ────────────────────────────────────────────────────────────────────
HOST: str = _get("MLX_SERVER_HOST", "127.0.0.1")
PORT: int = int(_get("MLX_SERVER_PORT", "5001"))

# ── MLX execution ─────────────────────────────────────────────────────────────
SANDBOX_DIR: Path = Path(_get("MLX_SANDBOX_DIR", str(Path.home() / "mlx-sandbox")))
TIMEOUT_SECONDS: int = int(_get("MLX_TIMEOUT", "180"))
MAX_CONCURRENT: int = int(_get("MLX_MAX_CONCURRENT", "3"))
OCR_QUEUE_MAX_SIZE: int = int(_get("MLX_OCR_QUEUE_MAX_SIZE", "8"))
OCR_QUEUE_WAIT_SECONDS: int = int(_get("MLX_OCR_QUEUE_WAIT_SECONDS", "1800"))
OCR_ENGINES: set[str] = {
    engine.strip().lower()
    for engine in _get("MLX_OCR_ENGINES", "baidu,glm").split(",")
    if engine.strip()
}.intersection({"baidu", "glm"})
GLM_VLM_PORT: int = int(_get("MLX_GLM_VLM_PORT", "8111"))
GLM_VLM_BASE_URL: str = _get(
    "MLX_GLM_VLM_BASE_URL", f"http://127.0.0.1:{GLM_VLM_PORT}"
)
GLM_VLM_LOG: str = _get(
    "MLX_GLM_VLM_LOG", str(Path.home() / "mlx-api" / "glm-vlm.log")
)
GLM_VLM_PYTHON: str = _get(
    "MLX_GLM_VLM_PYTHON", str(Path.home() / "mlx-api" / "glm-mlx-venv" / "bin" / "python")
)
GLM_OCR_TIMEOUT_SECONDS: int = int(
    _get("MLX_GLM_OCR_TIMEOUT", str(int(_get("MLX_TIMEOUT", "900"))))
)

# ── Input validation ──────────────────────────────────────────────────────────
MAX_PROMPT_LENGTH: int = int(_get("MLX_MAX_PROMPT_LENGTH", "16000"))
ALLOWED_MODELS: set[str] = set(
    _get("MLX_ALLOWED_MODELS", "mlx-qwen3,mlx-gemma4").split(",")
)
