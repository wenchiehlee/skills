#!/usr/bin/env python3
"""Run My-TW-Coverage theme rendering through the render-markdown skill."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def find_coverage_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (
            (candidate / "data" / "themes").is_dir()
            and (candidate / "data" / "enrichment_all").is_dir()
            and (candidate / "scripts" / "build_themes.py").is_file()
        ):
            return candidate
    raise SystemExit(
        "Cannot find My-TW-Coverage root. Run from the repository root or a subdirectory."
    )


def main() -> None:
    root = find_coverage_root()
    script = root / "scripts" / "build_themes.py"
    sys.path.insert(0, str(root))
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
