#!/usr/bin/env python3
"""Validate a generated podcast RSS feed and its local WebVTT transcripts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

TIMESTAMP_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})$")


def timestamp(value: str) -> float:
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        raise ValueError(f"invalid WebVTT timestamp: {value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"invalid WebVTT timestamp: {value}")
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def validate_vtt(path: Path) -> list[str]:
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "WEBVTT":
        return [f"{path}: missing WEBVTT header"]
    previous_start = -1.0
    for line_number, line in enumerate(lines, start=1):
        if " --> " not in line:
            continue
        start_text, end_text = line.split(" --> ", 1)
        try:
            start = timestamp(start_text)
            end = timestamp(end_text.split(" ", 1)[0])
        except ValueError as exc:
            errors.append(f"{path}:{line_number}: {exc}")
            continue
        if start < previous_start:
            errors.append(f"{path}:{line_number}: cue starts out of order")
        if end <= start:
            errors.append(f"{path}:{line_number}: cue end is not after start")
        previous_start = start
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", type=Path)
    args = parser.parse_args()
    feed = args.feed.resolve()
    try:
        root = ElementTree.parse(feed).getroot()
    except (ElementTree.ParseError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if root.tag != "rss":
        print(f"ERROR: {feed}: root element is not rss", file=sys.stderr)
        return 1

    channel = root.find("channel")
    if channel is None:
        print(f"ERROR: {feed}: missing channel", file=sys.stderr)
        return 1

    errors: list[str] = []
    seen_guids: set[str] = set()
    transcript_count = 0
    podcast_ns = "{https://podcastindex.org/namespace/1.0}transcript"
    for item in channel.findall("item"):
        guid = item.findtext("guid", "")
        if not guid or guid in seen_guids:
            errors.append(f"{feed}: missing or duplicate guid: {guid!r}")
        seen_guids.add(guid)
        enclosure = item.find("enclosure")
        if enclosure is None or not enclosure.get("url", "").endswith(".m4a"):
            errors.append(f"{feed}: item {guid!r} has no .m4a enclosure")
        transcript = item.find(podcast_ns)
        if transcript is not None:
            transcript_count += 1
            parsed = urlparse(transcript.get("url", ""))
            local_path = feed.parent / "transcripts" / Path(parsed.path).name
            if not local_path.exists() and feed.parent.name == "docs":
                channel = Path(parsed.path).parent.parent.name
                local_path = feed.parent / channel / "transcripts" / Path(parsed.path).name
            if not local_path.exists():
                errors.append(f"{feed}: missing transcript {local_path}")
            else:
                errors.extend(validate_vtt(local_path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {feed} ({len(seen_guids)} item(s), {transcript_count} transcript(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
