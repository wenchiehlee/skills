"""
diff_char.py — Character-level diff between GT (SRT) and a pipeline stage.

Usage:
    python diff_char.py 2357_2025_q4_stage2 mlx-exp1-exp2-exp3-exp4-exp6-final
    python diff_char.py 2357_2025_q4_stage2 codex --sandbox whisper-sandbox

Output: full-text char diff with per-error context, matching exactly what key_CER measures.
"""
from __future__ import annotations
import argparse
import difflib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Trivial fillers (same as verify_cer.py) ───────────────────────────────────
_TRIVIAL_FILLERS: frozenset[str] = frozenset({
    "的", "那", "了", "在", "個", "好", "嘛", "呢", "哦", "嗯", "啊",
    "也", "都", "吧", "吶", "囉", "唷", "喔",
    "這個", "那個", "就是", "就是說", "的話", "的一個", "的1個",
    "然後", "那個", "好的", "好了", "嗯嗯",
})

def _is_trivial(seg: str) -> bool:
    return seg.strip() in _TRIVIAL_FILLERS or seg.strip() == ""


# ── Normalisation (same as verify_cer.py) ────────────────────────────────────
def _normalize(text: str) -> str:
    text = "".join(text.split())
    text = text.lower()
    text = re.sub(r'[\u3000-\u303f\uff00-\uffef,.!?;:\'"()\[\]{}\-/\\，。！？；：""''（）【】、]', '', text)
    text = text.translate(str.maketrans('儘裏噁麼', '盡裡惡麽'))
    text = text.translate(str.maketrans('一二三四五六七八九零', '1234567890'))
    return text


# ── Parsers ───────────────────────────────────────────────────────────────────
def parse_srt(path: Path) -> tuple[str, list[tuple[int, int]]]:
    """Return (full_normalized_text, [(char_offset, sec), ...]) for timestamp lookup.
    Supports both old (MM:SS) and new Metadata Style srt.
    """
    lines = []
    ts_offsets = []  # (char_pos_in_normalized, sec)
    content = path.read_text(encoding="utf-8")
    
    if content.startswith("[METADATA]"):
        parts = content.split("---", 1)
        if len(parts) > 1:
            content = parts[1]

    for line in content.splitlines():
        # New format (MM:SS)
        m = re.match(r'^\((\d+):(\d{2})\)\s+(.*)', line.strip())
        if m:
            t = int(m.group(1)) * 60 + int(m.group(2))
            raw = m.group(3).strip()
            ts_offsets.append((sum(len(_normalize(l[1])) for l in lines), t))
            lines.append((t, raw))
            continue
            
        # Legacy format **[MM:SS -> MM:SS]** or [MM:SS]
        m = re.match(r'^\*?\*?\[(\d+):(\d{2})\s*[→>\-]*\s*(\d*:?\d*)\]\*?\*?\s+(.*)', line.strip())
        if m:
            t = int(m.group(1)) * 60 + int(m.group(2))
            raw = m.group(4).strip()
            ts_offsets.append((sum(len(_normalize(l[1])) for l in lines), t))
            lines.append((t, raw))
            
    full_norm = "".join(_normalize(text) for _, text in lines)
    return full_norm, ts_offsets


def _lookup_ts(ts_offsets: list[tuple[int, int]], char_pos: int) -> int:
    """Return the timestamp (seconds) for the given char position."""
    ts = 0
    for offset, sec in ts_offsets:
        if offset <= char_pos:
            ts = sec
        else:
            break
    return ts


def _fmt_sec(sec: int) -> str:
    return f"{sec // 60}:{sec % 60:02d}"


# ── Main diff ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stem", help="e.g. 2357_2025_q4_stage2")
    parser.add_argument("stage", help="stage name, e.g. mlx-exp1-exp2-exp3-exp4-exp6-final")
    parser.add_argument("--sandbox", default="Whisper-API-Server/whisper-sandbox")
    parser.add_argument("--context", type=int, default=12,
                        help="chars of context before/after diff")
    args = parser.parse_args()

    sandbox = Path(args.sandbox)
    # GT is always _GT.srt (renamed from _turboscribe.srt)
    gt_path = Path("Mac-mini/Whisper-API-Server/GroundTrue") / f"{args.stem}_GT.srt"
    if not gt_path.exists():
        # Fallback to sandbox if not in GroundTrue/
        gt_path = sandbox / f"{args.stem}_GT.srt"
        
    hyp_path = sandbox / f"{args.stem}_{args.stage}.srt"

    if not gt_path.exists():
        print(f"ERROR: GT file not found: {gt_path}")
        sys.exit(1)
    if not hyp_path.exists():
        # Try without the underscore if stage is empty (though unlikely from usage)
        alt_path = sandbox / f"{args.stem}.srt" if not args.stage else None
        if alt_path and alt_path.exists():
            hyp_path = alt_path
        else:
            print(f"ERROR: Hyp file not found: {hyp_path}")
            sys.exit(1)

    print(f"Ref: {gt_path}")
    print(f"Hyp: {hyp_path}\n")

    ref_norm, ref_ts = parse_srt(gt_path)
    hyp_norm, hyp_ts = parse_srt(hyp_path)

    matcher = difflib.SequenceMatcher(None, list(ref_norm), list(hyp_norm))
    
    # Header
    print(f"{'#':>3} | {'Time':>6} | {'Type':>7} | {'Diff [GT -> Hyp]':<20} | Context")
    print("-" * 80)

    err_count = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
            
        ref_seg = ref_norm[i1:i2]
        hyp_seg = hyp_norm[j1:j2]
        
        # Key CER filter
        if op == "replace":
            is_key = not (_is_trivial(ref_seg) and _is_trivial(hyp_seg))
        elif op == "insert":
            is_key = not _is_trivial(hyp_seg)
        else: # delete
            is_key = not _is_trivial(ref_seg)
            
        if not is_key:
            continue
            
        err_count += 1
        t_sec = _lookup_ts(ref_ts, i1)
        t_str = _fmt_sec(t_sec)
        
        ctx_b = ref_norm[max(0, i1 - args.context):i1]
        ctx_a = ref_norm[i2:min(len(ref_norm), i2 + args.context)]
        
        diff_str = f"{ref_seg or '∅'} -> {hyp_seg or '∅'}"
        context_str = f"{ctx_b}[{ref_seg or '∅'} -> {hyp_seg or '∅'}]{ctx_a}"
        
        print(f"{err_count:3d} | {t_str:>6} | {op:7} | {diff_str:<20} | {context_str}")

    print(f"\nTotal key errors: {err_count}")

if __name__ == "__main__":
    main()
