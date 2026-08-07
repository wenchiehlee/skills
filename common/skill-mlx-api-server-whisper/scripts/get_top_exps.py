"""
get_top_exps.py — Print top-N exp numbers from stage cer_reports.

Reads {stem}_stage0_cer_report.md and {stem}_sample_cer_report.md,
averages 評分 across available reports, and prints the top-N exp
numbers as a comma-separated string (e.g. "3,1").

Usage:
    python get_top_exps.py 2357_2025_q4 --sandbox Whisper-API-Server/whisper-sandbox
    python get_top_exps.py 2357_2025_q4 --top-n 2
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPORT_SUFFIXES = ["stage0", "stage1"]


def parse_scores(report_path: Path) -> dict[str, float]:
    scores: dict[str, float] = {}
    for line in report_path.read_text(encoding="utf-8").splitlines():
        m = re.match(
            r"^\s+(exp\d+)\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+)\s*$", line
        )
        if m:
            scores[m.group(1)] = float(m.group(2))
    return scores


def main():
    parser = argparse.ArgumentParser(description="Get top-N exp numbers from cer_reports")
    parser.add_argument("stem", help="e.g. 2357_2025_q4")
    parser.add_argument("--sandbox", default="Whisper-API-Server/whisper-sandbox")
    parser.add_argument("--top-n", type=int, default=2)
    args = parser.parse_args()

    sandbox = Path(args.sandbox)
    accumulated: dict[str, list[float]] = {}

    for suffix in REPORT_SUFFIXES:
        rpt = sandbox / f"{args.stem}_{suffix}_cer_report.md"
        if not rpt.exists():
            print(f"  [skip] {rpt.name} not found", file=sys.stderr)
            continue
        scores = parse_scores(rpt)
        if not scores:
            print(f"  [skip] {rpt.name} — no exp scores", file=sys.stderr)
            continue
        print(f"  [loaded] {rpt.name} ({len(scores)} exps)", file=sys.stderr)
        for exp, score in scores.items():
            accumulated.setdefault(exp, []).append(score)

    if not accumulated:
        print("  [warn] no exp scores found — falling back to all exps", file=sys.stderr)
        sys.exit(1)

    ranked = sorted(
        accumulated.items(),
        key=lambda x: sum(x[1]) / len(x[1]),
        reverse=True,
    )[: args.top_n]

    for exp, vals in ranked:
        avg = sum(vals) / len(vals)
        print(f"  {exp}: avg={avg:.1f} over {len(vals)} report(s)", file=sys.stderr)

    # stdout: only the comma-separated numbers for shell capture
    print(",".join(e.replace("exp", "") for e, _ in ranked))


if __name__ == "__main__":
    main()
