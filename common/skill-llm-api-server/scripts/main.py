import json
import logging
import os
import subprocess
import time
from pathlib import Path
from threading import Lock

from flask import Flask, jsonify, request
from waitress import serve

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CODEX_API_KEY = os.getenv("CODEX_API_KEY", "")
CODEX_TIMEOUT = int(os.getenv("CODEX_TIMEOUT", "120"))
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "120"))
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ROUTING_FILE = os.getenv("ROUTING_FILE", "/app/data/routing.json")


def _prompt_limit(name: str) -> int:
    raw = os.getenv(name, "60000").strip()
    try:
        return max(int(raw), 0)
    except ValueError:
        logger.warning("忽略無效的 %s=%r；使用 60000", name, raw)
        return 0


# 60000 為 server-side 預設字元上限；CLI、gateway 與模型本身仍可能有 context limit。
CODEX_MAX_PROMPT_LENGTH = _prompt_limit("CODEX_MAX_PROMPT_LENGTH")
GEMINI_MAX_PROMPT_LENGTH = _prompt_limit("GEMINI_MAX_PROMPT_LENGTH")


class PromptTooLong(ValueError):
    def __init__(self, cli_name: str, actual: int, limit: int):
        self.cli_name = cli_name
        self.actual = actual
        self.limit = limit
        super().__init__(f"{cli_name} prompt exceeds server limit ({actual} > {limit})")


def _check_prompt_length(cli_name: str, prompt: str) -> None:
    limit = CODEX_MAX_PROMPT_LENGTH if cli_name == "codex" else GEMINI_MAX_PROMPT_LENGTH
    if limit and len(prompt) > limit:
        raise PromptTooLong(cli_name, len(prompt), limit)


def _run_agy(prompt: str, model: str = "", json_mode: bool = False, timeout: int = GEMINI_TIMEOUT, effort: str = "") -> str:
    """呼叫 agy（Antigravity CLI，取代已停用的 gemini-cli）的非互動模式。

    subprocess.run 的 timeout 同時是對 issue #318（`agy -p` 在非 TTY 環境下可能
    卡住不回傳）的安全網：卡住的子行程會在 timeout 秒後被強制終止。
    """
    cmd = ["agy", "-p", prompt, "--dangerously-skip-permissions"]
    if model:
        if effort and "(" not in model:
            eff_title = effort.strip().title()
            if eff_title in ("Low", "Medium", "High"):
                model = f"{model} ({eff_title})"
        cmd.extend(["--model", model])
    # json_mode 目前透過 prompt 指示達成，agy 尚無對應的強制 JSON 輸出旗標
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"agy exited {result.returncode}: {detail}")
    return result.stdout.strip()


class ServerRoutingManager:
    def __init__(self, path=ROUTING_FILE, min_samples=10, threshold=0.8):
        self.path = Path(path)
        self.min_samples = min_samples
        self.threshold = threshold
        self._data = {}
        self._lock = Lock()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error("Failed to load server routing file: %s", e)
                self._data = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save server routing file: %s", e)

    def get_promoted_provider(self, task_name):
        with self._lock:
            return self._data.get(task_name, {}).get("promoted_to")

    def record(self, task_name, success, provider):
        with self._lock:
            if task_name not in self._data:
                self._data[task_name] = {"success": 0, "fail": 0, "promoted_to": None}
            stats = self._data[task_name]
            if success:
                stats["success"] += 1
            else:
                stats["fail"] += 1

            total = stats["success"] + stats["fail"]
            if not stats.get("promoted_to") and total >= self.min_samples:
                if (stats["success"] / total) >= self.threshold:
                    stats["promoted_to"] = provider
                    logger.info("Task '%s' promoted to %s on server (rate: %.1f%%)",
                                task_name, provider, (stats["success"] / total) * 100)
            self._save()


routing_manager = ServerRoutingManager()


def _check_api_key() -> bool:
    if not CODEX_API_KEY:
        return True
    return request.headers.get("X-API-Key") == CODEX_API_KEY


def _classify_cli_error(exc: Exception) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(exc, FileNotFoundError):
        return "cli_not_found"

    message = str(exc).lower()
    quota_markers = ("429", "rate limit", "quota", "usage limit", "too many requests", "resource exhausted")
    if any(marker in message for marker in quota_markers):
        return "quota_exceeded"

    auth_markers = ("401", "unauthorized", "unauthenticated", "auth", "credential", "token", "login")
    if any(marker in message for marker in auth_markers):
        return "auth_failure"
    if "exited " in message:
        return "nonzero_exit"
    return "unknown_error"


def _run_cli(cli_name: str, prompt: str, model: str = "", json_mode: bool = False, effort: str = "") -> str:
    """共通 CLI 執行邏輯。"""
    _check_prompt_length(cli_name, prompt)
    if cli_name == "gemini":
        # gemini-cli 的 OAuth 登入已於 2026-06-18 隨消費者方案停用（invalid_grant），
        # 改用 agy（Antigravity CLI，OAuth 登入已於本機完成，見
        # skills/skill-llm-api-server/scripts/renew-agy-auth.sh）。
        start = time.monotonic()
        logger.info("CLI start: cli=agy prompt_chars=%s model=%s effort=%s json_mode=%s",
                    len(prompt), model or GEMINI_DEFAULT_MODEL, effort or "-", json_mode)
        try:
            agy_kwargs = {"model": model, "json_mode": json_mode, "timeout": GEMINI_TIMEOUT}
            if effort:
                agy_kwargs["effort"] = effort
            output = _run_agy(prompt, **agy_kwargs)
        except Exception:
            logger.warning("CLI failed: cli=agy elapsed=%.1fs", time.monotonic() - start)
            raise
        logger.info("CLI success: cli=agy elapsed=%.1fs output_chars=%s",
                    time.monotonic() - start, len(output))
        return output.strip()

    if cli_name == "codex":
        cmd = ["codex", "exec", "--skip-git-repo-check", "--yolo"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        timeout = CODEX_TIMEOUT
    else:
        raise ValueError(f"Unknown CLI: {cli_name}")

    # Strip CODEX_API_KEY from subprocess env so codex-cli uses its OAuth token
    # instead of treating our server access key as an OpenAI credential.
    child_env = {k: v for k, v in os.environ.items() if k != "CODEX_API_KEY"}
    child_env["GEMINI_SANDBOX"] = "false"

    start = time.monotonic()
    logger.info(
        "CLI start: cli=%s timeout=%ss prompt_chars=%s model=%s json_mode=%s",
        cli_name,
        timeout,
        len(prompt),
        model or "-",
        json_mode,
    )
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        logger.warning("CLI timeout: cli=%s elapsed=%.1fs timeout=%ss", cli_name, elapsed, timeout)
        raise

    elapsed = time.monotonic() - start
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        logger.warning("CLI failed: cli=%s elapsed=%.1fs returncode=%s", cli_name, elapsed, result.returncode)
        raise RuntimeError(f"{cli_name} exited {result.returncode}: {detail}")

    logger.info("CLI success: cli=%s elapsed=%.1fs output_chars=%s", cli_name, elapsed, len(result.stdout))
    return result.stdout.strip()


# ── 基本端點 ──────────────────────────────────────────────────────────────────

@app.route("/")
def hello():
    return jsonify({"status": "ready", "service": "LLM CLI API Server"})


@app.route("/codex/status")
def codex_status():
    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            return jsonify({"codex_cli": "installed", "version": version})
        return jsonify({"codex_cli": "error", "detail": result.stderr.strip()}), 500
    except FileNotFoundError:
        return jsonify({"codex_cli": "not_found"}), 503
    except subprocess.TimeoutExpired:
        return jsonify({"codex_cli": "timeout"}), 504


@app.route("/tunnel/status")
def tunnel_status():
    tunnel_id = os.getenv("OPENAI_TUNNEL_ID", "")
    has_runtime_key = bool(os.getenv("OPENAI_TUNNEL_RUNTIME_KEY"))
    pid_file = Path("/tmp/openai_tunnel.pid")
    health_url_file = Path("/app/data/openai-tunnel/tunnel-health.url")
    log_file = Path("/tmp/openai_tunnel.log")

    supervisor_running = False
    supervisor_pid = None
    if pid_file.exists():
        try:
            supervisor_pid = int(pid_file.read_text().strip())
            os.kill(supervisor_pid, 0)
            supervisor_running = True
        except (ValueError, OSError):
            supervisor_running = False

    client_pids = []
    try:
        res = subprocess.run(["pgrep", "-f", "tunnel-client run"], capture_output=True, text=True)
        if res.returncode == 0:
            client_pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
    except Exception:
        pass

    client_running = len(client_pids) > 0

    health_url = None
    health_status = None
    if health_url_file.exists():
        try:
            health_url = health_url_file.read_text().strip()
            if health_url:
                try:
                    import urllib.request
                    with urllib.request.urlopen(f"{health_url}/readyz", timeout=2) as r:
                        health_status = r.read().decode("utf-8", errors="replace").strip()
                except Exception as he:
                    health_status = f"unreachable: {he}"
        except OSError:
            pass

    log_tail = []
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = lines[-25:]
        except Exception as e:
            log_tail = [f"Error reading log: {e}"]

    return jsonify({
        "tunnel_id": tunnel_id or None,
        "configured": bool(tunnel_id and has_runtime_key),
        "running": client_running,
        "supervisor_running": supervisor_running,
        "supervisor_pid": supervisor_pid,
        "client_pids": client_pids,
        "health_url": health_url,
        "health_status": health_status,
        "log_tail": log_tail,
    })


@app.route("/tunnel/doctor")
def tunnel_doctor():
    profiles_dir = "/app/data/openai-tunnel/profiles"
    env = {**os.environ}
    if os.getenv("OPENAI_TUNNEL_RUNTIME_KEY"):
        env["CONTROL_PLANE_API_KEY"] = os.getenv("OPENAI_TUNNEL_RUNTIME_KEY")
    if os.getenv("OPENAI_TUNNEL_ID"):
        env["CONTROL_PLANE_TUNNEL_ID"] = os.getenv("OPENAI_TUNNEL_ID")
    try:
        res = subprocess.run(
            ["tunnel-client", "doctor", "--profile", "local-workspace", "--profile-dir", profiles_dir, "--explain"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        return jsonify({
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tunnel/restart", methods=["POST"])
def tunnel_restart():
    if not _check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    pid_file = Path("/tmp/openai_tunnel.pid")
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            os.kill(old_pid, 9)
        except Exception:
            pass
    try:
        subprocess.run(["pkill", "-9", "-f", "tunnel-client"], capture_output=True)
    except Exception:
        pass
    if Path("/app/scripts/start-openai-tunnel.sh").exists():
        subprocess.Popen(["bash", "/app/scripts/start-openai-tunnel.sh"])
    return jsonify({"status": "restarting"})


# ── Codex exec 端點（相容 llm CodexProvider：POST /exec）────────────────────

@app.route("/exec", methods=["POST"])
def exec_codex():
    if not _check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "").strip()
    model = body.get("model", "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        output = _run_cli("codex", prompt, model=model)
        return jsonify({"output": output})
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"codex timed out after {CODEX_TIMEOUT}s"}), 504
    except PromptTooLong as e:
        return jsonify({"error": str(e), "limit": e.limit, "prompt_chars": e.actual}), 413
    except Exception as e:
        err_type = _classify_cli_error(e)
        logger.exception("exec_codex 發生錯誤 (%s)", err_type)
        return jsonify({"error": str(e), "error_type": err_type}), 500


@app.route("/codex/help")
@app.route("/codex/help/<subcommand>")
def codex_help(subcommand=None):
    try:
        cmd = ["codex", subcommand, "--help"] if subcommand else ["codex", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
        return jsonify({"stdout": result.stdout, "stderr": result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Gemini 端點 ───────────────────────────────────────────────────────────────

@app.route("/gemini/status")
def gemini_status():
    # gemini-cli 的 OAuth 登入已於 2026-06-18 隨消費者方案停用（invalid_grant）。
    # /gemini/exec 已改用 agy（OAuth，見 renew-agy-auth.sh）。
    try:
        result = subprocess.run(["agy", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            return jsonify({"gemini_cli": "installed", "tool": "agy", "auth_mode": "oauth", "version": version})
        return jsonify({"gemini_cli": "error", "tool": "agy", "detail": result.stderr.strip()}), 500
    except FileNotFoundError:
        return jsonify({"gemini_cli": "not_found", "tool": "agy"}), 503
    except subprocess.TimeoutExpired:
        return jsonify({"gemini_cli": "timeout", "tool": "agy"}), 504


@app.route("/gemini/exec", methods=["POST"])
def exec_gemini():
    if not _check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "").strip()
    model = body.get("model", "").strip()
    effort = body.get("effort", "").strip()
    json_mode = body.get("json_mode", False)
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        output = _run_cli("gemini", prompt, model=model, json_mode=json_mode, effort=effort)
        return jsonify({"output": output})
    except subprocess.TimeoutExpired:
        return jsonify({"error": f"gemini timed out after {GEMINI_TIMEOUT}s"}), 504
    except PromptTooLong as e:
        return jsonify({"error": str(e), "limit": e.limit, "prompt_chars": e.actual}), 413
    except Exception as e:
        err_type = _classify_cli_error(e)
        logger.exception("exec_gemini 發生錯誤 (%s)", err_type)
        return jsonify({"error": str(e), "error_type": err_type}), 500


@app.route("/gemini/models")
def gemini_models():
    """回傳 agy 支援的模型與可選的 reasoning effort 等級。"""
    return jsonify({
        "current_default": "Gemini 3.8 Flash (Medium)",
        "available_models": [
            "Gemini 3.8 Flash (High)",
            "Gemini 3.8 Flash (Medium)",
            "Gemini 3.8 Flash (Low)",
            "Gemini 3.7 Flash (High)",
            "Gemini 3.7 Flash (Medium)",
            "Gemini 3.7 Flash (Low)",
            "Gemini 3.6 Flash (High)",
            "Gemini 3.6 Flash (Medium)",
            "Gemini 3.6 Flash (Low)",
            "Gemini 3.1 Pro (High)",
            "Gemini 3.1 Pro (Low)",
            "Claude Sonnet 4.6 (Thinking)",
            "Claude Opus 4.6 (Thinking)",
            "GPT-OSS 120B (Medium)",
        ],
        "available_efforts": ["low", "medium", "high"],
    })


@app.route("/gemini/help")
def gemini_help():
    try:
        result = subprocess.run(
            ["agy", "--help"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
        return jsonify({"stdout": result.stdout, "stderr": result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Smart Routing 端點 ────────────────────────────────────────────────────────

@app.route("/smart/exec", methods=["POST"])
def exec_smart():
    if not _check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    task_name = body.get("task_name", "").strip()
    prompt = body.get("prompt", "").strip()
    draft_cli = body.get("draft_cli", "gemini").strip()
    judge_cli = body.get("judge_cli", "gemini").strip()
    model = body.get("model", "").strip()
    json_mode = body.get("json_mode", False)

    if not task_name or not prompt:
        return jsonify({"error": "task_name and prompt are required"}), 400

    promoted_provider = routing_manager.get_promoted_provider(task_name)

    # 狀態 A: 已達標
    if promoted_provider == draft_cli:
        try:
            output = _run_cli(draft_cli, prompt, model=model, json_mode=json_mode)
            return jsonify({"output": output, "smart_status": "promoted", "provider": draft_cli})
        except Exception as e:
            logger.warning("SmartRoute [%s] promoted provider %s failed: %s", task_name, draft_cli, e)
            # Fallback to normal exec logic below

    # 狀態 B: 評估階段 (Judging)
    failed_stage = "draft"
    provider = draft_cli
    try:
        # 1. 取得草稿
        draft_output = _run_cli(draft_cli, prompt, model=model, json_mode=json_mode)

        # 2. 評審
        failed_stage = "judge"
        provider = judge_cli
        judge_prompt = (
            f"你是評審員。以下是使用者的問題與本地模型的回答。\n"
            f"如果本地模型的回答已經達到你的水準（正確、完整且格式正確），請回覆：OK\n"
            f"如果本地模型的回答不夠好，請直接回覆你認為正確的完整答案。\n\n"
            f"問題：{prompt}\n"
            f"本地回答：{draft_output}"
        )
        judge_output = _run_cli(judge_cli, judge_prompt, model=model, json_mode=json_mode)

        # 3. 判斷
        if judge_output.upper() == "OK" or judge_output.upper().startswith("OK"):
            routing_manager.record(task_name, True, draft_cli)
            return jsonify({"output": draft_output, "smart_status": "judging_ok", "provider": draft_cli})
        else:
            routing_manager.record(task_name, False, draft_cli)
            return jsonify({"output": judge_output, "smart_status": "judging_fail", "provider": judge_cli})

    except PromptTooLong as e:
        return jsonify({"error": str(e), "limit": e.limit, "prompt_chars": e.actual}), 413
    except Exception as e:
        logger.exception("exec_smart 發生錯誤")
        return jsonify({
            "error": str(e),
            "smart_status": "error",
            "fallback_reason": _classify_cli_error(e),
            "failed_stage": failed_stage,
            "provider": provider,
        }), 500


if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5001)
