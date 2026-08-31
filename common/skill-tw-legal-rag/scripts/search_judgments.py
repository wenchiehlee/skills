#!/usr/bin/env python3
"""Run `twlegalrag pack` for a question and print the bundle JSON to stdout.

Thin wrapper used by the tw-legal-rag Claude Code skill. It only locates the
CLI and forwards arguments — all retrieval logic lives in the twlegalrag
package. Works on macOS / Linux / Windows, including user-site installs where
the console script is not on PATH.

Based on the upstream skill's search_judgments.py
(https://github.com/aa0101181514/tw-legal-rag), with an added Windows
user-site Scripts directory fallback: a plain `pip install twlegalrag`
without admin rights installs into `%APPDATA%\\Python\\Python3XX\\Scripts`,
which is not on PATH by default and is easy to miss.
"""

from __future__ import annotations

import argparse
import shutil
import site
import subprocess
import sys
from pathlib import Path


def _windows_user_scripts_candidates() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        base = Path(site.getuserbase())
    except Exception:
        return []
    # Windows user scheme nests Scripts under a PythonXY version folder
    # (base itself is version-agnostic) — try both layouts to be safe.
    version_dir = f"Python{sys.version_info.major}{sys.version_info.minor}"
    candidates_dirs = [base / version_dir / "Scripts", base / "Scripts"]
    found: list[Path] = []
    for scripts_dir in candidates_dirs:
        if scripts_dir.is_dir():
            found.extend(sorted(scripts_dir.glob("twlegalrag*.exe")))
    return found


def _cli_command() -> list[str]:
    """Return the command vector for the twlegalrag CLI.

    Preference order:
    1. `twlegalrag` console script on PATH (shutil.which also finds .exe on
       Windows).
    2. Windows user-site `Scripts/twlegalrag*.exe` — covers `pip install
       --user` (or no-admin) installs whose Scripts dir never lands on PATH.
    3. `<current python> -m twlegalrag` — only works if the installed
       version ships a `__main__.py`; some releases are console-script-only
       and this will fail with "No module named twlegalrag.__main__".
    """
    exe = shutil.which("twlegalrag")
    if exe:
        return [exe]

    for candidate in _windows_user_scripts_candidates():
        return [str(candidate)]

    return [sys.executable, "-m", "twlegalrag"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retrieve Taiwan judgments as a citation bundle (JSON on stdout)."
    )
    parser.add_argument("question", help="legal question in plain language")
    parser.add_argument(
        "-n", type=int, default=5, help="number of judgments to retrieve (1-10)"
    )
    args = parser.parse_args()

    cmd = _cli_command() + ["pack", args.question, "-n", str(args.n)]
    try:
        # The CLI prints the bundle JSON to stdout and progress to stderr;
        # inherit both so the caller sees exactly what the CLI produced.
        proc = subprocess.run(cmd)
    except FileNotFoundError:
        print(
            "twlegalrag CLI not found. Install it with: pip install twlegalrag",
            file=sys.stderr,
        )
        return 127
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
