#!/usr/bin/env python3
"""Regression test: empty image OCR must preserve an available PDF text layer."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# dotenv is an optional runtime dependency for this focused logic test.
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS))
import refine_todo_ocr as refine  # noqa: E402


class _Page:
    def get_text(self, _kind: str) -> str:
        return "31\nThank you\n"


class _Document:
    page_count = 1

    def load_page(self, _index: int) -> _Page:
        return _Page()

    def close(self) -> None:
        pass


class EmptyOCRPreservesPDFTextTest(unittest.TestCase):
    def test_empty_paddle_output_falls_back_to_embedded_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "report.pdf"
            pdf.write_bytes(b"test fixture")
            md = root / "report.md"
            md.write_text(
                '<!-- PAGE:1 -->\n## 第 1 頁\n\n'
                '<!-- TODO:OCR source="report.pdf" page=1 reason=scanned-page -->\n',
                encoding="utf-8",
            )
            rendered = root / "page.png"
            rendered.write_bytes(b"fake png")
            fake_fitz = types.SimpleNamespace(open=lambda _path: _Document())
            with (
                patch.object(refine, "_render_single_page_png", return_value=rendered),
                patch.object(refine, "transcribe_document_to_markdown", return_value=""),
                patch.dict(sys.modules, {"fitz": fake_fitz}),
            ):
                refine.refine(md, pdf, {1}, 200, "paddle")

            result = md.read_text(encoding="utf-8")
            self.assertIn("Thank you", result)
            self.assertNotIn("no text recognized", result)
            self.assertIn('engine="mac-mini-paddle"', result)
            self.assertIn('content_source="pdf-text-layer-fallback"', result)

    def test_existing_empty_result_can_be_repaired_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "report.pdf"
            pdf.write_bytes(b"test fixture")
            md = root / "report.md"
            md.write_text(
                '<!-- mac-mini-ocr:hybrid-base source="report.pdf" extractor="fitz" -->\n'
                '<!-- PAGE:1 -->\n## 第 1 頁\n\n'
                '<!-- OCR:done source="report.pdf" page=1 date="2026-09-30" engine="mac-mini-paddle" -->\n'
                f"{refine.NO_TEXT_RESULT}\n",
                encoding="utf-8",
            )
            fake_fitz = types.SimpleNamespace(open=lambda _path: _Document())
            with patch.dict(sys.modules, {"fitz": fake_fitz}):
                repaired = refine.repair_empty_ocr_results(md, pdf, {1})

            result = md.read_text(encoding="utf-8")
            self.assertEqual(repaired, 1)
            self.assertIn("Thank you", result)
            self.assertNotIn("no text recognized", result)
            self.assertIn('engine="mac-mini-paddle"', result)
            self.assertIn('content_source="pdf-text-layer-fallback"', result)


if __name__ == "__main__":
    unittest.main()
