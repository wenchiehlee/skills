"""Run GLM-OCR through the local MLX-VLM OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import mimetypes
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TIMING_PREFIX = "OCR_TIMING_JSON="
MODEL = "mlx-community/GLM-OCR-bf16"
logger = logging.getLogger("glm_ocr_runner")


def _image_markdown(image: bytes, mime_type: str, api_url: str, timeout: float) -> str:
    data_uri = f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": "Text Recognition:"},
        ]}],
        "max_tokens": 8192,
        "temperature": 0,
        "top_p": 0.00001,
    }
    payload_bytes = json.dumps(body).encode("utf-8")
    payload = None
    # GLM-OCR's deployment guide documents the unversioned route; newer
    # mlx-vlm releases expose the OpenAI-compatible /v1 route.
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        request = urllib.request.Request(
            f"{api_url.rstrip('/')}{suffix}",
            data=payload_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            if error.code != 404 or suffix.startswith("/v1/"):
                raise
    if payload is None:
        raise RuntimeError("MLX-VLM did not return an OCR response")
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content).strip()


def _pages(input_path: Path, dpi: int):
    if input_path.suffix.lower() != ".pdf":
        mime_type = mimetypes.guess_type(input_path.name)[0] or "image/png"
        yield input_path.read_bytes(), mime_type
        return

    import fitz

    document = fitz.open(input_path)
    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)
    for page in document:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        yield pixmap.tobytes("png"), "image/png"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GLM-OCR on a PDF or image.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--vlm-url", required=True)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()

    try:
        started = time.monotonic()
        pages = []
        for page_number, (image, mime_type) in enumerate(_pages(args.input, args.dpi), start=1):
            logger.info("Recognizing page %d", page_number)
            pages.append(_image_markdown(image, mime_type, args.vlm_url, args.timeout))
        if not any(page.strip() for page in pages):
            raise RuntimeError("GLM-OCR returned empty output for every page")
        print("\n\n".join(pages))
        print(f"{TIMING_PREFIX}{json.dumps({'inference_s': round(time.monotonic() - started, 3)})}", file=sys.stderr)
        return 0
    except Exception:
        logger.exception("GLM-OCR request failed")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    raise SystemExit(main())
