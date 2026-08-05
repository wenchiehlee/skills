#!/usr/bin/env python3
"""Audit InvestorConference release audio checksums and durations."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".wav"}


def repo_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in cur.parents:
        if (parent / "audio_manifest.json").exists() or (parent / ".git").exists():
            return parent
    return cur.parents[3]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return float(r.stdout.strip())
    except Exception as exc:
        print(f"[audit] ffprobe failed for {path.name}: {exc}", file=sys.stderr)
    return None


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "InvestorConference-audio-audit/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response, dest.open("wb") as f:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def audio_file_path(stem: str, url: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        suffix = ".m4a"
    stock_id = stem.split("_", 1)[0]
    return f"data/{stock_id}/{stem}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or refresh audio_metadata.json from release audio assets.")
    parser.add_argument("--stems", nargs="*", help="Limit audit to specific manifest stems.")
    parser.add_argument("--cache-dir", default=None, help="Directory for downloaded audio cache.")
    parser.add_argument("--update-durations", action="store_true", help="Also refresh audio_durations.json from audited durations.")
    parser.add_argument("--fail-on-duplicate", action="store_true", help="Exit non-zero when duplicate checksums are found.")
    args = parser.parse_args()

    repo = repo_root()
    manifest = load_json(repo / "audio_manifest.json")
    metadata = load_json(repo / "audio_metadata.json")
    durations = load_json(repo / "audio_durations.json")
    selected = set(args.stems or [])
    cache_base = Path(args.cache_dir) if args.cache_dir else Path(tempfile.gettempdir()) / "investorconference-audio-audit"
    cache_base.mkdir(parents=True, exist_ok=True)

    checked_at = _dt.date.today().isoformat()
    stems = sorted(stem for stem in manifest if not selected or stem in selected)
    if selected:
        missing = sorted(selected - set(manifest))
        for stem in missing:
            print(f"[audit] Missing stem in audio_manifest.json: {stem}", file=sys.stderr)

    for stem in stems:
        url = manifest[stem]
        if not isinstance(url, str) or not url.startswith("http"):
            print(f"[audit] Skip non-http manifest value: {stem}", file=sys.stderr)
            continue
        suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".m4a"
        local = cache_base / f"{stem}{suffix}"
        if not local.exists() or local.stat().st_size == 0:
            print(f"[audit] Downloading {stem}...")
            download(url, local)
        duration = probe_duration(local)
        item = {
            "file": audio_file_path(stem, url),
            "sha256": sha256_file(local),
            "size_bytes": local.stat().st_size,
            "duration_sec": round(duration, 3) if duration is not None else None,
            "release_url": url,
            "checked_at": checked_at,
            "source": "github_release_audit",
            "status": "ok",
        }
        metadata[stem] = item
        if args.update_durations and duration is not None:
            durations[item["file"]] = int(duration)
        print(f"[audit] {stem}: sha256={item['sha256'][:12]}..., duration={item['duration_sec']}s")

    by_sha: dict[str, list[str]] = {}
    for stem, item in metadata.items():
        if isinstance(item, dict) and item.get("sha256"):
            by_sha.setdefault(str(item["sha256"]).lower(), []).append(stem)

    duplicates = {sha: sorted(v) for sha, v in by_sha.items() if len(v) > 1}
    for sha, dup_stems in sorted(duplicates.items()):
        canonical = dup_stems[0]
        print(f"[audit] DUPLICATE sha256={sha}: {', '.join(dup_stems)}")
        for stem in dup_stems[1:]:
            if stem in metadata and isinstance(metadata[stem], dict):
                metadata[stem]["status"] = "duplicate"
                metadata[stem]["duplicate_of"] = canonical

    write_json(repo / "audio_metadata.json", metadata)
    if args.update_durations:
        write_json(repo / "audio_durations.json", durations)

    if duplicates and args.fail_on_duplicate:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
