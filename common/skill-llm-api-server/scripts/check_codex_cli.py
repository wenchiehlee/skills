#!/usr/bin/env python3
"""
Smoke test for the Codex CLI API endpoints.

Usage:
    python check_codex_cli.py
    CODEX_API_KEY=your-key \
    python check_codex_cli.py
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_CANDIDATES = [
    "https://api.wenchiehlee.synology.me:8443",
    "http://llm-cli-api.tail28f10.ts.net:5001",
]


def resolve_api_url() -> str:
    env_url = os.getenv("CODEX_API_URL", "").strip().rstrip("/")
    if env_url:
        return env_url
    for cand in DEFAULT_CANDIDATES:
        try:
            req = urllib.request.Request(f"{cand}/codex/status", method="GET")
            if os.getenv("CODEX_API_KEY"):
                req.add_header("X-API-Key", os.getenv("CODEX_API_KEY"))
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    return cand
        except Exception:
            continue
    return DEFAULT_CANDIDATES[0]


API_URL = resolve_api_url()
API_KEY = os.getenv("CODEX_API_KEY", "")
TIMEOUT = int(os.getenv("CODEX_TEST_TIMEOUT", "180"))


def request_json(method, path, payload=None):
    data = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    if API_KEY:
        headers["X-API-Key"] = API_KEY

    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"error": body}
        return e.code, detail
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        return 0, {"error": str(e)}


def main():
    print(f"Testing Codex API: {API_URL}")

    status_code, status_body = request_json("GET", "/codex/status")
    print(f"/codex/status -> HTTP {status_code}")
    print(json.dumps(status_body, ensure_ascii=False, indent=2))
    if status_code != 200:
        print("Codex CLI is not available or not authenticated enough to report status.", file=sys.stderr)
        return 1

    prompt = (
        "Reply with exactly this JSON and no markdown: "
        '{"ok": true, "tool": "codex-cli"}'
    )
    exec_code, exec_body = request_json("POST", "/exec", {"prompt": prompt})
    print(f"/exec -> HTTP {exec_code}")
    print(json.dumps(exec_body, ensure_ascii=False, indent=2))

    if exec_code != 200:
        print("Codex CLI execution failed.", file=sys.stderr)
        return 1

    output = exec_body.get("output", "")
    if "codex-cli" not in output:
        print("Codex CLI returned output, but it did not match the expected smoke-test marker.", file=sys.stderr)
        return 1

    print("Codex CLI smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
