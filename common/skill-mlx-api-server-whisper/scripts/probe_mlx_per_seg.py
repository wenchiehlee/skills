"""
probe_mlx_per_seg.py
====================
Probe Qwen2.5-14B synthesis behaviour in per-segment selection mode.

Goal: understand *why* the model synthesises text even with verbatim prompts,
and discover which prompt strategy (or pure-Python fallback) avoids it.

Strategies tested for each segment:
  A  current    — current per-seg prompt ("選出最準確版本並直接輸出")
  B  strict     — numbered list + "輸出版本N的全部原文，一字不差"
  C  copy_back  — "請完整複製最準確版本的全部文字，不得增減"
  D  py_longest — Python only: pick longest version (no LLM)
  E  py_majority— Python only: pick version with smallest avg edit distance to others

Metrics per case × strategy:
  verbatim   — exact match to any input version? (True/False)
  edit_dist  — Levenshtein distance to closest input version
  ed_pct     — edit_dist / len(closest_input) × 100
  output     — first 40 chars of output
  gt_dist    — edit distance to turboscribe GT (if available)

Usage (on Mac mini):
    python3 mlx-api-server-whisper/probe_mlx_per_seg.py \\
        --sandbox mlx-api-server-whisper/whisper-sandbox \\
        --stem 2357_2025_q4_stage1
"""

import re
import sys
import time
import random
import argparse
from pathlib import Path

# ── Levenshtein (no external dep) ─────────────────────────────────────────────

def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a):
        curr = [i + 1] + [0] * lb
        for j, cb in enumerate(b):
            curr[j+1] = min(
                prev[j+1] + 1,
                curr[j]   + 1,
                prev[j]   + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[lb]


# ── Segment parsing ────────────────────────────────────────────────────────────

SEG_RE = re.compile(
    r'\*\*\[(\d+:\d+)\s*[→\-]+\s*>?\s*(\d+:\d+)\]\*\*\s*(.*)'
)
SRT_RE = re.compile(r'(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)')

def mmss_to_sec(mmss: str) -> int:
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)

def hhmmss_to_sec(ts: str) -> int:
    ts = ts.split(",")[0]
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return int(parts[0]) * 60 + int(parts[1])

def parse_md_segments(path: Path) -> dict[int, str]:
    """Returns {start_sec: text} from .md file."""
    result: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = SEG_RE.match(line.strip())
        if m:
            result[mmss_to_sec(m.group(1))] = m.group(3).strip()
    return result

def parse_srt_segments(path: Path) -> dict[int, str]:
    """Returns {start_sec: text} from a GT file.

    Supports three formats:
      1. Standard SRT:  HH:MM:SS,mmm --> HH:MM:SS,mmm
      2. Custom mmss:   (M:SS) text   (TurboScribe export format used in this project)
      3. Bracket md:    **[MM:SS → MM:SS]** text
    """
    result: dict[int, str] = {}
    text_content = path.read_text(encoding="utf-8")
    lines = text_content.splitlines()

    # Detect format from first non-empty, non-digit line
    CUSTOM_RE = re.compile(r'^\((\d+:\d+)\)\s+(.*)')

    format_detected = None
    for line in lines:
        line = line.strip()
        if not line or line.isdigit():
            continue
        if SRT_RE.match(line):
            format_detected = "srt"
            break
        if CUSTOM_RE.match(line):
            format_detected = "custom"
            break
        if SEG_RE.match(line):
            format_detected = "md"
            break

    if format_detected == "custom":
        # (M:SS) text — one segment per line
        for line in lines:
            m = CUSTOM_RE.match(line.strip())
            if m:
                sec = mmss_to_sec(m.group(1))
                result[sec] = m.group(2).strip()
        return result

    if format_detected == "md":
        return parse_md_segments(path)

    # Standard SRT
    i = 0
    while i < len(lines):
        if SRT_RE.match(lines[i].strip()):
            start_sec = hhmmss_to_sec(lines[i].split("-->")[0].strip())
            texts = []
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].strip().isdigit():
                texts.append(lines[j].strip())
                j += 1
            text = " ".join(texts)
            text = re.sub(r'<[^>]+>', '', text).strip()
            if text:
                result[start_sec] = text
            i = j
        else:
            i += 1
    return result


# ── Strategies ────────────────────────────────────────────────────────────────

def strategy_python_longest(texts: list[str]) -> str:
    return max(texts, key=len)

def strategy_python_majority(texts: list[str]) -> str:
    """Pick version with smallest average edit distance to all others."""
    best = texts[0]
    best_avg = float("inf")
    for candidate in texts:
        others = [t for t in texts if t != candidate]
        if not others:
            return candidate
        avg = sum(edit_distance(candidate, o) for o in others) / len(others)
        if avg < best_avg:
            best_avg = avg
            best = candidate
    return best

STRATEGY_PROMPTS = {
    "A_current": """\
以下是同一時段的數個語音轉錄版本，請選出最準確的一個版本並直接輸出其原文。
規則：
1. 只能從下列版本中選一個，直接輸出該版本的原文，一字不差，不得修改、不得合併
2. 只輸出文字本身，不加時間戳記，不加說明，不加版本編號
3. 英文詞彙（AI、server、follow、pattern 等）保留英文原文
4. 選擇文字最完整的版本

版本：
{versions}""",

    "B_strict": """\
以下列出同一時段的語音辨識版本。
請先在心中判斷哪個版本最準確，然後「直接複製貼上」該版本，一個字都不能改。

{numbered_versions}

輸出：只輸出你選擇的那個版本的原文，不加任何說明或編號。""",

    "C_copy_back": """\
你是一個複製工具。以下有數個版本，請找出最準確的一個版本，然後把它的全部文字完整複製一遍。
重要：輸出必須與你選擇的版本完全相同，不得增加、刪除或修改任何文字。

{versions}

請複製最準確版本的全部文字：""",
}

def build_llm_prompt(strategy_key: str, texts: list[str]) -> str:
    template = STRATEGY_PROMPTS[strategy_key]
    versions_plain = "\n".join(f"- {t}" for t in texts)
    numbered = "\n".join(f"版本{i+1}：{t}" for i, t in enumerate(texts))
    return template.format(versions=versions_plain, numbered_versions=numbered)

def call_llm(model, tokenizer, prompt_text: str, max_tokens: int = 128) -> tuple[str, int]:
    from mlx_lm import generate
    messages = [{"role": "user", "content": prompt_text}]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    token_count = len(tokenizer.encode(formatted))
    output = generate(model, tokenizer, prompt=formatted,
                      max_tokens=max_tokens, verbose=False)
    return output.strip(), token_count


# ── Analysis helpers ──────────────────────────────────────────────────────────

def analyse_output(output: str, texts: list[str], gt: str | None = None) -> dict:
    verbatim = output in texts
    dists = [edit_distance(output, t) for t in texts]
    min_dist = min(dists)
    closest = texts[dists.index(min_dist)]
    ed_pct = min_dist / max(len(closest), 1) * 100
    result = {
        "verbatim": verbatim,
        "edit_dist": min_dist,
        "ed_pct": ed_pct,
        "output_snippet": output[:50],
        "gt_dist": edit_distance(output, gt) if gt else None,
    }
    return result

def diff_chars(a: str, b: str) -> str:
    """Simple inline diff: show added chars in [+x] deleted in [-x]."""
    import difflib
    matcher = difflib.SequenceMatcher(None, a, b)
    result = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            result.append(a[i1:i2])
        elif op == "replace":
            result.append(f"[-{a[i1:i2]}][+{b[j1:j2]}]")
        elif op == "delete":
            result.append(f"[-{a[i1:i2]}]")
        elif op == "insert":
            result.append(f"[+{b[j1:j2]}]")
    return "".join(result)


# ── Main ───────────────────────────────────────────────────────────────────────

def avg_pairwise_ed(texts: list[str]) -> float:
    """Average pairwise edit distance across all pairs in the list."""
    if len(texts) < 2:
        return 0.0
    total, count = 0, 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            total += edit_distance(texts[i], texts[j])
            count += 1
    return total / count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", default="mlx-api-server-whisper/whisper-sandbox")
    parser.add_argument("--stem",    default="2357_2025_q4_stage1")
    parser.add_argument("--model",   default="mlx-community/Qwen2.5-14B-Instruct-4bit")
    parser.add_argument("--exps",    default="1,2,3,4,6",
                        help="Comma-separated exp numbers to load")
    parser.add_argument("--extra-cases", default="",
                        help="Extra MM:SS timestamps to force-include (e.g. '0:25,0:29,0:34')")
    parser.add_argument("--n-random", type=int, default=3,
                        help="Number of random segments to test")
    parser.add_argument("--n-high-variance", type=int, default=5,
                        help="Number of highest-variance segments to test (0=disable)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM strategies, only run Python strategies")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    sandbox = Path(args.sandbox)
    exp_nums = [int(x) for x in args.exps.split(",")]
    random.seed(args.seed)

    # ── Load all exp segments ────────────────────────────────────────────────
    exp_data: dict[str, dict[int, str]] = {}
    for n in exp_nums:
        p = sandbox / f"{args.stem}_exp{n}.md"
        if not p.exists():
            print(f"WARNING: {p} not found, skipping exp{n}")
            continue
        exp_data[f"exp{n}"] = parse_md_segments(p)
        print(f"  Loaded exp{n}: {len(exp_data[f'exp{n}'])} segments")

    if not exp_data:
        print("ERROR: no exp files found")
        sys.exit(1)

    # ── Load GT (turboscribe) ────────────────────────────────────────────────
    gt_data: dict[int, str] = {}
    gt_path = sandbox / f"{args.stem}_turboscribe.srt"
    if gt_path.exists():
        gt_data = parse_srt_segments(gt_path)
        print(f"  Loaded GT: {len(gt_data)} segments from {gt_path.name}")
    else:
        print(f"  NOTE: No GT file found at {gt_path}")

    # ── Build shared timeline: timestamps present in ALL exps ───────────────
    all_ts = set.intersection(*(set(v.keys()) for v in exp_data.values()))
    all_ts = sorted(all_ts)
    print(f"\n  Shared timestamps (present in all exps): {len(all_ts)}")

    # ── Compute per-timestamp variance (avg pairwise edit distance across exps)
    variance: dict[int, float] = {}
    for ts in all_ts:
        texts = [exp_data[e][ts] for e in exp_data if ts in exp_data[e]]
        variance[ts] = avg_pairwise_ed(texts)

    # ── Select test cases ────────────────────────────────────────────────────
    # 1. Force-include explicit timestamps
    force_ts: list[int] = []
    if args.extra_cases:
        for ts_str in args.extra_cases.split(","):
            ts_str = ts_str.strip()
            if not ts_str:
                continue
            try:
                sec = mmss_to_sec(ts_str if ":" in ts_str else f"0:{ts_str}")
                if sec in all_ts:
                    force_ts.append(sec)
                else:
                    nearest = min(all_ts, key=lambda x: abs(x - sec))
                    print(f"  NOTE: {ts_str} ({sec}s) not in shared ts, using nearest "
                          f"{nearest//60}:{nearest%60:02d} (variance={variance[nearest]:.1f})")
                    force_ts.append(nearest)
            except Exception as e:
                print(f"  WARNING: could not parse timestamp '{ts_str}': {e}")

    # 2. High-variance segments: top N by avg pairwise edit distance
    hv_ts: list[int] = []
    if args.n_high_variance > 0:
        sorted_by_var = sorted(all_ts, key=lambda t: variance[t], reverse=True)
        for t in sorted_by_var:
            if t not in force_ts and variance[t] > 0:
                hv_ts.append(t)
                if len(hv_ts) >= args.n_high_variance:
                    break
        print(f"\n  High-variance segments (top {len(hv_ts)}):")
        for t in hv_ts:
            texts = [exp_data[e][t] for e in exp_data if t in exp_data[e]]
            print(f"    {t//60}:{t%60:02d}  var={variance[t]:.1f}  "
                  f"texts: {[tx[:20] for tx in texts]}")

    # 3. Random sample from middle
    mid_ts = [t for t in all_ts
              if len(all_ts) // 6 <= all_ts.index(t) <= len(all_ts) * 5 // 6]
    remaining = [t for t in mid_ts if t not in force_ts and t not in hv_ts]
    random_ts = random.sample(remaining, min(args.n_random, len(remaining)))

    test_ts = sorted(set(force_ts + hv_ts + random_ts))
    print(f"\n  Test cases: {len(test_ts)} timestamps")
    print(f"    Force-include ({len(force_ts)}): {[f'{t//60}:{t%60:02d}' for t in force_ts]}")
    print(f"    High-variance ({len(hv_ts)}):    {[f'{t//60}:{t%60:02d}' for t in hv_ts]}")
    print(f"    Random        ({len(random_ts)}): {[f'{t//60}:{t%60:02d}' for t in random_ts]}")

    # ── Load model ───────────────────────────────────────────────────────────
    model, tokenizer = None, None
    if not args.no_llm:
        try:
            from mlx_lm import load
        except ImportError:
            print("ERROR: pip install mlx-lm")
            sys.exit(1)
        print(f"\nLoading model: {args.model} …")
        model, tokenizer = load(args.model)
        print("Model ready.\n")

    # ── Run probe ────────────────────────────────────────────────────────────
    all_results: list[dict] = []
    strategy_keys = ([] if args.no_llm else list(STRATEGY_PROMPTS.keys())) + ["D_py_longest", "E_py_majority"]

    print("\n" + "=" * 100)
    print(f"  PROBE: per-segment synthesis behaviour  |  {len(test_ts)} cases × {len(strategy_keys)} strategies")
    print("=" * 100)
    print(f"\n{'Timestamp':<12} {'Strategy':<14} {'Verbatim':<9} {'ED':<5} {'ED%':<6} {'GT_ED':<7} Output snippet")
    print("-" * 100)

    for ts in test_ts:
        label = f"{ts//60}:{ts%60:02d}"
        texts = [exp_data[e][ts] for e in exp_data if ts in exp_data[e]]
        if not texts:
            continue
        gt_text = gt_data.get(ts)

        # Find GT by nearest timestamp (turboscribe uses only start-second,
        # may differ by up to ~5s from exp segment boundaries)
        if not gt_text and gt_data:
            nearest_gt = min(gt_data.keys(), key=lambda x: abs(x - ts))
            if abs(nearest_gt - ts) <= 5:
                gt_text = gt_data[nearest_gt]

        # Print input versions
        print(f"\n[{label}] Input versions ({len(texts)}):")
        for i, t in enumerate(texts):
            print(f"         exp{exp_nums[i] if i < len(exp_nums) else '?'}: {t}")
        if gt_text:
            print(f"         GT:  {gt_text}")

        for strategy in strategy_keys:
            t0 = time.time()
            token_info = ""

            if strategy == "D_py_longest":
                output = strategy_python_longest(texts)
                elapsed = time.time() - t0

            elif strategy == "E_py_majority":
                output = strategy_python_majority(texts)
                elapsed = time.time() - t0

            else:
                prompt_text = build_llm_prompt(strategy, texts)
                output, tokens = call_llm(model, tokenizer, prompt_text)
                elapsed = time.time() - t0
                token_info = f" ({tokens}tok)"

            metrics = analyse_output(output, texts, gt_text)
            verbatim_icon = "✓" if metrics["verbatim"] else "✗"
            gt_dist_s = f"{metrics['gt_dist']}" if metrics["gt_dist"] is not None else "—"
            snippet = output[:50].replace("\n", "↵")

            print(f"  [{label}]  {strategy:<14} {verbatim_icon:<9} "
                  f"{metrics['edit_dist']:<5} {metrics['ed_pct']:.1f}%  {gt_dist_s:<7} "
                  f"{snippet}{token_info}  {elapsed:.1f}s")

            # If not verbatim, show diff against closest input
            if not metrics["verbatim"] and metrics["edit_dist"] > 0:
                dists = [edit_distance(output, t) for t in texts]
                closest = texts[dists.index(min(dists))]
                diff = diff_chars(closest, output)
                print(f"           diff vs closest: {diff[:120]}")

            all_results.append({
                "ts": label, "strategy": strategy,
                "verbatim": metrics["verbatim"],
                "ed": metrics["edit_dist"],
                "ed_pct": metrics["ed_pct"],
                "gt_dist": metrics["gt_dist"],
                "output": output,
            })

    # ── Summary table ────────────────────────────────────────────────────────
    print("\n\n" + "=" * 100)
    print("SUMMARY — verbatim rate and avg edit distance per strategy")
    print("=" * 100)
    print(f"\n{'Strategy':<16} {'Verbatim':<10} {'VerbatimRate':<14} {'AvgED':<8} {'AvgED%':<8} {'AvgGT_ED'}")
    print("-" * 70)

    for strat in strategy_keys:
        rows = [r for r in all_results if r["strategy"] == strat]
        if not rows:
            continue
        n_verbatim = sum(1 for r in rows if r["verbatim"])
        avg_ed = sum(r["ed"] for r in rows) / len(rows)
        avg_ed_pct = sum(r["ed_pct"] for r in rows) / len(rows)
        gt_rows = [r for r in rows if r["gt_dist"] is not None]
        avg_gt = sum(r["gt_dist"] for r in gt_rows) / len(gt_rows) if gt_rows else None
        avg_gt_s = f"{avg_gt:.1f}" if avg_gt is not None else "—"
        print(f"  {strat:<14} {n_verbatim}/{len(rows):<8}  {n_verbatim/len(rows)*100:>5.0f}%       "
              f"{avg_ed:>6.1f}   {avg_ed_pct:>5.1f}%   {avg_gt_s}")

    print()

    # ── Key finding ──────────────────────────────────────────────────────────
    print("=" * 100)
    print("KEY FINDINGS")
    print("=" * 100)

    py_majority_rows = [r for r in all_results if r["strategy"] == "E_py_majority"]
    py_longest_rows  = [r for r in all_results if r["strategy"] == "D_py_longest"]
    best_llm_strat   = None
    best_llm_rate    = -1
    for strat in [s for s in strategy_keys if not s.startswith(("D_", "E_"))]:
        rows = [r for r in all_results if r["strategy"] == strat]
        rate = sum(1 for r in rows if r["verbatim"]) / len(rows) if rows else 0
        if rate > best_llm_rate:
            best_llm_rate = rate
            best_llm_strat = strat

    if py_majority_rows:
        pm_rate = sum(1 for r in py_majority_rows if r["verbatim"]) / len(py_majority_rows)
        print(f"  Python majority vote  verbatim rate: {pm_rate:.0%}  (ED vs input always 0)")
    if py_longest_rows:
        pl_rate = sum(1 for r in py_longest_rows if r["verbatim"]) / len(py_longest_rows)
        print(f"  Python longest        verbatim rate: {pl_rate:.0%}")
    if best_llm_strat:
        print(f"  Best LLM strategy: {best_llm_strat}  verbatim rate: {best_llm_rate:.0%}")

    print()
    print("  NOTE: Python strategies are always verbatim by definition.")
    print("  Compare GT edit distances to judge transcription quality.")
    print()


if __name__ == "__main__":
    main()
