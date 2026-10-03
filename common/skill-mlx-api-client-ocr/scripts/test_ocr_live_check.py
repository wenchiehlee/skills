#!/usr/bin/env python3
"""Regression tests for the OCR server live check."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

sys.path.insert(0, str(Path(__file__).parent))
import ocr_client  # noqa: E402


class OCRLiveCheckTest(unittest.TestCase):
    @patch("ocr_client.requests.get")
    def test_live_check_uses_health_endpoint(self, get: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"status": "ok", "ocr": {"queued": 0}}
        get.return_value = response

        result = ocr_client.check_ocr_server_live()

        self.assertEqual(result["status"], "ok")
        get.assert_called_once_with(ocr_client.OCR_HEALTH_URL, timeout=5.0)

    @patch("ocr_client.requests.get")
    def test_live_check_rejects_non_ok_health_status(self, get: Mock) -> None:
        response = Mock(status_code=200)
        response.json.return_value = {"status": "degraded"}
        get.return_value = response

        with self.assertRaises(ocr_client.OCRRequestError):
            ocr_client.check_ocr_server_live()


if __name__ == "__main__":
    unittest.main()
