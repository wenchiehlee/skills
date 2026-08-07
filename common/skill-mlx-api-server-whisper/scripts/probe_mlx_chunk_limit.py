"""
probe_mlx_chunk_limit.py
========================
Find the maximum safe chunk size for Qwen2.5-14B-Instruct-4bit before
it starts truncating segments at the end of a chunk.

Strategy:
  - Load real segments from stage2 exp1 (394 segments, ~20 min audio)
  - Feed increasing numbers of segments (N=5,10,15,20,25,30,40,50)
    in the same format used by step_merge_mlx()
  - For each N, check if the LAST 3 segments are fully output or truncated
  - Report the threshold where truncation starts

Usage (on Mac mini):
    python3 mlx-api-server-whisper/probe_mlx_chunk_limit.py \
        --sandbox mlx-api-server-whisper/whisper-sandbox \
        --stem 2357_2025_q4_stage2
"""

import re
import sys
import time
import argparse
from pathlib import Path

# ── Segment parsing (mirrors postprocess.py) ──────────────────────────────────

SEG_RE = re.compile(
    r'\*\*\[(\d+:\d+)\s*[→\-]+\s*>?\s*(\d+:\d+)\]\*\*\s*(.*)'
)

def mmss_to_sec(mmss: str) -> float:
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)

def parse_segments(path: Path):
    segs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = SEG_RE.match(line.strip())
        if m:
            segs.append({
                "start": mmss_to_sec(m.group(1)),
                "end":   mmss_to_sec(m.group(2)),
                "text":  m.group(3).strip(),
                "ts":    f"[{m.group(1)} → {m.group(2)}]",
            })
    return segs

def format_seg(s: dict) -> str:
    return f"{s['ts']} {s['text']}"

# ── Scoring: check if last K segments are fully output ────────────────────────

def check_last_segs(output: str, input_segs: list, last_k: int = 3) -> dict:
    """
    For each of the last_k input segments, check if the output contains
    the full text. Returns per-segment status.
    """
    results = []
    for seg in input_segs[-last_k:]:
        start_key = seg["ts"].split("→")[0].strip().lstrip("[").strip()
        expected  = seg["text"]
        # find line in output matching this timestamp
        out_text = ""
        for line in output.splitlines():
            if start_key in line:
                m = re.match(r'\[[\d:]+\s*[→\-]+\s*>?\s*[\d:]+\]\s*(.*)', line)
                if m:
                    out_text = m.group(1).strip()
                break

        if not out_text:
            status = "MISSING"
        elif len(out_text) >= len(expected) * 0.95:
            status = "FULL ✓"
        elif len(out_text) >= len(expected) * 0.70:
            status = "PARTIAL ~"
        else:
            status = f"TRUNC ✗ ({len(out_text)}/{len(expected)}ch)"

        results.append({
            "ts": seg["ts"], "expected": expected,
            "got": out_text, "status": status,
        })
    return results


# ── Prompt builder (mirrors _merge_system_mlx in postprocess.py) ──────────────

def build_prompt(segs: list, tokenizer) -> tuple[str, int]:
    """Build the merge prompt for N segments of exp1 only."""
    body = "【Exp1】\n" + "\n".join(format_seg(s) for s in segs)
    system = """\
你是台灣上市公司法人說明會的專業逐字稿編輯。
以下是同一小段音頻的 1 個 AI 轉錄版本（Exp1）。
請輸出逐字稿，每行 [MM:SS → MM:SS] 文字，保持繁體中文，不截斷任何句子。
只輸出逐字稿，不要任何說明。
"""
    full_prompt = system + "\n\n" + body
    messages = [{"role": "user", "content": full_prompt}]
    formatted = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    token_count = len(tokenizer.encode(formatted))
    return formatted, token_count


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sandbox", default="mlx-api-server-whisper/whisper-sandbox")
    parser.add_argument("--stem",    default="2357_2025_q4_stage2")
    parser.add_argument("--model",   default="mlx-community/Qwen2.5-14B-Instruct-4bit")
    parser.add_argument(
        "--sizes", default="5,10,15,20,25,30,40,50,60,80",
        help="Comma-separated chunk sizes (number of segments) to test"
    )
    args = parser.parse_args()

    sizes = [int(x) for x in args.sizes.split(",")]
    sandbox = Path(args.sandbox)

    # Load real segments
    exp_path = sandbox / f"{args.stem}_exp1.md"
    if not exp_path.exists():
        print(f"ERROR: {exp_path} not found")
        sys.exit(1)

    all_segs = parse_segments(exp_path)
    print(f"Loaded {len(all_segs)} segments from {exp_path.name}")

    # Load model
    try:
        from mlx_lm import load, generate
    except ImportError:
        print("ERROR: pip install mlx-lm")
        sys.exit(1)

    print(f"Loading model: {args.model} …")
    model, tokenizer = load(args.model)
    print("Model ready.\n")

    print(f"{'N':>4}  {'tokens':>7}  {'last3 status':<50}  {'time':>6}")
    print("-" * 80)

    results = []
    for n in sizes:
        if n > len(all_segs):
            print(f"{n:>4}  (not enough segments, max={len(all_segs)})")
            continue

        # Take segments from 1/3 point — avoids opening (easy) and Q&A short segs
        start = len(all_segs) // 3
        chunk = all_segs[start : start + n]

        prompt_text, token_count = build_prompt(chunk, tokenizer)

        t0 = time.time()
        output = generate(model, tokenizer, prompt=prompt_text,
                          max_tokens=4096, verbose=False)
        elapsed = time.time() - t0

        checks = check_last_segs(output, chunk, last_k=3)
        statuses = " | ".join(f"{c['status']}" for c in checks)

        print(f"{n:>4}  {token_count:>7}  {statuses:<50}  {elapsed:>5.1f}s")

        # Print detail for diagnosis
        print(f"       Input segs used: {[s['ts']+' '+s['text'][:20] for s in chunk[-3:]]}")
        out_lines = [l for l in output.splitlines() if re.match(r'\[[\d:]+', l)]
        print(f"       Model output last 3 lines: {out_lines[-3:] if out_lines else ['(no timestamp lines)']}")

        results.append({
            "n": n, "tokens": token_count, "checks": checks,
            "output_len": len(output), "elapsed": elapsed,
        })

        # Stop only if ALL last 3 are TRUNC/MISSING (not just one)
        all_bad = all(c["status"].startswith("TRUNC") or c["status"] == "MISSING"
                      for c in checks)
        if all_bad and n >= 20:
            print(f"\n  *** TRUNCATION THRESHOLD REACHED at N={n} ({token_count} tokens) ***")
            break

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    safe_n  = None
    trunc_n = None
    for r in results:
        any_bad  = any(c["status"].startswith("TRUNC") or c["status"] == "MISSING"
                       for c in r["checks"])
        all_good = all(c["status"] == "FULL ✓" for c in r["checks"])
        tag = "SAFE ✓" if all_good else ("TRUNC ✗" if any_bad else "PARTIAL ~")
        print(f"  N={r['n']:>3}  tokens={r['tokens']:>6}  → {tag}")
        if all_good:
            safe_n = r["n"]
        if any_bad and trunc_n is None:
            trunc_n = r["n"]

    print()
    if safe_n:
        print(f"  Last safe chunk size : N={safe_n} segments")
    if trunc_n:
        print(f"  First truncation at  : N={trunc_n} segments")
        # Estimate seconds: stage2 is ~20min / 394 segs ≈ 3.05 sec/seg
        sec_per_seg = 1200 / len(all_segs)
        safe_sec = int((trunc_n - 1) * sec_per_seg) if trunc_n > 1 else 0
        print(f"  Recommended MLX_CHUNK_WINDOW_SEC ≤ {safe_sec}s")
    print()


if __name__ == "__main__":
    main()
