# Usage: run from mlx-api-server-whisper/ directory
#   python gen_cer_difference.py 2357_2025_q3
#   python gen_cer_difference.py 2357_2025_q3 2357_2025_q4
#
# Output: GroundTrue/{stem}_cer_difference.md
#   - Summary table: CER, key_CER, sub/ins/del counts
#   - Per-error detail table: op type, TS ref, AM hyp, context

import sys
from pathlib import Path
sys.path.insert(0, '.')
from verify_cer import _normalize_for_cer, _classify_errors, _get_key_error_details, extract_text, _cer

def gen_cer_difference(stem: str) -> None:
    gt_dir   = Path("GroundTrue")
    ts_path  = gt_dir / f"{stem}_GT.srt"
    # Use the most recent AlphaMemo draft (latest MMDD suffix)
    am_files = sorted((gt_dir / "Draft").glob(f"{stem}_alphamemo_*.md"))
    if not am_files:
        print(f"No AlphaMemo draft found for {stem}"); return
    am_path  = am_files[-1]   # latest by filename sort
    out_path = gt_dir / f"{stem}_cer_difference.md"

    if not ts_path.exists():
        print(f"ERROR: GT file not found: {ts_path}")
        return

    ts_text = extract_text(ts_path)
    am_text = extract_text(am_path)

    cer_val = _cer(reference=ts_text, hypothesis=am_text) * 100
    result  = _classify_errors(reference=ts_text, hypothesis=am_text)
    key_cer = result['weighted_cer'] * 100
    ref_len = len(_normalize_for_cer(ts_text))
    errors  = _get_key_error_details(reference=ts_text, hypothesis=am_text, context_chars=20)

    lines = [
        f"# CER Difference — {stem}",
        "",
        f"**Reference**: `GroundTrue/{stem}_GT.srt` (Primary GT)",
        f"**Hypothesis**: `{am_path.relative_to(Path('.'))}` (AlphaMemo, cross-check)",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ref chars (GT normalized) | {ref_len} |",
        f"| hyp chars (AM normalized) | {len(_normalize_for_cer(am_text))} |",
        f"| sub | {result['sub']} |",
        f"| ins | {result['ins']} |",
        f"| del | {result['del']} |",
        f"| key_sub | {result['key_sub']} |",
        f"| key_ins | {result['key_ins']} |",
        f"| key_del | {result['key_del']} |",
        f"| **CER** | **{cer_val:.2f}%** |",
        f"| **key_CER** | **{key_cer:.2f}%** |",
        "",
        f"> Note: high key_del ({result['key_del']}) reflects AlphaMemo's summarization tendency, not Ground Truth errors.",
        "",
        "## Key Error Detail",
        "",
        f"Total key errors: {len(errors)}",
        "",
        "| # | Type | GT (ref) | AM (hyp) | Context |",
        "|---|------|----------|----------|---------|",
    ]
    for i, e in enumerate(errors, 1):
        ref_disp = f"`{e['ref']}`" if e["ref"] else "—"
        hyp_disp = f"`{e['hyp']}`" if e["hyp"] else "—"
        ctx = f"{e['ctx_before']}**[{e['ref'] or '∅'}→{e['hyp'] or '∅'}]**{e['ctx_after']}"
        lines.append(f"| {i} | {e['op']}×{e['n']} | {ref_disp} | {hyp_disp} | {ctx} |")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written {out_path}  ({len(errors)} key errors, key_CER={key_cer:.2f}%)")

if __name__ == "__main__":
    for stem in sys.argv[1:]:
        gen_cer_difference(stem)
