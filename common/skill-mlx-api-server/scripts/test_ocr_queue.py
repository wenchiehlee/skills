"""Regression test that selected OCR engines still share one FIFO worker."""

from __future__ import annotations

import os
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("MLX_SERVER_API_KEY", "queue-test-only-key-0000000000000000")
try:
    import dotenv  # noqa: F401
except ImportError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: False
    sys.modules["dotenv"] = dotenv_stub
import config  # noqa: E402
import executor  # noqa: E402


class _FakeProcess:
    returncode = 0

    def __init__(self, command, **_kwargs):
        self.command = command
        self.pid = 12345

    def poll(self):
        return 0

    def communicate(self, timeout=None):
        active = _state["active"]
        active += 1
        _state["active"] = active
        _state["maximum"] = max(active, _state["maximum"])
        _state["engines"].append(executor._ocr_current_engine)
        time.sleep(0.08)
        _state["active"] -= 1
        return "recognized", ""


_state = {"active": 0, "maximum": 0, "engines": []}


class OCRQueueTests(unittest.TestCase):
    def test_baidu_and_paddle_requests_are_serialized(self):
        old_engines = config.OCR_ENGINES
        old_paddle_python = config.PADDLE_OCR_PYTHON
        config.OCR_ENGINES = {"baidu", "paddle"}
        config.PADDLE_OCR_PYTHON = sys.executable
        _state.update(active=0, maximum=0, engines=[])

        def run(engine):
            return executor.run_ocr("/tmp/queue-test.png", engine=engine)

        try:
            with (
                patch.object(executor.subprocess, "Popen", side_effect=_FakeProcess),
                patch.object(executor, "_stop_paddle_vlm", return_value=0.0),
                patch.object(executor, "_ensure_paddle_vlm", return_value=0.0),
            ):
                first = threading.Thread(target=run, args=("baidu",))
                second = threading.Thread(target=run, args=("paddle",))
                first.start()
                time.sleep(0.02)
                second.start()
                first.join(timeout=2)
                second.join(timeout=2)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(_state["maximum"], 1)
            self.assertEqual(_state["engines"], ["baidu", "paddle"])
            self.assertEqual(executor.ocr_queue_status(), {
                "active": False, "active_engine": None, "queued": 0
            })
        finally:
            config.OCR_ENGINES = old_engines
            config.PADDLE_OCR_PYTHON = old_paddle_python


if __name__ == "__main__":
    unittest.main()
