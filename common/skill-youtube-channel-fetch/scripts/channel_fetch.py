#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
channel_fetch.py — Download audio for the newest videos on a YouTube channel,
publish each as a GitHub Release asset on the source repo, and register it in
the {stem: audio_url} manifest consumed by skill-mlx-api-client-whisper.

Requires the `yt-dlp` CLI on PATH (audio extraction / metadata listing) and
`requests` (already a dependency of skill-mlx-api-client-whisper).

Usage (CLI):
    python scripts/channel_fetch.py fetch https://www.youtube.com/@fubonsec --limit 5
    python scripts/channel_fetch.py fetch https://www.youtube.com/@fubonsec --limit 5 --sync

Usage (module):
    from scripts.channel_fetch import ChannelFetcher
    fetcher = ChannelFetcher()  # reads .env: WHISPER_SOURCE_REPO, YOUTUBE_FETCH_TOKEN
    fetcher.fetch_channel("https://www.youtube.com/@fubonsec", limit=5)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

import requests

API_ROOT = "https://api.github.com"
UPLOADS_ROOT = "https://uploads.github.com"

# Mirrors STEM_PATTERNS["youtube"] in skill-mlx-api-client-whisper/scripts/whisper_issue_client.py —
# video_id is always the fixed 11-char YouTube ID.
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# yt-dlp only enables the "deno" JS runtime by default; without one it can't run the
# signature-deciphering JS YouTube now requires, silently limiting extraction to the
# legacy 640x360 muxed format and, for some videos (seen on livestream VODs), failing
# downloads outright with a plain 403. Node is a much more commonly pre-installed
# runtime than deno, so use it explicitly rather than requiring deno everywhere.
YT_DLP_JS_RUNTIME_ARGS = ["--js-runtimes", "node"]


HANDLE_IN_URL_RE = re.compile(r"youtube\.com/@([A-Za-z0-9._-]+)", re.IGNORECASE)


def slugify_channel(name: str) -> str:
    """Turn a channel handle/title into the stem-safe {channel} segment."""
    slug = name.strip().lstrip("@")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return slug or "channel"


def channel_handle_from_url(channel_url: str) -> str | None:
    """Extract the ASCII @handle from a channel URL, e.g. '.../@fubonsec/videos' -> 'fubonsec'."""
    m = HANDLE_IN_URL_RE.search(channel_url)
    return m.group(1) if m else None


class ChannelFetcher:
    def __init__(
        self,
        source_repo: str | None = None,
        token: str | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.source_repo = source_repo or os.environ.get("WHISPER_SOURCE_REPO", "")
        # PAT needs Contents: Read and write on source_repo (release creation/upload).
        # REPO_FILE_SYNC_<SOURCE_OWNER>_<...> follows the same naming convention as
        # whisper_issue_client's REPO_FILE_SYNC_<TARGET_OWNER>_<...>, just scoped to the
        # source repo instead of the target repo — e.g. REPO_FILE_SYNC_WENCHIEHLEE_MONEY
        # for source_repo "wenchiehlee-money/...". YOUTUBE_FETCH_TOKEN/GH_TOKEN are generic
        # fallbacks for ad-hoc local use.
        self.token = (
            token
            or os.environ.get("REPO_FILE_SYNC_WENCHIEHLEE_MONEY")
            or os.environ.get("YOUTUBE_FETCH_TOKEN")
            or os.environ.get("GH_TOKEN")
        )
        if not self.source_repo:
            raise RuntimeError("WHISPER_SOURCE_REPO must be set (env or .env)")
        if not self.token:
            raise RuntimeError(
                "A REPO_FILE_SYNC_* var scoped to WHISPER_SOURCE_REPO "
                "(or YOUTUBE_FETCH_TOKEN / GH_TOKEN) is required"
            )
        self.repo_root = repo_root or Path.cwd()

    # -- yt-dlp -----------------------------------------------------------

    def list_channel_videos(self, channel_url: str, limit: int) -> list[dict]:
        """Return up to `limit` videos, newest first, as [{video_id, title, channel}]."""
        url = channel_url.rstrip("/")
        if not url.endswith(("/videos", "/streams")):
            url += "/videos"
        proc = subprocess.run(
            ["yt-dlp", *YT_DLP_JS_RUNTIME_ARGS, "--flat-playlist", "--playlist-end", str(limit), "-J", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp listing failed: {proc.stderr[:500]}")
        data = json.loads(proc.stdout)
        entries = data.get("entries", [])[:limit]
        # Prefer the ASCII @handle from the input URL — many channel display names
        # (data["channel"]/["uploader"]) are non-ASCII (e.g. Chinese) and slugify_channel()
        # would strip them to nothing, collapsing every such channel's stem to "channel_...".
        channel_name = (
            channel_handle_from_url(channel_url)
            or data.get("uploader_id", "").lstrip("@")
            or data.get("channel")
            or data.get("uploader")
            or data.get("id")
            or "channel"
        )
        videos = []
        for e in entries:
            vid = e.get("id", "")
            if not VIDEO_ID_RE.match(vid):
                continue
            videos.append({"video_id": vid, "title": e.get("title", vid), "channel": channel_name})
        return videos

    def download_audio(self, video_id: str, dest_dir: Path) -> Path:
        """Download best-audio for a video into dest_dir, returns the resulting file path."""
        out_template = str(dest_dir / f"{video_id}.%(ext)s")
        proc = subprocess.run(
            [
                "yt-dlp", *YT_DLP_JS_RUNTIME_ARGS,
                "-x", "--audio-format", "m4a", "--audio-quality", "0",
                "-o", out_template,
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp audio download failed for {video_id}: {proc.stderr[:500]}")
        matches = sorted(dest_dir.glob(f"{video_id}.*"))
        if not matches:
            raise RuntimeError(f"yt-dlp reported success but produced no file for {video_id}")
        return matches[0]

    # -- GitHub releases ----------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self.token}")
        headers.setdefault("Accept", "application/vnd.github+json")
        headers.setdefault("X-GitHub-Api-Version", "2022-11-28")
        resp = requests.request(method, url, headers=headers, timeout=120, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"GitHub API {method} {url} failed: {resp.status_code} {resp.text[:300]}")
        return resp

    def publish_audio_asset(self, stem: str, audio_path: Path) -> str:
        """
        Create (or reuse) a GitHub Release tagged `audio-{stem}` on source_repo and upload
        `audio_path` as its asset. Returns the asset's browser_download_url.
        """
        tag = f"audio-{stem}"
        release = None
        resp = requests.get(
            f"{API_ROOT}/repos/{self.source_repo}/releases/tags/{tag}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        if resp.status_code == 200:
            release = resp.json()
        elif resp.status_code == 404:
            release = self._request(
                "POST",
                f"{API_ROOT}/repos/{self.source_repo}/releases",
                json={"tag_name": tag, "name": tag, "body": f"Audio source for stem `{stem}`.", "draft": False, "prerelease": False},
            ).json()
        else:
            resp.raise_for_status()

        # Remove a stale asset with the same name (re-fetch scenario), then upload fresh.
        asset_name = audio_path.name
        for asset in release.get("assets", []):
            if asset.get("name") == asset_name:
                self._request("DELETE", f"{API_ROOT}/repos/{self.source_repo}/releases/assets/{asset['id']}")

        upload_url = release["upload_url"].split("{")[0]
        with open(audio_path, "rb") as f:
            data = f.read()
        upload_resp = self._request(
            "POST",
            f"{upload_url}?name={asset_name}",
            headers={"Content-Type": "audio/mp4"},
            data=data,
        )
        return upload_resp.json()["browser_download_url"]

    # -- manifest / orchestration --------------------------------------------

    def fetch_channel(
        self,
        channel_url: str,
        limit: int = 5,
        manifest_path: str | Path = "audio_manifest.json",
    ) -> dict[str, int]:
        manifest_path = Path(manifest_path)
        manifest: dict[str, str] = {}
        if manifest_path.exists():
            manifest = {k: v for k, v in json.loads(manifest_path.read_text(encoding="utf-8")).items() if not k.startswith("_")}

        videos = self.list_channel_videos(channel_url, limit)
        added = skipped = 0
        with tempfile.TemporaryDirectory(prefix="channel_fetch_") as tmp:
            tmp_dir = Path(tmp)
            for video in videos:
                channel_slug = slugify_channel(video["channel"])
                stem = f"{channel_slug}_{video['video_id']}"
                fin_path = self.repo_root / "data" / channel_slug / f"{stem}_FIN.srt"
                if stem in manifest or fin_path.exists():
                    print(f"[channel_fetch] skip {stem} (already sourced)")
                    skipped += 1
                    continue
                print(f"[channel_fetch] downloading audio for {stem}: {video['title']}")
                audio_path = self.download_audio(video["video_id"], tmp_dir)
                renamed = audio_path.with_name(f"{stem}{audio_path.suffix}")
                audio_path.rename(renamed)
                print(f"[channel_fetch] publishing release asset for {stem}")
                audio_url = self.publish_audio_asset(stem, renamed)
                manifest[stem] = audio_url
                added += 1

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[channel_fetch] done. added={added} skipped={skipped} -> {manifest_path}")
        return {"added": added, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    fetch_p = sub.add_parser("fetch", help="Fetch newest N videos' audio from a channel and update the manifest")
    fetch_p.add_argument("channel_url", help="e.g. https://www.youtube.com/@fubonsec")
    fetch_p.add_argument("--limit", type=int, default=5, help="Number of newest videos to consider (default 5)")
    fetch_p.add_argument("--manifest", default="audio_manifest.json", help="Path to the manifest JSON")
    fetch_p.add_argument("--sync", action="store_true", help="Run whisper_issue_client.sync_manifest afterwards")

    args = parser.parse_args()
    fetcher = ChannelFetcher()

    if args.cmd == "fetch":
        fetcher.fetch_channel(args.channel_url, limit=args.limit, manifest_path=args.manifest)
        if args.sync:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill-mlx-api-client-whisper" / "scripts"))
            from whisper_issue_client import WhisperIssueClient  # type: ignore

            WhisperIssueClient().sync_manifest(args.manifest)
