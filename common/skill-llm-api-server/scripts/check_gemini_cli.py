#!/usr/bin/env python3
"""
Smoke test for the Gemini CLI API endpoints.

Usage:
    python check_gemini_cli.py
    CODEX_API_URL=https://api.wenchiehlee.synology.me:8443 \
    CODEX_API_KEY=your-key \
    python check_gemini_cli.py
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request


API_URL = os.getenv("CODEX_API_URL", "http://newton.tail28f10.ts.net:5055").rstrip("/")
API_KEY = os.getenv("CODEX_API_KEY", "")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TIMEOUT = int(os.getenv("GEMINI_TEST_TIMEOUT", "180"))


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
    print(f"Testing Gemini API: {API_URL}")

    status_code, status_body = request_json("GET", "/gemini/status")
    print(f"/gemini/status -> HTTP {status_code}")
    print(json.dumps(status_body, ensure_ascii=False, indent=2))
    if status_code != 200:
        print("Gemini CLI is not available or not authenticated enough to report status.", file=sys.stderr)
        return 1

    prompt = (
        "Reply with exactly this JSON and no markdown: "
        '{"ok": true, "tool": "gemini-cli"}'
    )
    exec_code, exec_body = request_json(
        "POST",
        "/gemini/exec",
        {"prompt": prompt, "model": MODEL, "json_mode": True},
    )
    print(f"/gemini/exec -> HTTP {exec_code}")
    print(json.dumps(exec_body, ensure_ascii=False, indent=2))

    if exec_code != 200:
        print("Gemini CLI execution failed.", file=sys.stderr)
        return 1

    output = exec_body.get("output", "")
    if "gemini-cli" not in output:
        print("Gemini CLI returned output, but it did not match the expected smoke-test marker.", file=sys.stderr)
        return 1

    print("Gemini CLI smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
