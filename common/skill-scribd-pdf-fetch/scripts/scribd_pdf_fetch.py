#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scribd_pdf_fetch.py — Wrapper around the external `scribd-downloader` tool.

This skill does NOT vendor scribd-downloader.py. The upstream project
(https://github.com/themrsami/scribd-downloader) declares MIT in its README
but ships no LICENSE file, so we treat it the same way this skills registry
treats yt-dlp: an external tool the user installs/clones themselves, invoked
as a subprocess, never copied into this (public, MIT-licensed) repo. See
SKILL.md "授權與合規注意事項" for the full rationale.

What this wrapper adds on top of the upstream CLI:
  1. Locates (or clones) a local checkout of the upstream repo.
  2. Applies a one-line local compatibility patch for Chrome 130+ (observed
     up to 152.x), where `excludeSwitches: ["enable-automation"]` makes
     Chrome exit immediately with "session not created: Chrome instance
     exited." The patch only touches the user's own local clone; it is not
     redistributed source.
  3. Runs the tool non-interactively (feeds the URL over stdin) and moves
     the resulting PDF to an --out-dir if requested.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

UPSTREAM_URL = "https://github.com/themrsami/scribd-downloader.git"
DEFAULT_CLONE_PARENT = Path.home() / "SynologyDrive" / "NAS" / "github.com"
DEFAULT_CLONE_DIR_NAME = "scribd-downloader"

# The exact lines upstream ships (as of the 2026-09-02 commit 0396d95) that
# crash newer Chrome by excluding the enable-automation switch. Matched by
# regex so reordering/whitespace changes upstream don't break the patch.
_BROKEN_OPTION_PATTERN = re.compile(
    r'[ \t]*options\.add_experimental_option\(\s*"excludeSwitches".*?\n'
    r'[ \t]*options\.add_experimental_option\(\s*"useAutomationExtension".*?\n',
)


def find_or_clone_repo(repo_dir: Path) -> Path:
    if (repo_dir / "scribd-downloader.py").exists():
        return repo_dir
    if repo_dir.exists() and any(repo_dir.iterdir()):
        raise SystemExit(
            f"{repo_dir} exists but does not look like a scribd-downloader "
            "checkout (missing scribd-downloader.py). Pass --repo-dir to "
            "point at the right clone."
        )
    print(f"[scribd-pdf-fetch] Cloning {UPSTREAM_URL} -> {repo_dir}")
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", UPSTREAM_URL, str(repo_dir)], check=True)
    return repo_dir


def ensure_requirements(repo_dir: Path) -> None:
    req = repo_dir / "requirements.txt"
    if not req.exists():
        return
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        check=True,
    )


def apply_chrome_compat_patch(repo_dir: Path) -> bool:
    """
    Remove the excludeSwitches/useAutomationExtension experimental options
    that crash Chrome 130+ on startup. Idempotent: no-op if already patched
    or the lines are not found (e.g. upstream already fixed it upstream).

    Returns True if the file was modified.
    """
    script_path = repo_dir / "scribd-downloader.py"
    original = script_path.read_text(encoding="utf-8")
    patched, count = _BROKEN_OPTION_PATTERN.subn("", original)
    if count == 0:
        return False
    script_path.write_text(patched, encoding="utf-8")
    print(
        f"[scribd-pdf-fetch] Applied Chrome 130+ compatibility patch to "
        f"{script_path} (removed {count} line pair(s))."
    )
    return True


def guess_output_filename(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    last_segment = parsed.path.rstrip("/").split("/")[-1] or "scribd_document"
    return f"{urllib.parse.unquote(last_segment)}.pdf"


def run_downloader(repo_dir: Path, url: str) -> Path:
    expected_name = guess_output_filename(url)
    expected_path = repo_dir / expected_name

    print(f"[scribd-pdf-fetch] Running downloader for: {url}")
    result = subprocess.run(
        [sys.executable, "scribd-downloader.py"],
        cwd=repo_dir,
        input=url + "\n",
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"scribd-downloader.py exited with code {result.returncode}"
        )
    if not expected_path.exists():
        raise SystemExit(
            f"Expected output PDF not found: {expected_path}\n"
            "The upstream tool may have changed its filename convention; "
            "check its stdout above."
        )
    return expected_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch a Scribd document as PDF via the external "
        "scribd-downloader tool.",
    )
    parser.add_argument("url", help="Scribd document URL "
                         "(https://www.scribd.com/document/<id>/... or "
                         "https://www.scribd.com/doc/<id>/...)")
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=DEFAULT_CLONE_PARENT / DEFAULT_CLONE_DIR_NAME,
        help="Local checkout of themrsami/scribd-downloader. Cloned here "
        "if missing. Default: %(default)s",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Move the resulting PDF here after download. Default: leave "
        "it inside --repo-dir.",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Run `pip install -r requirements.txt` in --repo-dir first.",
    )
    parser.add_argument(
        "--no-patch",
        action="store_true",
        help="Skip the Chrome 130+ compatibility patch (use if upstream "
        "has already fixed it, or to diagnose a different Chrome crash).",
    )
    args = parser.parse_args()

    repo_dir = find_or_clone_repo(args.repo_dir)

    if args.install_deps:
        ensure_requirements(repo_dir)

    if not args.no_patch:
        apply_chrome_compat_patch(repo_dir)

    pdf_path = run_downloader(repo_dir, args.url)

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        dest = args.out_dir / pdf_path.name
        shutil.move(str(pdf_path), str(dest))
        pdf_path = dest

    print(f"[scribd-pdf-fetch] Saved: {pdf_path}")


if __name__ == "__main__":
    main()
