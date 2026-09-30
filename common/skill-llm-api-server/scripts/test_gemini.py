"""
Tests for gemini-related endpoints in main.py.

gemini-cli's consumer OAuth login was terminated by Google on 2026-06-18
(invalid_grant). /gemini/exec and /smart/exec (gemini) now call agy
(Antigravity CLI, OAuth, main._run_agy) instead of the old gemini binary.
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from main import app


@pytest.fixture
def client():
    import main as m_module

    original_api_key = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = ""
    app.config["TESTING"] = True
    try:
        with app.test_client() as c:
            yield c
    finally:
        m_module.CODEX_API_KEY = original_api_key


def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# -- GET /gemini/status --------------------------------------------------------

def test_gemini_status_installed(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="agy 1.1.22")) as m:
        r = client.get("/gemini/status")

    assert r.status_code == 200
    data = r.get_json()
    assert data["gemini_cli"] == "installed"
    assert data["tool"] == "agy"
    assert data["version"] == "agy 1.1.22"
    m.assert_called_once_with(["agy", "--version"], capture_output=True, text=True, timeout=10)


def test_gemini_status_not_found(client):
    with patch("main.subprocess.run", side_effect=FileNotFoundError):
        r = client.get("/gemini/status")

    assert r.status_code == 503
    assert r.get_json()["gemini_cli"] == "not_found"


def test_gemini_status_timeout(client):
    with patch("main.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=10)):
        r = client.get("/gemini/status")

    assert r.status_code == 504
    assert r.get_json()["gemini_cli"] == "timeout"


def test_gemini_status_error_returncode(client):
    with patch("main.subprocess.run", return_value=_make_proc(returncode=1, stderr="auth error")):
        r = client.get("/gemini/status")

    assert r.status_code == 500
    data = r.get_json()
    assert data["gemini_cli"] == "error"
    assert data["detail"] == "auth error"


# -- POST /gemini/exec ---------------------------------------------------------

def test_exec_gemini_success(client):
    with patch("main._run_agy", return_value="print('hello')\n") as m:
        r = client.post(
            "/gemini/exec",
            json={"prompt": "write hello world in python", "model": "gemini-2.5-flash"},
        )

    assert r.status_code == 200
    assert r.get_json()["output"] == "print('hello')"
    m.assert_called_once_with(
        "write hello world in python", model="gemini-2.5-flash", json_mode=False, timeout=120,
    )


def test_exec_gemini_success_without_model(client):
    with patch("main._run_agy", return_value="ok") as m:
        r = client.post("/gemini/exec", json={"prompt": "hello"})

    assert r.status_code == 200
    assert r.get_json()["output"] == "ok"
    m.assert_called_once_with("hello", model="", json_mode=False, timeout=120)


def test_exec_gemini_missing_prompt(client):
    r = client.post("/gemini/exec", json={})

    assert r.status_code == 400
    assert "prompt is required" in r.get_json()["error"]


def test_exec_gemini_empty_prompt(client):
    r = client.post("/gemini/exec", json={"prompt": "   "})

    assert r.status_code == 400


def test_exec_gemini_no_json_body(client):
    r = client.post("/gemini/exec", data="not json", content_type="text/plain")

    assert r.status_code == 400


def test_exec_gemini_timeout(client):
    with patch("main._run_agy", side_effect=subprocess.TimeoutExpired(cmd="agy", timeout=120)):
        r = client.post("/gemini/exec", json={"prompt": "something slow"})

    assert r.status_code == 504
    assert "timed out" in r.get_json()["error"]


def test_exec_gemini_cli_failure(client):
    with patch("main._run_agy", side_effect=RuntimeError("agy exited 1: not authenticated")):
        r = client.post("/gemini/exec", json={"prompt": "hello"})

    assert r.status_code == 500
    assert "not authenticated" in r.get_json()["error"]


def test_exec_gemini_unauthorized(client):
    import main as m_module

    original = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = "secret-key"
    try:
        r = client.post("/gemini/exec", json={"prompt": "hello"})
        assert r.status_code == 401
        assert "Unauthorized" in r.get_json()["error"]
    finally:
        m_module.CODEX_API_KEY = original


def test_exec_gemini_authorized_with_key(client):
    import main as m_module

    original = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = "secret-key"
    try:
        with patch("main._run_agy", return_value="ok"):
            r = client.post(
                "/gemini/exec",
                json={"prompt": "hello"},
                headers={"X-API-Key": "secret-key"},
            )
        assert r.status_code == 200
    finally:
        m_module.CODEX_API_KEY = original


# -- GET /gemini/help ----------------------------------------------------------

def test_gemini_help(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="Usage: agy ...")) as m:
        r = client.get("/gemini/help")

    assert r.status_code == 200
    data = r.get_json()
    assert "Usage" in data["stdout"]
    assert m.call_args[0][0] == ["agy", "--help"]


def test_gemini_help_error(client):
    with patch("main.subprocess.run", side_effect=FileNotFoundError("agy not found")):
        r = client.get("/gemini/help")

    assert r.status_code == 500
    assert "error" in r.get_json()


# -- _run_agy internal behaviour ------------------------------------------------

def test_run_agy_command_structure():
    import main as m_module

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_proc(stdout="result")

    with patch("main.subprocess.run", side_effect=fake_run):
        out = m_module._run_agy("my prompt", model="gemini-2.5-flash", json_mode=True)

    assert out == "result"
    assert captured["cmd"] == [
        "agy", "-p", "my prompt", "--dangerously-skip-permissions", "--model", "gemini-2.5-flash",
    ]


def test_run_agy_raises_on_nonzero_exit():
    import main as m_module

    with patch("main.subprocess.run", return_value=_make_proc(returncode=1, stderr="boom")):
        with pytest.raises(RuntimeError, match="boom"):
            m_module._run_agy("hello")


def test_run_cli_gemini_strips_trailing_whitespace(client):
    with patch("main._run_agy", return_value="  output with spaces  \n"):
        r = client.post("/gemini/exec", json={"prompt": "hello"})

    assert r.get_json()["output"] == "output with spaces"


# -- POST /smart/exec error diagnostics ----------------------------------------

def test_smart_exec_draft_auth_failure_returns_diagnostics(client):
    with patch("main.routing_manager.get_promoted_provider", return_value=None), patch(
        "main._run_agy",
        side_effect=RuntimeError("agy exited 1: 401 Unauthorized"),
    ):
        r = client.post(
            "/smart/exec",
            json={
                "task_name": "unit-test",
                "prompt": "hello",
                "draft_cli": "gemini",
                "judge_cli": "codex",
            },
        )

    assert r.status_code == 500
    data = r.get_json()
    assert data["smart_status"] == "error"
    assert data["fallback_reason"] == "auth_failure"
    assert data["failed_stage"] == "draft"
    assert data["provider"] == "gemini"
    assert "401 Unauthorized" in data["error"]


def test_smart_exec_judge_timeout_returns_diagnostics(client):
    with patch("main.routing_manager.get_promoted_provider", return_value=None), patch(
        "main._run_agy", return_value="draft answer",
    ), patch(
        "main.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=120),
    ):
        r = client.post(
            "/smart/exec",
            json={
                "task_name": "unit-test",
                "prompt": "hello",
                "draft_cli": "gemini",
                "judge_cli": "codex",
            },
        )

    assert r.status_code == 500
    data = r.get_json()
    assert data["smart_status"] == "error"
    assert data["fallback_reason"] == "timeout"
    assert data["failed_stage"] == "judge"
    assert data["provider"] == "codex"
