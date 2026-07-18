#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild and plot biztrends.TW Taiwan cycle index from newest revenue data."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pandas as pd
from PIL import Image


def find_project_root() -> Path:
    env_root = os.environ.get("BIZTRENDS_TW_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    for candidate in candidates:
        if (candidate / "scripts" / "build_tw_cycle_index.py").is_file() and (candidate / "scripts" / "plot_tw_cycle_index.py").is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find biztrends.TW root. Run from the repo root or set BIZTRENDS_TW_ROOT.")


def raw_revenue_path(root: Path) -> Path:
    local = root / "data" / "Python-Actions.GoodInfo.Analyzer" / "raw_revenue.csv"
    sibling = root.parent / "Python-Actions.GoodInfo.Analyzer" / "data" / "stage1_raw" / "raw_revenue.csv"
    for path in (local, sibling):
        if path.is_file():
            return path
    raise SystemExit(f"Cannot find raw_revenue.csv at {local} or {sibling}")


def latest_month_and_count(csv_path: Path, month_col: str) -> tuple[str, int]:
    df = pd.read_csv(csv_path)
    if month_col not in df.columns:
        raise SystemExit(f"{csv_path} missing required column: {month_col}")
    months = df[month_col].astype(str)
    latest = months.max()
    return latest, int((months == latest).sum())


def run(cmd: list[str], root: Path, env: dict[str, str] | None = None) -> None:
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, env=env, check=True)


def main() -> int:
    root = find_project_root()
    print(f"Project root: {root}")

    raw_path = raw_revenue_path(root)
    raw_latest, raw_count = latest_month_and_count(raw_path, "月別")
    print(f"Raw revenue: {raw_path}")
    print(f"Raw latest month: {raw_latest} ({raw_count} rows)")

    run(["python3", "scripts/build_tw_cycle_index.py"], root)

    derived_files = [
        root / "data" / "tw_cycle_intensity_index.csv",
        root / "data" / "tw_cycle_intensity_by_symbol.csv",
    ]
    for path in derived_files:
        latest, count = latest_month_and_count(path, "month")
        print(f"{path.relative_to(root)} latest month: {latest} ({count} rows)")
        if latest < raw_latest:
            raise SystemExit(
                f"Derived data is stale: {path.relative_to(root)} latest={latest}, raw latest={raw_latest}"
            )

    env = os.environ.copy()
    env["CI"] = "1"
    run(["python3", "scripts/plot_tw_cycle_index.py"], root, env=env)

    png_path = root / "output" / "tw_cycle_index.png"
    if not png_path.is_file():
        raise SystemExit(f"PNG not generated: {png_path}")
    with Image.open(png_path) as im:
        print(f"PNG: {png_path} {im.format} {im.size} {im.mode}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
