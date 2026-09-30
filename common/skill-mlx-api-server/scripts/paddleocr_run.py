#!/usr/bin/env python3
"""Run one PaddleOCR-VL 1.6 request using the loopback MLX-VLM server."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("paddleocr_runner")
TIMING_PREFIX = "OCR_TIMING_JSON="


def _render_pdf(pdf_path: Path, dpi: int, output_dir: Path) -> list[Path]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    page_paths: list[Path] = []
    scale = dpi / 72
    for index in range(len(pdf)):
        page = pdf[index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        image_path = output_dir / f"page_{index + 1:04d}.png"
        image.save(image_path)
        page_paths.append(image_path)
        image.close()
        bitmap.close()
        page.close()
    pdf.close()
    return page_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PaddleOCR-VL 1.6 on a PDF or image.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--vlm-url", required=True)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file does not exist: {args.input}")
    if not 72 <= args.dpi <= 600:
        parser.error("DPI must be between 72 and 600")

    total_started = time.monotonic()
    render_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="paddleocr_pages_") as tmp:
        tmp_dir = Path(tmp)
        if args.input.suffix.lower() == ".pdf":
            page_paths = _render_pdf(args.input, args.dpi, tmp_dir)
        else:
            page_paths = [args.input]
        render_seconds = time.monotonic() - render_started

        if not page_paths:
            raise RuntimeError("Input PDF has no pages")

        # Import after argument validation to make setup time measurable.
        from paddleocr import PaddleOCRVL

        setup_started = time.monotonic()
        pipeline = PaddleOCRVL(
            pipeline_version="v1.6",
            vl_rec_backend="mlx-vlm-server",
            vl_rec_server_url=args.vlm_url.rstrip("/") + "/",
            vl_rec_api_model_name="PaddlePaddle/PaddleOCR-VL-1.6",
        )
        setup_seconds = time.monotonic() - setup_started

        inference_started = time.monotonic()
        output_parts: list[str] = []
        output_dir = tmp_dir / "results"
        output_dir.mkdir()
        page_count = 0
        for index, page_path in enumerate(page_paths, start=1):
            logger.info("Recognizing page %d/%d", index, len(page_paths))
            results = pipeline.predict(input=str(page_path))
            for result in results:
                result_dir = output_dir / f"result_{index:04d}"
                result_dir.mkdir()
                result.save_to_markdown(str(result_dir / f"page_{index:04d}"))
                generated = sorted(result_dir.glob("*.md"))
                if generated:
                    output_parts.append(generated[-1].read_text(encoding="utf-8").strip())
                page_count += 1
        inference_seconds = time.monotonic() - inference_started

    markdown = "\n\n".join(part for part in output_parts if part)
    print(markdown, end="\n" if markdown else "")
    timings = {
        "pdf_render_s": round(render_seconds, 3),
        "pipeline_setup_s": round(setup_seconds, 3),
        "inference_s": round(inference_seconds, 3),
        "pages": page_count,
        "runner_total_s": round(time.monotonic() - total_started, 3),
    }
    print(TIMING_PREFIX + json.dumps(timings, separators=(",", ":")), file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("PaddleOCR-VL request failed")
        raise SystemExit(1)
