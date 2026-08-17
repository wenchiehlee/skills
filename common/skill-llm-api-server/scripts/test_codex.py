"""
Tests for codex-cli related endpoints in main.py.
Uses Flask test client + unittest.mock to avoid real subprocess calls.
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


# ── helper ────────────────────────────────────────────────────────────────────

def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ── GET / ─────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ready"
    assert "LLM CLI API Server" in data["service"]


# ── GET /codex/status ─────────────────────────────────────────────────────────

def test_codex_status_installed(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="codex-cli 0.128.0")) as m:
        r = client.get("/codex/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["codex_cli"] == "installed"
    assert "0.128.0" in data["version"]
    m.assert_called_once_with(["codex", "--version"], capture_output=True, text=True, timeout=10)


def test_codex_status_not_found(client):
    with patch("main.subprocess.run", side_effect=FileNotFoundError):
        r = client.get("/codex/status")
    assert r.status_code == 503
    assert r.get_json()["codex_cli"] == "not_found"


def test_codex_status_timeout(client):
    with patch("main.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=10)):
        r = client.get("/codex/status")
    assert r.status_code == 504
    assert r.get_json()["codex_cli"] == "timeout"


def test_codex_status_error_returncode(client):
    with patch("main.subprocess.run", return_value=_make_proc(returncode=1, stderr="some error")):
        r = client.get("/codex/status")
    assert r.status_code == 500
    assert r.get_json()["codex_cli"] == "error"


# ── POST /exec ────────────────────────────────────────────────────────────────

def test_exec_codex_success(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="print('hello')\n")) as m:
        r = client.post("/exec", json={"prompt": "write hello world in python"})
    assert r.status_code == 200
    assert r.get_json()["output"] == "print('hello')"
    cmd_used = m.call_args[0][0]
    assert cmd_used[0] == "codex"
    assert "exec" in cmd_used
    assert "--skip-git-repo-check" in cmd_used
    assert "--yolo" in cmd_used


def test_exec_codex_missing_prompt(client):
    r = client.post("/exec", json={})
    assert r.status_code == 400
    assert "prompt is required" in r.get_json()["error"]


def test_exec_codex_empty_prompt(client):
    r = client.post("/exec", json={"prompt": "   "})
    assert r.status_code == 400


def test_exec_codex_no_json_body(client):
    r = client.post("/exec", data="not json", content_type="text/plain")
    assert r.status_code == 400


def test_exec_codex_timeout(client):
    with patch("main.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=120)):
        r = client.post("/exec", json={"prompt": "something slow"})
    assert r.status_code == 504
    assert "timed out" in r.get_json()["error"]


def test_exec_codex_cli_failure(client):
    with patch("main.subprocess.run", return_value=_make_proc(returncode=1, stderr="auth error")):
        r = client.post("/exec", json={"prompt": "hello"})
    assert r.status_code == 500
    assert "auth error" in r.get_json()["error"]


def test_exec_codex_cli_401_from_openai(client):
    """codex CLI exits with a 401 Unauthorized message from OpenAI (not logged in)."""
    openai_401 = "Error: 401 Unauthorized - invalid or missing OpenAI credentials"
    with patch("main.subprocess.run", return_value=_make_proc(returncode=1, stderr=openai_401)):
        r = client.post("/exec", json={"prompt": "hello"})
    assert r.status_code == 500
    data = r.get_json()
    assert "401" in data["error"] or "Unauthorized" in data["error"]


def test_exec_codex_unauthorized(client):
    import main as m_module
    original = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = "secret-key"
    try:
        r = client.post("/exec", json={"prompt": "hello"})
        assert r.status_code == 401
        assert "Unauthorized" in r.get_json()["error"]
    finally:
        m_module.CODEX_API_KEY = original


def test_exec_codex_authorized_with_key(client):
    import main as m_module
    original = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = "secret-key"
    try:
        with patch("main.subprocess.run", return_value=_make_proc(stdout="ok")):
            r = client.post(
                "/exec",
                json={"prompt": "hello"},
                headers={"X-API-Key": "secret-key"},
            )
        assert r.status_code == 200
    finally:
        m_module.CODEX_API_KEY = original


# ── GET /codex/help ───────────────────────────────────────────────────────────

def test_codex_help(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="Usage: codex ...")) as m:
        r = client.get("/codex/help")
    assert r.status_code == 200
    data = r.get_json()
    assert "Usage" in data["stdout"]
    cmd = m.call_args[0][0]
    assert cmd == ["codex", "--help"]


def test_codex_help_subcommand(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="exec help text")) as m:
        r = client.get("/codex/help/exec")
    assert r.status_code == 200
    cmd = m.call_args[0][0]
    assert cmd == ["codex", "exec", "--help"]


def test_codex_help_error(client):
    with patch("main.subprocess.run", side_effect=FileNotFoundError("codex not found")):
        r = client.get("/codex/help")
    assert r.status_code == 500
    assert "error" in r.get_json()


# ── _run_cli internal behaviour ───────────────────────────────────────────────

def test_run_cli_codex_command_structure(client):
    """Verify codex uses exec + --skip-git-repo-check + --yolo and passes prompt as last arg."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _make_proc(stdout="result")

    with patch("main.subprocess.run", side_effect=fake_run):
        r = client.post("/exec", json={"prompt": "my prompt"})

    assert r.status_code == 200
    assert captured["cmd"][0] == "codex"
    assert captured["cmd"][1] == "exec"
    assert "--skip-git-repo-check" in captured["cmd"]
    assert "--yolo" in captured["cmd"]
    assert captured["cmd"][-1] == "my prompt"


def test_run_cli_strips_trailing_whitespace(client):
    with patch("main.subprocess.run", return_value=_make_proc(stdout="  output with spaces  \n")):
        r = client.post("/exec", json={"prompt": "hello"})
    assert r.get_json()["output"] == "output with spaces"


def test_run_cli_excludes_codex_api_key_from_env(client):
    """CODEX_API_KEY must not be passed to the codex subprocess to avoid
    codex-cli treating our server access key as an OpenAI credential.
    GEMINI_SANDBOX=false must be added."""
    import main as m_module
    import os
    captured_env = {}

    original = m_module.CODEX_API_KEY
    m_module.CODEX_API_KEY = "server-access-key"

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        return _make_proc(stdout="result")

    with patch.dict(os.environ, {"CODEX_API_KEY": "server-access-key"}):
        with patch("main.subprocess.run", side_effect=fake_run):
            client.post("/exec", json={"prompt": "hello"})

    m_module.CODEX_API_KEY = original
    assert "CODEX_API_KEY" not in captured_env
    assert captured_env["GEMINI_SANDBOX"] == "false"
