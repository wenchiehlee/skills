#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
channel_fetch.py — Download audio for the newest videos on a YouTube channel,
publish each as a GitHub Release asset on the source repo, and register it in
the {stem: audio_url} manifest consumed by skill-mlx-api-client-whisper.

Before touching audio/whisper at all, each video is checked for an official
YouTube transcript via `youtube-transcript-api`, in a preferred language:
  - YouTube's own auto-generated captions -> written straight to FIN.srt
    (no better than whisper's own output, so not worth refining).
  - Creator-uploaded (manual) captions -> written to GT.srt only. A stem
    with a GT.srt and no FIN.srt is a complete, valid end state on its own
    (downstream steps treat GT.srt as the source SRT when FIN.srt is
    absent) — FIN.srt is written only once something has actually produced
    a pipeline-scored transcript. `channel_fetch.py refine` can later spend
    audio+Mac-mini time on task_type="refine_fin_srt" to have the pipeline
    generate a real FIN.srt from that GT, if you want a CER-scored version.
Either way the video skips the audio/manifest/whisper path entirely at fetch
time — whisper's ~1-1.5h/video multi-experiment transcription is reserved for
videos YouTube has no transcript for at all.

Requires the `yt-dlp` CLI on PATH (audio extraction / metadata listing) and
`requests`/`youtube-transcript-api` (already dependencies of
skill-mlx-api-client-whisper / this skill).

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
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

import requests
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

API_ROOT = "https://api.github.com"
UPLOADS_ROOT = "https://uploads.github.com"

# Preference order for fetch_official_transcript(): Traditional-Chinese variants first
# (this repo's channels are Taiwan financial YouTube), then Simplified, then English.
# youtube-transcript-api raises NoTranscriptFound (a CouldNotRetrieveTranscript subclass)
# rather than falling back to an unrelated language, so a video whose only captions are
# e.g. Japanese correctly falls through to the whisper pipeline instead of mistranscribing.
DEFAULT_TRANSCRIPT_LANGUAGES = ["zh-TW", "zh-Hant", "zh", "zh-Hans", "zh-CN", "en"]

# Mirrors STEM_PATTERNS["youtube"] in skill-mlx-api-client-whisper/scripts/whisper_issue_client.py —
# video_id is always the fixed 11-char YouTube ID.
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# yt-dlp only enables the "deno" JS runtime by default; without one it can't run the
# signature-deciphering JS YouTube now requires, silently limiting extraction to the
# legacy 640x360 muxed format and, for some videos (seen on livestream VODs), failing
# downloads outright with a plain 403. Node is a much more commonly pre-installed
# runtime than deno, so use it explicitly rather than requiring deno everywhere.
# --remote-components ejs:github fetches yt-dlp's n/sig challenge-solver script from
# GitHub rather than the one bundled in the installed release, which cuts down (but
# doesn't fully eliminate — YouTube's anti-bot behavior is itself flaky) plain 403s.
YT_DLP_JS_RUNTIME_ARGS = ["--js-runtimes", "node", "--remote-components", "ejs:github"]


def yt_dlp_cookie_args() -> list[str]:
    cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE")
    if cookies_file:
        return ["--cookies", cookies_file]
    return []


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


def _normalize_date(date: str | None) -> str | None:
    """'YYYY-MM-DD' or 'YYYYMMDD' -> 'YYYYMMDD'. None passes through."""
    if not date:
        return None
    digits = date.replace("-", "")
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"date must be YYYY-MM-DD or YYYYMMDD, got: {date!r}")
    return digits


def _pseudo_srt_timestamp(total_seconds: float) -> str:
    """(MM:SS.mmm) — matches CUE_RE in skill-youtube-channel-srt-keyframe-extract's
    parse_srt(); MM is total minutes (unbounded), not clock-wrapped hours:minutes."""
    minutes = int(total_seconds // 60)
    seconds = total_seconds - minutes * 60
    return f"{minutes:02d}:{seconds:06.3f}"


def transcript_to_pseudo_srt(snippets: list[dict], stem: str, language_code: str, source_suffix: str) -> str:
    """Render youtube-transcript-api snippets ({text, start, duration}) into this repo's
    FIN.srt/GT.srt format — see data/*/*_FIN.srt for the format this mirrors."""
    lines = [
        "[METADATA]",
        f"Source: {stem}{source_suffix}",
        f"Language: {language_code}",
        "---",
    ]
    for snip in snippets:
        text = " ".join(snip["text"].split())
        if not text:
            continue
        lines.append(f"({_pseudo_srt_timestamp(snip['start'])}) {text}")
    return "\n".join(lines) + "\n"


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

    def _list_tab(self, channel_url: str, tab: str, limit: int) -> tuple[list[dict], str]:
        """Flat-playlist a single channel tab (/videos or /streams). Returns
        ([{video_id, title}], channel_name) — channel_name is best-effort per this
        one tab's response and may be empty for a tab with zero entries."""
        url = channel_url.rstrip("/") + f"/{tab}"
        proc = subprocess.run(
            ["yt-dlp", *YT_DLP_JS_RUNTIME_ARGS, *yt_dlp_cookie_args(), "--flat-playlist", "--playlist-end", str(limit), "-J", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            # Plenty of channels simply don't have a /streams tab (e.g. ones that never
            # livestream) — that's "zero entries", not a fetch failure, and shouldn't
            # sink the /videos tab's results when both are queried together.
            if "does not have a" in proc.stderr and "tab" in proc.stderr:
                return [], ""
            raise RuntimeError(f"yt-dlp listing failed ({tab}): {proc.stderr[:500]}")
        data = json.loads(proc.stdout)
        channel_name = (
            channel_handle_from_url(channel_url)
            or data.get("uploader_id", "").lstrip("@")
            or data.get("channel")
            or data.get("uploader")
            or data.get("id")
            or ""
        )
        entries = []
        for e in data.get("entries", [])[:limit]:
            vid = e.get("id", "")
            if VIDEO_ID_RE.match(vid):
                entries.append({"video_id": vid, "title": e.get("title", vid)})
        return entries, channel_name

    def _video_upload_timestamp(self, video_id: str) -> int:
        """Epoch upload timestamp for ordering/filtering candidates pulled from multiple
        tabs (flat-playlist entries don't carry a usable date). 0 if the lookup fails —
        such a video sorts last / is excluded from date-range filtering rather than
        crashing the whole channel fetch."""
        proc = subprocess.run(
            ["yt-dlp", *YT_DLP_JS_RUNTIME_ARGS, *yt_dlp_cookie_args(), "--skip-download", "--print", "%(timestamp)s",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        try:
            return int(float(line))
        except ValueError:
            return 0

    # Per-tab safety cap when scanning by date range instead of "newest N" — how far
    # back into a tab's listing to look before giving up on finding `date_after`.
    DATE_RANGE_CANDIDATE_POOL = 400

    def _resolve_in_range(self, entries: list[dict], date_after: str | None, date_before: str | None) -> list[dict]:
        """entries: newest-first from one tab (as returned by _list_tab). Resolves each
        one's real upload date and keeps those within [date_after, date_before]
        (YYYYMMDD strings, either bound optional). A single tab's listing is
        monotonically newest-first, so once a resolved date falls before date_after we
        can stop scanning that tab entirely — bounds the cost for a narrow/recent range
        instead of always walking the full DATE_RANGE_CANDIDATE_POOL."""
        matched = []
        for e in entries:
            ts = self._video_upload_timestamp(e["video_id"])
            if ts == 0:
                continue  # lookup failed; skip rather than mis-include/exclude
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")
            if date_before and date_str > date_before:
                continue
            if date_after and date_str < date_after:
                break
            matched.append({**e, "date": date_str, "_ts": ts})
        return matched

    def list_channel_videos(
        self,
        channel_url: str,
        limit: int | None = 5,
        date_after: str | None = None,
        date_before: str | None = None,
    ) -> list[dict]:
        """Return videos newest-first as [{video_id, title, channel}].

        Two modes:
          - "newest N" (default): up to `limit` videos.
          - date range: pass date_after and/or date_before (YYYY-MM-DD or YYYYMMDD) to
            get every video in that range instead — `limit`, if also given, caps the
            result afterward.

        Combines the channel's /videos and /streams tabs (unless the URL already names
        one explicitly) — channels that mainly post archived livestreams (e.g. a daily
        morning-show format) put their regular public content under /streams, not
        /videos, so querying only /videos silently misses it. --flat-playlist entries
        don't carry a usable date, so ordering (and, in date-range mode, filtering)
        relies on a real per-video upload timestamp lookup.
        """
        date_after = _normalize_date(date_after)
        date_before = _normalize_date(date_before)
        ranged = bool(date_after or date_before)

        url = channel_url.rstrip("/")
        if url.endswith("/videos"):
            tabs = ["videos"]
            url = url[: -len("/videos")]
        elif url.endswith("/streams"):
            tabs = ["streams"]
            url = url[: -len("/streams")]
        else:
            tabs = ["videos", "streams"]

        pool = self.DATE_RANGE_CANDIDATE_POOL if ranged else (limit or 5)

        by_id: dict[str, dict] = {}
        channel_name = ""
        for tab in tabs:
            entries, name = self._list_tab(url, tab, pool)
            channel_name = channel_name or name
            if ranged:
                entries = self._resolve_in_range(entries, date_after, date_before)
            for e in entries:
                by_id.setdefault(e["video_id"], e)  # first tab wins on title if seen twice

        candidates = list(by_id.values())
        if ranged:
            candidates.sort(key=lambda c: c.get("_ts", 0), reverse=True)
        elif len(tabs) > 1 and candidates:
            # Each individual tab is already newest-first, but interleaving two such
            # lists by dict-insertion order isn't — resolve real order via per-video
            # timestamp lookups before truncating to `limit`.
            for c in candidates:
                c["_ts"] = self._video_upload_timestamp(c["video_id"])
            candidates.sort(key=lambda c: c["_ts"], reverse=True)

        if limit is not None:
            candidates = candidates[:limit]

        channel_name = channel_name or "channel"
        return [{"video_id": c["video_id"], "title": c["title"], "channel": channel_name} for c in candidates]

    def fetch_official_transcript(
        self, video_id: str, languages: list[str] | None = None
    ):
        """Return a FetchedTranscript for the first matching language in `languages`,
        or None if YouTube has no transcript in any of them (captions disabled, or only
        available in an unrelated language). Network/API errors are also treated as "no
        transcript" — the caller falls back to the audio+whisper path rather than
        failing the whole channel fetch over a single flaky lookup."""
        languages = languages or DEFAULT_TRANSCRIPT_LANGUAGES
        try:
            return YouTubeTranscriptApi().fetch(video_id, languages=languages)
        except CouldNotRetrieveTranscript:
            return None
        except Exception as e:
            print(f"[channel_fetch]   transcript lookup failed for {video_id} ({type(e).__name__}: {e}), falling back to whisper")
            return None

    def download_audio(self, video_id: str, dest_dir: Path) -> Path:
        """Download best-audio for a video into dest_dir, returns the resulting file path."""
        out_template = str(dest_dir / f"{video_id}.%(ext)s")
        proc = subprocess.run(
            [
                "yt-dlp", *YT_DLP_JS_RUNTIME_ARGS, *yt_dlp_cookie_args(),
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
        limit: int | None = 5,
        manifest_path: str | Path = "audio_manifest.json",
        try_official_transcript: bool = True,
        transcript_languages: list[str] | None = None,
        date_after: str | None = None,
        date_before: str | None = None,
    ) -> dict[str, int]:
        manifest_path = Path(manifest_path)
        manifest: dict[str, str] = {}
        if manifest_path.exists():
            manifest = {k: v for k, v in json.loads(manifest_path.read_text(encoding="utf-8")).items() if not k.startswith("_")}

        videos = self.list_channel_videos(channel_url, limit, date_after=date_after, date_before=date_before)
        transcribed_auto = transcribed_manual = added = skipped = failed = 0
        with tempfile.TemporaryDirectory(prefix="channel_fetch_") as tmp:
            tmp_dir = Path(tmp)
            for video in videos:
                channel_slug = slugify_channel(video["channel"])
                stem = f"{channel_slug}_{video['video_id']}"
                data_dir = self.repo_root / "data" / channel_slug
                fin_path = data_dir / f"{stem}_FIN.srt"
                gt_path = data_dir / f"{stem}_GT.srt"
                if stem in manifest or fin_path.exists() or gt_path.exists():
                    print(f"[channel_fetch] skip {stem} (already sourced)")
                    skipped += 1
                    continue

                try:
                    if try_official_transcript:
                        transcript = self.fetch_official_transcript(video["video_id"], transcript_languages)
                        if transcript is not None:
                            raw = transcript.to_raw_data()
                            data_dir.mkdir(parents=True, exist_ok=True)
                            if transcript.is_generated:
                                # YouTube's own ASR — no better than what whisper would produce,
                                # so just use it as FIN.srt directly; not worth a refine_fin_srt pass.
                                fin_path.write_text(
                                    transcript_to_pseudo_srt(raw, stem, transcript.language_code, "_youtube-transcript-auto"),
                                    encoding="utf-8",
                                )
                                print(f"[channel_fetch] {stem}: auto-generated YouTube transcript ({transcript.language_code}), wrote {fin_path} — skipping whisper")
                                transcribed_auto += 1
                            else:
                                # Creator-uploaded captions — close enough to ground truth to keep
                                # as GT.srt. No FIN.srt is written here: a GT.srt with no FIN.srt
                                # is itself a complete state (downstream steps use GT.srt as the
                                # source SRT when FIN.srt is absent) — FIN.srt is reserved for an
                                # actual pipeline-scored transcript. `channel_fetch.py refine` can
                                # later spend audio+Mac-mini time to have the pipeline generate one
                                # from this GT, if a CER-scored version is wanted.
                                gt_path.write_text(
                                    transcript_to_pseudo_srt(raw, stem, transcript.language_code, "_youtube-transcript-manual"),
                                    encoding="utf-8",
                                )
                                print(f"[channel_fetch] {stem}: manual YouTube transcript ({transcript.language_code}), wrote {gt_path} — run `refine` to have whisper pipeline generate a scored FIN.srt from this GT")
                                transcribed_manual += 1
                            continue

                    print(f"[channel_fetch] downloading audio for {stem}: {video['title']}")
                    audio_path = self.download_audio(video["video_id"], tmp_dir)
                    renamed = audio_path.with_name(f"{stem}{audio_path.suffix}")
                    audio_path.rename(renamed)
                    print(f"[channel_fetch] publishing release asset for {stem}")
                    audio_url = self.publish_audio_asset(stem, renamed)
                    manifest[stem] = audio_url
                    added += 1
                except RuntimeError as e:
                    # One unfetchable video (members-only, deleted, geo-blocked, etc.) shouldn't
                    # sink the whole batch — log it and keep going so the manifest write below
                    # still captures whatever earlier videos in this run did succeed.
                    print(f"[channel_fetch] {stem}: failed, skipping ({e})")
                    failed += 1

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"[channel_fetch] done. transcribed_auto={transcribed_auto} transcribed_manual={transcribed_manual} "
            f"added={added} skipped={skipped} -> {manifest_path}"
        )
        return {
            "transcribed_auto": transcribed_auto,
            "transcribed_manual": transcribed_manual,
            "added": added,
            "skipped": skipped,
        }

    # -- refinement of manual-transcript stems -------------------------------

    def list_unrefined_gt_stems(self) -> list[tuple[str, Path]]:
        """Find every stem under data/ with a GT.srt but no FIN.srt yet — i.e. sourced
        straight from a manual YouTube transcript and never run through the whisper
        pipeline's refine_fin_srt. Returns [(stem, gt_path), ...]."""
        data_root = self.repo_root / "data"
        if not data_root.is_dir():
            return []
        found = []
        for gt_path in sorted(data_root.glob("*/*_GT.srt")):
            stem = gt_path.name[: -len("_GT.srt")]
            fin_path = gt_path.with_name(f"{stem}_FIN.srt")
            if not fin_path.exists():
                found.append((stem, gt_path))
        return found

    def request_refinement(
        self,
        manifest_path: str | Path = "audio_manifest.json",
        stems: list[str] | None = None,
    ) -> dict[str, int]:
        """For stems that have a GT.srt but no FIN.srt yet (i.e. sourced from a manual
        YouTube transcript and never run through the whisper pipeline), download+publish
        audio and open a refine_fin_srt request so the Mac-mini pipeline generates a real,
        CER-scored FIN.srt from the existing GT.srt — without paying for a full
        multi-experiment transcription pass."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill-mlx-api-client-whisper" / "scripts"))
        from whisper_issue_client import WhisperIssueClient  # type: ignore

        manifest_path = Path(manifest_path)
        manifest: dict[str, str] = {}
        if manifest_path.exists():
            manifest = {k: v for k, v in json.loads(manifest_path.read_text(encoding="utf-8")).items() if not k.startswith("_")}

        candidates = self.list_unrefined_gt_stems()
        if stems is not None:
            wanted = set(stems)
            candidates = [(s, p) for s, p in candidates if s in wanted]

        whisper_client = WhisperIssueClient()
        requested = skipped = 0
        with tempfile.TemporaryDirectory(prefix="channel_fetch_refine_") as tmp:
            tmp_dir = Path(tmp)
            for stem, gt_path in candidates:
                video_id = stem.rsplit("_", 1)[-1]
                audio_url = manifest.get(stem)
                if not audio_url:
                    print(f"[channel_fetch] downloading audio for refine: {stem}")
                    audio_path = self.download_audio(video_id, tmp_dir)
                    renamed = audio_path.with_name(f"{stem}{audio_path.suffix}")
                    audio_path.rename(renamed)
                    audio_url = self.publish_audio_asset(stem, renamed)
                    manifest[stem] = audio_url

                issue = whisper_client.open_fin_request(stem, audio_url, task_type="refine_fin_srt")
                if issue is None:
                    print(f"[channel_fetch] refine already requested for {stem} (issue open)")
                    skipped += 1
                else:
                    print(f"[channel_fetch] opened refine_fin_srt request for {stem}: {issue.get('html_url', '')}")
                    requested += 1

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[channel_fetch] refine done. requested={requested} skipped={skipped}")
        return {"requested": requested, "skipped": skipped}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    fetch_p = sub.add_parser("fetch", help="Fetch newest N videos (or a date range) from a channel and update the manifest")
    fetch_p.add_argument("channel_url", help="e.g. https://www.youtube.com/@fubonsec")
    fetch_p.add_argument(
        "--limit", type=int, default=None,
        help="Number of newest videos to consider (default 5, unless --date-after/--date-before "
             "is given, in which case the default is every video in that range)",
    )
    fetch_p.add_argument("--date-after", default=None, help="Only videos uploaded on/after this date (YYYY-MM-DD)")
    fetch_p.add_argument("--date-before", default=None, help="Only videos uploaded on/before this date (YYYY-MM-DD)")
    fetch_p.add_argument("--manifest", default="audio_manifest.json", help="Path to the manifest JSON")
    fetch_p.add_argument("--sync", action="store_true", help="Run whisper_issue_client.sync_manifest afterwards")
    fetch_p.add_argument(
        "--no-transcript", action="store_true",
        help="Skip the official-YouTube-transcript check; always go through audio+whisper",
    )
    fetch_p.add_argument(
        "--transcript-languages", default=None,
        help=f"Comma-separated language preference order (default: {','.join(DEFAULT_TRANSCRIPT_LANGUAGES)})",
    )

    refine_p = sub.add_parser(
        "refine",
        help="For stems with a GT.srt but no FIN.srt yet (manual-transcript-sourced), "
             "download audio and request the whisper pipeline generate a real FIN.srt from that GT.srt",
    )
    refine_p.add_argument("--manifest", default="audio_manifest.json", help="Path to the manifest JSON")
    refine_p.add_argument("--stem", action="append", dest="stems", default=None,
                           help="Limit to specific stem(s) (repeatable); default: all unrefined GT-only stems")

    args = parser.parse_args()
    fetcher = ChannelFetcher()

    if args.cmd == "fetch":
        limit = args.limit
        if limit is None and not (args.date_after or args.date_before):
            limit = 5  # default "newest N" behavior when no date range is given
        fetcher.fetch_channel(
            args.channel_url,
            limit=limit,
            manifest_path=args.manifest,
            try_official_transcript=not args.no_transcript,
            transcript_languages=args.transcript_languages.split(",") if args.transcript_languages else None,
            date_after=args.date_after,
            date_before=args.date_before,
        )
        if args.sync:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill-mlx-api-client-whisper" / "scripts"))
            from whisper_issue_client import WhisperIssueClient  # type: ignore

            WhisperIssueClient().sync_manifest(args.manifest)
    elif args.cmd == "refine":
        fetcher.request_refinement(manifest_path=args.manifest, stems=args.stems)
