#!/usr/bin/env python3
"""
Aggregate GoogleSearch.Factset "Quarantine Alert" GitHub issues into a
chronic-offender report: which stock codes keep getting quarantined across
the newest N issues, under which reason(s), and how often.

This is issue-triage tooling only. It does not duplicate quarantine_files.py
or process_cli.py — it reads GitHub Issues (via `gh`), not local MD/CSV data.

Usage:
    python analyze_quarantine_issues.py --repo wenchiehlee/GoogleSearch.Factset --limit 10
    python analyze_quarantine_issues.py --repo wenchiehlee/GoogleSearch.Factset --limit 10 --json-in issues.json

Requires: GitHub CLI (`gh`) authenticated for the target repo, unless --json-in
is given (a file already produced by:
    gh issue list --repo <repo> --json number,title,createdAt,body --limit N --state open
).
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict

STOCK_BLOCK_RE = re.compile(r"Stock: (\d+) \(([^)]+)\).*?(?=\nStock:|\Z)", re.S)
REASON_RE = re.compile(r"Reasons: (\w+)")


def load_issues(repo, limit, json_in):
    if json_in:
        with open(json_in, encoding="utf-8") as f:
            return json.load(f)

    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--repo", repo,
            "--json", "number,title,createdAt,body",
            "--limit", str(limit),
            "--state", "open",
            "--label", "data-quality",
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def analyze(issues):
    reason_totals = Counter()
    stock_reasons = defaultdict(Counter)
    stock_names = {}

    for issue in issues:
        body = issue.get("body", "") or ""
        for match in STOCK_BLOCK_RE.finditer(body):
            code, name = match.group(1), match.group(2)
            block = match.group(0)
            stock_names[code] = name
            for reason in REASON_RE.findall(block):
                reason_totals[reason] += 1
                stock_reasons[code][reason] += 1

    chronic = sorted(stock_reasons.items(), key=lambda kv: -sum(kv[1].values()))
    return reason_totals, chronic, stock_names


def render_report(issues, reason_totals, chronic, stock_names, threshold_ratio=0.8):
    n_issues = len(issues)
    lines = []
    lines.append(f"Issues analyzed: {n_issues}")
    lines.append(f"Issue numbers: {[i['number'] for i in issues]}")
    lines.append(f"Reason totals: {dict(reason_totals)}")
    lines.append(f"Distinct stocks flagged: {len(chronic)}")
    lines.append("")
    lines.append("Chronic offenders (code, name, total flags, reasons):")
    for code, reasons in chronic:
        total = sum(reasons.values())
        flag = " <-- appears in nearly every issue: check for a systemic/code bug, not a per-file fluke" \
            if n_issues and total >= threshold_ratio * n_issues else ""
        lines.append(f"  {code} {stock_names[code]:<10} total={total:<3} {dict(reasons)}{flag}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="wenchiehlee/GoogleSearch.Factset")
    parser.add_argument("--limit", type=int, default=10, help="How many newest open data-quality issues to pull")
    parser.add_argument("--json-in", help="Pre-fetched `gh issue list --json ...` output, skips calling gh")
    parser.add_argument("--threshold-ratio", type=float, default=0.8,
                         help="Flag a stock as chronic/systemic if it appears in >= this fraction of analyzed issues")
    args = parser.parse_args()

    issues = load_issues(args.repo, args.limit, args.json_in)
    reason_totals, chronic, stock_names = analyze(issues)
    print(render_report(issues, reason_totals, chronic, stock_names, args.threshold_ratio))


if __name__ == "__main__":
    sys.exit(main())
