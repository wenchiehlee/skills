"""
analyze_critical.py — 從現有 md 找出 critical 時段，計算 Critical-CER

概念：
  1. 掃描 *_exp1.md（或任何有時間戳的 stage）每個 segment 的財務術語密度
  2. 依 2 分鐘窗口聚合密度，標出 critical windows
  3. 對 critical segments 計算 CER vs ground truth（alphamemo/claude）
  4. 輸出 timeline heatmap + Critical-CER

Usage:
    python analyze_critical.py 2357_2025_q4
    python analyze_critical.py 2357_2025_q3 --stage final
    python analyze_critical.py 2357_2025_q3 --window 3 --top 5
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ANSI colour helpers
_RED    = "\033[31m"
_YELLOW = "\033[33m"
_GREEN  = "\033[32m"
_RESET  = "\033[0m"

def _cer_color(c: float) -> str:
    if c < 0.20:  return _GREEN
    if c < 0.35:  return _YELLOW
    return _RED

# ── 財務術語關鍵字（台灣法人說明會） ─────────────────────────────────────────

FINANCIAL_TERMS = [
    # 損益
    "毛利率", "毛利", "營業利益率", "營業利益", "淨利率", "淨利", "稅後",
    "每股盈餘", "EPS", "EBITDA",
    # 營收
    "營收", "收入", "出貨", "出貨量",
    # 成長率
    "年增", "年減", "季增", "季減", "YoY", "QoQ", "年對年", "季對季",
    "成長", "衰退", "下滑", "提升", "改善", "惡化",
    # 數字單位
    "億", "百萬", "千萬",
    # 季度
    "第一季", "第二季", "第三季", "第四季", "Q1", "Q2", "Q3", "Q4",
    "上半年", "下半年", "全年",
    # 財務科目
    "存貨", "應收帳款", "現金", "資本支出", "折舊", "攤提",
    "營業費用", "研發費用", "業外",
    # 預測
    "展望", "預期", "指引", "目標", "預測", "預計",
    # 產品/市場（ASUS 特有）
    "伺服器", "AI Server", "毛利", "佔比", "市占", "市場佔有率",
]

TERM_PATTERN = re.compile("|".join(re.escape(t) for t in FINANCIAL_TERMS))


# ── Segment 解析 ──────────────────────────────────────────────────────────────

def _ts_to_sec(ts: str) -> float:
    parts = ts.strip().split(":")
    return int(parts[0]) * 60 + float(parts[1])


def parse_segments(md_path: Path) -> list[dict]:
    """Parse **[MM:SS → MM:SS]** segments → list of {start, end, text}"""
    segs = []
    pattern = re.compile(r"^\*\*\[([\d:]+)[→\->\s]+([\d:]+)\]\*\*\s*(.*)")
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line.strip())
        if m:
            segs.append({
                "start": _ts_to_sec(m.group(1)),
                "end":   _ts_to_sec(m.group(2)),
                "text":  m.group(3).strip(),
            })
    return segs


# ── 財務術語密度計算 ──────────────────────────────────────────────────────────

def term_density(text: str) -> float:
    """財務術語字元數 / 總字元數（去空白）"""
    chars = len(text.replace(" ", ""))
    if chars == 0:
        return 0.0
    hits = sum(len(m.group()) for m in TERM_PATTERN.finditer(text))
    return hits / chars


# ── 2 分鐘窗口聚合 ───────────────────────────────────────────────────────────

def build_windows(segs: list[dict], window_min: float) -> list[dict]:
    if not segs:
        return []
    window_sec = window_min * 60
    max_end = max(s["end"] for s in segs)
    windows = []
    t = 0.0
    while t < max_end:
        t_end = t + window_sec
        win_segs = [s for s in segs if s["start"] >= t and s["start"] < t_end]
        if win_segs:
            combined_text = " ".join(s["text"] for s in win_segs)
            density = term_density(combined_text)
            windows.append({
                "start":   t,
                "end":     t_end,
                "segs":    win_segs,
                "text":    combined_text,
                "density": density,
                "chars":   len(combined_text.replace(" ", "")),
            })
        t = t_end
    return windows


# ── Timeline Heatmap ─────────────────────────────────────────────────────────

DENSITY_BARS = [" ", "░", "▒", "▓", "█"]

def density_bar(d: float) -> str:
    idx = min(int(d * 20), 4)
    return DENSITY_BARS[idx]


def cer_bar(c: float) -> str:
    """CER bar: lower is better (inverted)"""
    if c is None:
        return "  — "
    if c < 0.05:  return "████"
    if c < 0.10:  return "▓▓▓░"
    if c < 0.20:  return "▒▒░░"
    if c < 0.35:  return "░░  "
    return "    "


def print_timeline(windows: list[dict], critical_starts: set[float],
                   window_cers: dict[float, float] | None = None):
    has_cer = window_cers is not None
    header = f"  {'Time':>12}  Density  {'Chars':>6}  {'CER':>7}  CER-bar  Flag"
    divider= f"  {'----':>12}  -------  {'-----':>6}  {'---':>7}  -------  ----"
    if not has_cer:
        header = f"  {'Time':>12}  Density  {'Chars':>6}  Flag"
        divider= f"  {'----':>12}  -------  {'-----':>6}  ----"
    print(f"\n  [Timeline — financial term density" + (" + per-window CER" if has_cer else "") + "]")
    print(header)
    print(divider)
    for w in windows:
        mm_s, ss_s = divmod(int(w["start"]), 60)
        mm_e, ss_e = divmod(int(w["end"]), 60)
        flag = "◀ CRITICAL" if w["start"] in critical_starts else ""
        bar  = density_bar(w["density"])
        if has_cer:
            c = window_cers.get(w["start"])
            if c is not None:
                col = _cer_color(c)
                c_str = f"{col}{c:>7.1%}{_RESET}"
                c_bar = f"{col}{cer_bar(c)}{_RESET}"
            else:
                c_str = f"{'—':>7}"
                c_bar = "    "
            print(f"  {mm_s:02d}:{ss_s:02d}–{mm_e:02d}:{ss_e:02d}  {bar*3}{w['density']:>5.1%}  {w['chars']:>6}  {c_str}  {c_bar}  {flag}")
        else:
            print(f"  {mm_s:02d}:{ss_s:02d}–{mm_e:02d}:{ss_e:02d}  {bar*3}{w['density']:>5.1%}  {w['chars']:>6}  {flag}")


# ── CER helpers ──────────────────────────────────────────────────────────────

def _cer(reference: str, hypothesis: str) -> float:
    try:
        from jiwer import cer
        return cer(reference, hypothesis)
    except ImportError:
        print("ERROR: jiwer not installed. Run: pip install jiwer")
        sys.exit(1)


def extract_gt_text(gt_path: Path) -> str:
    """Extract plain text from ground truth (auto-detect format)."""
    from verify_cer import extract_text
    return extract_text(gt_path)


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze(stem: str, sandbox: Path, stage: str, window_min: float, top_n: int):
    stage_path = sandbox / f"{stem}_{stage}.md"
    if not stage_path.exists():
        print(f"ERROR: {stage_path.name} not found")
        sys.exit(1)

    segs = parse_segments(stage_path)
    if not segs:
        print(f"ERROR: no timestamped segments found in {stage_path.name}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"Critical Segment Analysis — {stem}  [{stage}]")
    print(f"  Segments : {len(segs)}")
    print(f"  Duration : {segs[-1]['end']/60:.1f} min")
    print(f"  Window   : {window_min} min")
    print(f"  Top-N    : {top_n} critical windows")
    print(f"{'='*70}")

    windows = build_windows(segs, window_min)

    # rank by density, pick top N
    ranked = sorted(windows, key=lambda w: w["density"], reverse=True)
    critical = ranked[:top_n]
    critical_starts = {w["start"] for w in critical}

    # ── Per-window CER using timestamped GT (claude) ──────────────────────────
    window_cers: dict[float, float] | None = None
    claude_path = sandbox / f"{stem}_punct_reviewed_claude.md"
    if claude_path.exists():
        gt_segs = parse_segments(claude_path)
        if gt_segs:
            gt_windows = build_windows(gt_segs, window_min)
            gt_by_start = {w["start"]: w["text"] for w in gt_windows}
            window_cers = {}
            for w in windows:
                gt_text = gt_by_start.get(w["start"], "")
                if gt_text and w["text"]:
                    window_cers[w["start"]] = _cer(gt_text, w["text"])

    print_timeline(windows, critical_starts, window_cers)

    # ── Critical segments text (hypothesis) ──────────────────────────────────
    critical_segs = [s for w in critical for s in w["segs"]]
    critical_segs.sort(key=lambda s: s["start"])
    hyp_text = " ".join(s["text"] for s in critical_segs)
    hyp_chars = len(hyp_text.replace(" ", ""))

    print(f"\n  Critical windows : {len(critical)}")
    print(f"  Critical chars   : {hyp_chars}")
    total_duration = sum(w["end"] - w["start"] for w in critical)
    print(f"  Critical duration: {total_duration/60:.1f} min  "
          f"({total_duration/segs[-1]['end']*100:.0f}% of total)")

    # ── CER vs ground truths ──────────────────────────────────────────────────
    gt_files = {}
    claude_path = sandbox / f"{stem}_punct_reviewed_claude.md"
    if claude_path.exists():
        gt_files["claude"] = claude_path
    for p in sorted(sandbox.glob(f"{stem}_alphamemo_*.md")):
        label = p.stem.replace(f"{stem}_", "")
        gt_files[label] = p

    if not gt_files:
        print("\n  [no ground truth found — skipping CER]")
        return

    print(f"\n  Critical-CER vs ground truths:")
    print(f"  {'GT':<20}  {'Full-CER':>9}  {'Critical-CER':>13}  {'Delta':>7}")
    print(f"  {'--':<20}  {'--------':>9}  {'------------':>13}  {'-----':>7}")

    for label, gt_path in gt_files.items():
        gt_text = extract_gt_text(gt_path)

        # Full CER (all segments vs full GT)
        full_hyp = " ".join(s["text"] for s in segs)
        full_cer = _cer(gt_text, full_hyp)

        # Critical CER
        crit_cer = _cer(gt_text, hyp_text)

        delta = crit_cer - full_cer
        delta_str = f"{delta:+.1%}"
        print(f"  {label:<20}  {full_cer:>9.1%}  {crit_cer:>13.1%}  {delta_str:>7}")

    print(f"\n  Note: Critical-CER uses only top-{top_n} high-density windows as hypothesis")
    print(f"        compared against the FULL ground truth text.")
    print(f"        Lower Critical-CER = pipeline handles financial content well.")
    print(f"{'='*70}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Critical segment analysis for Whisper pipeline")
    parser.add_argument("stem", help="e.g. 2357_2025_q3")
    parser.add_argument("--stage",   default="exp1", help="Stage to analyse (default: exp1)")
    parser.add_argument("--window",  type=float, default=2.0, help="Window size in minutes (default: 2)")
    parser.add_argument("--top",     type=int,   default=5,   help="Number of top critical windows (default: 5)")
    parser.add_argument("--sandbox", default="whisper-sandbox")
    args = parser.parse_args()

    sandbox = Path(__file__).parent / args.sandbox
    analyze(args.stem, sandbox, args.stage, args.window, args.top)


if __name__ == "__main__":
    main()
