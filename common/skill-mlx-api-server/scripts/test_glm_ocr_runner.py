"""Regression tests for GLM-OCR's local MLX-VLM request contract."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from glm_ocr_run import MODEL, _image_markdown


class GlmOcrRunnerTests(unittest.TestCase):
    def test_sends_image_with_official_text_recognition_prompt(self):
        response = io.BytesIO(json.dumps({
            "choices": [{"message": {"content": "Revenue\n| Q1 | Q2 |"}}]
        }).encode())
        with patch("glm_ocr_run.urllib.request.urlopen", return_value=response) as urlopen:
            result = _image_markdown(b"png-bytes", "image/png", "http://127.0.0.1:8111", 30)

        self.assertEqual(result, "Revenue\n| Q1 | Q2 |")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "http://127.0.0.1:8111/chat/completions")
        self.assertEqual(payload["model"], MODEL)
        content = payload["messages"][0]["content"]
        self.assertEqual(content[1]["text"], "Text Recognition:")
        self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
