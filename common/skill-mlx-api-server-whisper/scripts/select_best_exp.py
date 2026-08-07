"""
select_best_exp.py — Cross-stage exp ranking by 評分

Reads cer_report.md from all available stages (stage0, stage2, sample/stage1),
aggregates 評分 scores, computes average + consistency (1 - CV), and ranks exps.

Usage:
    python select_best_exp.py 2357_2025_q4 --sandbox whisper-sandbox
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


STAGE_SUFFIXES = [
    ("stage0", "Stage 0 (~2min)"),
    ("stage1", "Stage 1 (~10min)"),
    ("stage2", "Stage 2 (~8min)"),
]


def parse_scores(report_path: Path) -> dict[str, float]:
    """Parse exp→評分 from a cer_report.md KPI table."""
    scores: dict[str, float] = {}
    for line in report_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s+(exp\d+)\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+)\s*$", line)
        if m:
            scores[m.group(1)] = float(m.group(2))
    return scores


def main():
    parser = argparse.ArgumentParser(description="Select best exp by cross-stage 評分")
    parser.add_argument("stem", help="e.g. 2357_2025_q4")
    parser.add_argument("--sandbox", default="mlx-api-server-whisper/whisper-sandbox")
    args = parser.parse_args()

    sandbox = Path(args.sandbox)

    # ── Load available stage reports ──────────────────────────────────────────
    stage_scores: dict[str, dict[str, float]] = {}   # suffix → {exp: score}
    for suffix, label in STAGE_SUFFIXES:
        report = sandbox / f"{args.stem}_{suffix}_cer_report.md"
        if report.exists():
            scores = parse_scores(report)
            if scores:
                stage_scores[suffix] = scores
                print(f"  [loaded] {label:18s} → {report.name}  ({len(scores)} exps)")
            else:
                print(f"  [skip]   {label:18s} — no exp scores in {report.name}")
        else:
            print(f"  [skip]   {label:18s} — {report.name} not found")

    if not stage_scores:
        print("\n⚠ No stage reports found — run eval-sample first")
        sys.exit(0)

    # ── Collect all exp names across all stages ───────────────────────────────
    all_exps: list[str] = sorted(
        {exp for scores in stage_scores.values() for exp in scores},
        key=lambda x: int(re.search(r"\d+", x).group())
    )

    # ── Compute per-exp: avg, std, consistency, availability ─────────────────
    results: list[dict] = []
    for exp in all_exps:
        vals = [stage_scores[s][exp] for s in stage_scores if exp in stage_scores[s]]
        if not vals:
            continue
        avg   = sum(vals) / len(vals)
        std   = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5
        cv    = std / avg if avg > 0 else 0.0        # coefficient of variation
        cons  = max(0.0, 1.0 - cv)                  # consistency: 1 = perfectly stable
        avail = len(vals) / len(stage_scores)         # fraction of stages available
        final = avg * cons * (0.8 + 0.2 * avail)    # penalise missing stages slightly
        results.append({
            "exp":   exp,
            "avg":   avg,
            "std":   std,
            "cons":  cons,
            "avail": avail,
            "final": final,
            "vals":  vals,
        })

    results.sort(key=lambda x: x["final"], reverse=True)

    # ── Print ranking ─────────────────────────────────────────────────────────
    n_stages = len(stage_scores)
    stage_labels = [STAGE_SUFFIXES[i][1] for i, (s, _) in enumerate(STAGE_SUFFIXES) if s in stage_scores]

    print("")
    print("════════════════════════════════════════════════════════════")
    print(f"  Best Exp by 評分  ({n_stages} stage(s): {', '.join(stage_labels)})")
    print("════════════════════════════════════════════════════════════")
    header = f"  {'Rank':<5} {'Exp':<6} {'Avg':>6} {'Std':>5} {'Cons%':>6} {'Stages':>6}  {'Final':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for i, r in enumerate(results, 1):
        marker = "  ← BEST" if i == 1 else ""
        vals_str = " / ".join(f"{v:.1f}" for v in r["vals"])
        print(f"  #{i:<4} {r['exp']:<6} {r['avg']:>6.1f} {r['std']:>5.1f} "
              f"{r['cons']*100:>5.1f}% {int(r['avail']*n_stages):>2}/{n_stages}   "
              f"{r['final']:>6.1f}  [{vals_str}]{marker}")

    best = results[0]
    print("")
    print(f"  → Best exp: {best['exp']}  "
          f"(avg={best['avg']:.1f}, consistency={best['cons']*100:.1f}%)")
    print("════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
