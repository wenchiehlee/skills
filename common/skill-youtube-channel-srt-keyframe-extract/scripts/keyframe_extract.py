#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
keyframe_extract.py — Analyze a FIN.srt transcript for moments that likely show a
chart/diagram/on-screen data (LLM semantic pass), then grab a PNG video frame at
each timestamp.

Requires `yt-dlp` and `ffmpeg` on PATH, plus the shared `llm` package (sibling repo
`../llm`, editable-installed) for the LLM call — see that repo's README for its
provider fallback chain (codex -> gemini -> mlx) and env vars.

Usage (CLI):
    python scripts/keyframe_extract.py extract some-channel_dQw4w9WgXcQ \
        --srt data/some-channel/some-channel_dQw4w9WgXcQ_FIN.srt \
        --video-url https://www.youtube.com/watch?v=dQw4w9WgXcQ

Usage (module):
    from scripts.keyframe_extract import KeyframeExtractor
    KeyframeExtractor().extract(stem, srt_path, video_url)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")
except ImportError:
    pass

from llm import LLMClient

# yt-dlp only enables the "deno" JS runtime by default; without one it can't run the
# signature-deciphering JS YouTube now requires, silently limiting extraction to the
# legacy 640x360 muxed format (so captured frames come out far below 1080p) and, for
# some videos, failing downloads outright with a plain 403. Node is a much more
# commonly pre-installed runtime than deno, so use it explicitly.
YT_DLP_JS_RUNTIME_ARGS = ["--js-runtimes", "node"]

# Despite the ".srt" filename, skill-mlx-api-server-whisper's FIN.srt/GT.srt is NOT
# standard SubRip: an optional "[METADATA]\n...\n---\n" header, then one cue per line
# as "(MM:SS.mmm) text" — no end timestamp, no blank-line separators, no numeric index.
# MM is plain minutes-since-start and can exceed 59 for videos over an hour (it never
# rolls into an HH field), so it must not be parsed as SS.
CUE_RE = re.compile(r"^\((?P<mm>\d+):(?P<ss>\d{2})\.(?P<ms>\d{3})\)\s*(?P<text>.*)$")

SYSTEM_PROMPT = (
    "你正在分析一支財經 YouTube 影片的逐字稿（SRT，含時間碼）。這類影片是講者口述搭配"
    "螢幕上的圖表／簡報／數字切換，話題常常隨著新的一句話開始就跟著換一張畫面，"
    "不一定會明講「看這張圖」。找出逐字稿中「講者開始一個新話題／提出新的數字／"
    "切換到新公司或新圖表」的時刻——只要合理猜測畫面此時很可能切換到新的視覺內容"
    "（圖表／簡報／數字／新聞畫面／個股走勢圖）即可選入，不需要句子裡明確描述畫面。"
    "不要挑選明顯只是延續同一段話、同一個話題的句子（例如同一個數字的補充說明、"
    "語氣詞、承接上一句的細節）。每個時刻回傳字幕的起始時間碼（HH:MM:SS）"
    "與一句話說明預期畫面內容或話題轉折點。"
)

JSON_INSTRUCTION = (
    "請只回傳合法 JSON（不要加 markdown code fence），格式為：\n"
    '{"moments": [{"timestamp": "HH:MM:SS", "reason": "一句話說明預期畫面內容"}, ...]}\n'
    "若沒有值得截圖的時刻，回傳 {\"moments\": []}。"
)


@dataclass
class SrtCue:
    start_seconds: float
    start: str  # HH:MM:SS (normalized; mm in the source can exceed 59)
    text: str


def _format_hhmmss(total_seconds: float) -> str:
    total = int(total_seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_srt(path: Path) -> list[SrtCue]:
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()
    if lines and lines[0].strip() == "[METADATA]":
        try:
            lines = lines[lines.index("---") + 1:]
        except ValueError:
            pass  # malformed header; fall through and let CUE_RE just find nothing
    cues = []
    for line in lines:
        m = CUE_RE.match(line.strip())
        if not m:
            continue
        text = m.group("text").strip()
        if not text:
            continue
        seconds = int(m.group("mm")) * 60 + int(m.group("ss")) + int(m.group("ms")) / 1000
        cues.append(SrtCue(start_seconds=seconds, start=_format_hhmmss(seconds), text=text))
    return cues


def render_transcript(cues: list[SrtCue]) -> str:
    return "\n".join(f"[{c.start}] {c.text}" for c in cues)


class KeyframeExtractor:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient(app_name="skill-youtube-channel-srt-keyframe-extract")

    def find_key_moments(self, cues: list[SrtCue]) -> list[dict]:
        if not cues:
            return []
        transcript = render_transcript(cues)
        prompt = f"{SYSTEM_PROMPT}\n\n{JSON_INSTRUCTION}\n\n逐字稿：\n{transcript}"
        data = self.client.generate_json(prompt)
        if isinstance(data, dict):
            return data.get("moments", [])
        return []

    def download_video(self, video_url: str, dest_dir: Path) -> Path:
        out_template = str(dest_dir / "video.%(ext)s")
        proc = subprocess.run(
            ["yt-dlp", *YT_DLP_JS_RUNTIME_ARGS,
             "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
             "--merge-output-format", "mp4", "-o", out_template, video_url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"yt-dlp video download failed: {proc.stderr[:500]}")
        matches = sorted(dest_dir.glob("video.*"))
        if not matches:
            raise RuntimeError("yt-dlp reported success but produced no video file")
        return matches[0]

    def grab_frame(self, video_path: Path, timestamp: str, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", timestamp, "-i", str(video_path),
             "-frames:v", "1", "-q:v", "2", str(out_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg frame capture failed at {timestamp}: {proc.stderr[-500:]}")

    def extract(self, stem: str, srt_path: str | Path, video_url: str, out_dir: str | Path | None = None) -> list[Path]:
        srt_path = Path(srt_path)
        cues = parse_srt(srt_path)
        moments = self.find_key_moments(cues)
        if not moments:
            print(f"[keyframe_extract] no key visual moments found in {srt_path}")
            return []

        out_dir = Path(out_dir) if out_dir else srt_path.parent / f"{stem}_keyframes"
        out_dir.mkdir(parents=True, exist_ok=True)

        saved: list[Path] = []
        with tempfile.TemporaryDirectory(prefix="keyframe_extract_") as tmp:
            tmp_dir = Path(tmp)
            print(f"[keyframe_extract] downloading video for {stem} ({len(moments)} moment(s) to capture)")
            video_path = self.download_video(video_url, tmp_dir)
            for moment in moments:
                ts = moment["timestamp"]
                ts_compact = ts.replace(":", "")
                out_path = out_dir / f"{stem}_{ts_compact}.png"
                print(f"[keyframe_extract]   {ts} — {moment.get('reason', '')}")
                self.grab_frame(video_path, ts, out_path)
                saved.append(out_path)
            # video_path lives in the TemporaryDirectory; it is removed on context exit.

        print(f"[keyframe_extract] done. saved {len(saved)} PNG(s) to {out_dir}")
        return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    extract_p = sub.add_parser("extract", help="Find key visual moments in a FIN.srt and save frame PNGs")
    extract_p.add_argument("stem", help="e.g. some-channel_dQw4w9WgXcQ")
    extract_p.add_argument("--srt", required=True, help="Path to the FIN.srt (or GT.srt) to analyze")
    extract_p.add_argument("--video-url", required=True, help="Original YouTube video URL (for frame download)")
    extract_p.add_argument("--out-dir", default=None, help="Output directory for PNGs (default: <srt dir>/<stem>_keyframes)")

    args = parser.parse_args()
    if args.cmd == "extract":
        KeyframeExtractor().extract(args.stem, args.srt, args.video_url, args.out_dir)
