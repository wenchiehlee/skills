#!/usr/bin/env python3
"""Regression test for reading PaddleOCR's saved Markdown output."""
from pathlib import Path
import tempfile
import unittest

from paddleocr_run import _save_result_markdown


class FakePaddleResult:
    def save_to_markdown(self, save_path: str) -> None:
        # Match PaddleOCR's documented contract: save_path is a directory.
        output_dir = Path(save_path)
        (output_dir / "page_0001.md").write_text("Revenue\n\n| 2026 | 10 |", encoding="utf-8")


class PaddleMarkdownSaveTest(unittest.TestCase):
    def test_reads_markdown_written_under_save_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _save_result_markdown(FakePaddleResult(), Path(tmp) / "result")
        self.assertIn("Revenue", result)
        self.assertIn("| 2026 | 10 |", result)


if __name__ == "__main__":
    unittest.main()
