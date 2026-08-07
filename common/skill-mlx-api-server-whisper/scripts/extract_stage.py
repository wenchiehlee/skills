#!/usr/bin/env python3
"""
extract_stage.py — Extract stage transcript files from a full punct_reviewed_claude.md

Usage:
    python3 extract_stage.py <source.md> <stage_id> <offset_ts> <duration_ts> [--source-audio <name>]

Arguments:
    source.md       Full transcript file (e.g. 2357_2025_q4_punct_reviewed_claude.md)
    stage_id        Stage identifier: 0, 1, 2, ...
    offset_ts       Start of stage in full recording (MM:SS), e.g. 34:03
    duration_ts     Duration of stage audio (MM:SS), e.g. 02:00 or 10:00

Options:
    --source-audio  Override the stage audio filename (default: auto-derived from source)
    --output-dir    Output directory (default: same as source file)

Examples:
    # 2357 Q4 2025 — stage0 (2 min starting at 34:03 in full recording)
    python3 extract_stage.py 2357_2025_q4_punct_reviewed_claude.md 0 34:03 02:00

    # 2357 Q4 2025 — stage1 (10 min starting at 34:03)
    python3 extract_stage.py 2357_2025_q4_punct_reviewed_claude.md 1 34:03 10:00

    # Both stages in one command (run twice with different stage_id)
"""

import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path


def parse_ts(ts: str) -> int:
    """Parse 'MM:SS' to total seconds."""
    parts = ts.strip().split(':')
    return int(parts[0]) * 60 + int(parts[1])


def fmt_ts(secs: int) -> str:
    """Format seconds to 'MM:SS'."""
    secs = max(0, int(round(secs)))
    return f"{secs // 60:02d}:{secs % 60:02d}"


LINE_RE = re.compile(r'^\[(\d+:\d+)\s*[→>-]+\s*(\d+:\d+)\]\s*(.*)')


def extract_stage(source_path: Path, stage_id: int, offset_secs: int,
                  duration_secs: int, source_audio: str | None = None,
                  output_dir: Path | None = None) -> Path:
    """
    Extract a stage transcript from the full source file.

    Returns the path of the written output file.
    """
    # Derive output filename from source
    stem = source_path.stem  # e.g. 2357_2025_q4_punct_reviewed_claude
    # Replace the base prefix: insert _stage{N} before _punct
    if '_punct' in stem:
        out_stem = stem.replace('_punct', f'_stage{stage_id}_punct', 1)
    else:
        out_stem = stem + f'_stage{stage_id}'

    out_dir = output_dir or source_path.parent
    out_path = out_dir / (out_stem + '.md')

    # Derive stage audio name
    if source_audio is None:
        # e.g. 2357_2025_q4_punct_reviewed_claude.md → 2357_2025_q4_stage0.m4a
        base = re.sub(r'_punct.*', '', stem)  # 2357_2025_q4
        source_audio = f'{base}_stage{stage_id}.m4a'

    end_secs = offset_secs + duration_secs
    coverage_end = fmt_ts(duration_secs)

    # Read source
    lines = source_path.read_text(encoding='utf-8').splitlines()

    # Build output
    out_lines = [
        f'# Transcript: {source_audio}  [FINAL — Reviewed]',
        '',
        '| Field | Value |',
        '|-------|-------|',
        f'| **Source** | `{source_audio}` |',
        f'| **Method** | Extracted from full transcript — timestamps adjusted to stage audio |',
        f'| **Coverage** | 00:00 → {coverage_end} |',
        f'| **Note** | Derived from `{source_path.name}` |',
        f'| **Reviewed** | Claude Sonnet 4.6 股票分析師審查 — 財務術語、年份、邏輯一致性修正 |',
        f'| **Now** | {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M CST")} |',
        '',
        '---',
        '',
    ]

    content_lines = []
    for line in lines:
        m = LINE_RE.match(line)
        if m:
            ts_start = parse_ts(m.group(1))
            ts_end   = parse_ts(m.group(2))
            text     = m.group(3).rstrip()

            # Only include lines within [offset, offset+duration)
            if ts_start < offset_secs or ts_start >= end_secs:
                continue

            stage_start = ts_start - offset_secs
            stage_end   = ts_end   - offset_secs
            content_lines.append(f'**[{fmt_ts(stage_start)} → {fmt_ts(stage_end)}]** {text}')
        elif line.strip() == '':
            # Preserve blank line only if we've started outputting content
            # and the last line isn't already blank
            if content_lines and content_lines[-1] != '':
                content_lines.append('')

    # Remove trailing blank lines
    while content_lines and content_lines[-1] == '':
        content_lines.pop()

    out_lines.extend(content_lines)
    out_lines.append('')  # final newline

    out_path.write_text('\n'.join(out_lines), encoding='utf-8')
    print(f'Written: {out_path}  ({len(content_lines)} lines, coverage 00:00 -> {coverage_end})')
    return out_path


def main():
    parser = argparse.ArgumentParser(description='Extract stage transcript from full punct_reviewed_claude.md')
    parser.add_argument('source',       help='Source markdown file')
    parser.add_argument('stage_id',     type=int, help='Stage number (0, 1, 2, ...)')
    parser.add_argument('offset_ts',    help='Offset of stage start in full recording (MM:SS), e.g. 34:03')
    parser.add_argument('duration_ts',  help='Duration of stage audio (MM:SS), e.g. 02:00')
    parser.add_argument('--source-audio', default=None, help='Override stage audio filename')
    parser.add_argument('--output-dir',   default=None, help='Output directory')
    args = parser.parse_args()

    source_path  = Path(args.source)
    offset_secs  = parse_ts(args.offset_ts)
    duration_secs = parse_ts(args.duration_ts)
    output_dir   = Path(args.output_dir) if args.output_dir else None

    if not source_path.exists():
        print(f'Error: {source_path} not found', file=sys.stderr)
        sys.exit(1)

    extract_stage(source_path, args.stage_id, offset_secs, duration_secs,
                  source_audio=args.source_audio, output_dir=output_dir)


if __name__ == '__main__':
    main()
