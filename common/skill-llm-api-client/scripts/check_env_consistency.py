#!/usr/bin/env python3
"""Check local LLM environment names against a GitHub Actions workflow.

This intentionally compares names and presence only. It never prints values.
The checker understands dotenv files containing unquoted shell-special characters.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_LOCAL = {"CODEX_API_KEY", "GEMINI_API_KEY"}
GEMINI_ROTATION = {f"GEMINI_API_KEY_{i}" for i in range(1, 20)}
OPTIONAL_LOCAL = {
    "AMPLITUDE_API_KEY",
    "LLM_APP_NAME",
    "MLX_API_URL",
    "MLX_SERVER_API_KEY",
    "MLX_MODEL",
    "GEMINI_SKIP_KEYS",
}
SECRET_REF_RE = re.compile(r"secrets\.([A-Z][A-Z0-9_]*)")
ENV_NAME_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def dotenv_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = ENV_NAME_RE.match(raw)
        if match and not raw.lstrip().startswith("#"):
            names.add(match.group(1))
    return names


def workflow_secret_names(path: Path) -> set[str]:
    return set(SECRET_REF_RE.findall(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--workflow",
        type=Path,
        default=Path(".github/workflows/Actions.yaml"),
    )
    args = parser.parse_args()

    missing_files = [p for p in (args.env_file, args.workflow) if not p.is_file()]
    if missing_files:
        for path in missing_files:
            print(f"ERROR missing file: {path}")
        return 2

    local = dotenv_names(args.env_file)
    managed = REQUIRED_LOCAL | OPTIONAL_LOCAL | GEMINI_ROTATION
    workflow = workflow_secret_names(args.workflow) & managed
    missing_local = sorted(REQUIRED_LOCAL - local)
    workflow_not_local = sorted(workflow - local)
    local_not_workflow = sorted(
        (local & managed) - workflow
    )

    print(f"Local env file: {args.env_file}")
    print(f"Workflow: {args.workflow}")
    print(f"Local LLM variables found: {len(local & managed)}")
    print(f"Workflow secret references found: {len(workflow)}")

    if missing_local:
        print("FAIL missing required local variables: " + ", ".join(missing_local))
    if workflow_not_local:
        print("FAIL workflow secrets absent from local .env: " + ", ".join(workflow_not_local))
    if local_not_workflow:
        print(
            "INFO local variables not injected by this workflow: "
            + ", ".join(local_not_workflow)
        )

    if missing_local or workflow_not_local:
        return 1

    print("PASS variable names are consistent for all workflow-injected secrets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
