"""
merge_transcripts.py — Multi-pass transcript merger + domain correction

Pipeline:
  Pass 1  Parse all 3 exp srt files into (start, end, text) tuples
  Pass 2  Align overlapping segments by timestamp window -> pick best
  Pass 3  Domain corrections (names, technical terms, prompt leakage)
  Pass 4  Smoothness — merge consecutive micro-fragments into sentences
  Pass 5  Write final srt

Usage:
  python mlx-api-server-whisper/merge_transcripts.py \\
      --sandbox mlx-api-server-whisper/whisper-sandbox \\
      --stem 2357_2025_q4 \\
      --output mlx-api-server-whisper/whisper-sandbox/2357_2025_q4_final.srt
"""

import re
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

# ── Domain correction table ───────────────────────────────────────────────────
# (pattern, replacement)  — applied in order, case-sensitive where needed
CORRECTIONS = [
    # ── Executive names ──────────────────────────────────────────────────────
    (r'許仙月', '許先越'),
    (r'許憲越', '許先越'),
    (r'許憲月', '許先越'),
    (r'許先嶽', '許先越'),
    (r'先月(?=[先越跟]|$)', '先越'),
    (r'鬍樹斌', '胡書賓'),
    (r'胡樹斌', '胡書賓'),
    (r'鬍書賓', '胡書賓'),

    # ── Technical terms ───────────────────────────────────────────────────────
    (r'248STOPS', '48 TOPS'),
    (r'24BusTops', '48 TOPS'),
    (r'TUFO Bus Tops', '48 TOPS'),
    (r'BusTops', 'TOPS'),
    (r'Bus Tops', 'TOPS'),
    (r'STOPS', 'TOPS'),
    (r'TerraFlap', 'Teraflops'),
    (r'Terraflop', 'Teraflops'),
    (r'Marty Eel的MOU', 'MOU'),

    # ── Financial terms ──────────────────────────────────────────────────────
    (r'銀售', '營收'),
    (r'銀業利益', '營業利益'),
    (r'銀業外', '營業外'),
    (r'美股盈餘', '每股盈餘'),

    # ── Prompt leakage ────────────────────────────────────────────────────────
    (r'。?\s*請使用繁體字轉錄。?', ''),
    (r'以下是華碩電腦法人說明會的繁體中文逐字稿。?', ''),
]

HALLUCINATION_PATTERNS = [
    r'請使用繁體字轉錄',
    r'以下是華碩電腦法人說明會',
    r'ר',
    r'(.{6,})\1{3,}',
]

# ── Parser ────────────────────────────────────────────────────────────────────

def parse_srt(path: Path) -> list:
    """Return list of (start_s, end_s, text) from a whisper_exp srt file."""
    segs = []
    content = path.read_text(encoding='utf-8')
    
    # Skip Metadata block
    if content.startswith("[METADATA]"):
        parts = content.split("---", 1)
        if len(parts) > 1:
            content = parts[1]

    # Support (MM:SS) and legacy [MM:SS -> MM:SS]
    pat_new = re.compile(r'^\((\d+):(\d+)\)\s*(.*)')
    pat_legacy = re.compile(r'^\*\*\[(\d+):(\d+) \u2192 (\d+):(\d+)\]\*\*\s*(.*)')
    
    for line in content.splitlines():
        line = line.strip()
        m = pat_new.match(line)
        if m:
            ms, ss, text = m.groups()
            start = int(ms)*60 + int(ss)
            text = text.strip()
            if text:
                segs.append((start, start + 2.0, text))
            continue
            
        m = pat_legacy.match(line)
        if m:
            ms, ss, me, se, text = m.groups()
            start = int(ms)*60 + int(ss)
            end   = int(me)*60 + int(se)
            text  = text.strip()
            if text:
                segs.append((start, end, text))
                
    return segs


# ── Segment quality scorer ────────────────────────────────────────────────────

def is_hallucinated(text: str) -> bool:
    for pat in HALLUCINATION_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def score(text: str) -> float:
    if is_hallucinated(text):
        return -999.0
    if not text:
        return 0.0
    base = len(text)
    words = text.split()
    rep_penalty = 0
    if len(words) >= 4:
        most = max(words.count(w) for w in set(words))
        rep_ratio = most / len(words)
        if rep_ratio > 0.4:
            rep_penalty = base * rep_ratio
    punct_bonus = 2 if text[-1] in '。！？，、' else 0
    return base - rep_penalty + punct_bonus


# ── Pass 2: Timestamp alignment + best-pick ───────────────────────────────────

def merge_segments(all_segs: list, window: float = 2.0) -> list:
    if not all_segs: return []
    all_segs = sorted(all_segs, key=lambda x: x[0])
    groups  = []
    current = [all_segs[0]]
    for seg in all_segs[1:]:
        start = seg[0]
        if start - current[0][0] <= window:
            current.append(seg)
        else:
            groups.append(current)
            current = [seg]
    if current:
        groups.append(current)
    merged = []
    for grp in groups:
        best = max(grp, key=lambda x: score(x[2]))
        if score(best[2]) < 0: continue
        merged.append((best[0], best[1], best[2]))
    deduped = []
    for seg in merged:
        if deduped and seg[0] < deduped[-1][1]:
            if score(seg[2]) > score(deduped[-1][2]):
                deduped[-1] = seg
        else:
            deduped.append(seg)
    return deduped


def apply_corrections(text: str) -> str:
    for pattern, replacement in CORRECTIONS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def smooth(segs: list, gap_threshold: float = 1.5, max_chars: int = 60) -> list:
    if not segs: return segs
    result  = [list(segs[0])]
    for s, e, t in segs[1:]:
        prev = result[-1]
        gap  = s - prev[1]
        combined_len = len(prev[2]) + len(t)
        prev_ends_open = prev[2] and prev[2][-1] not in '。！？'
        already_contains = t in prev[2] or prev[2] in t
        if gap <= gap_threshold and combined_len <= max_chars and prev_ends_open and not already_contains:
            prev[1]  = e
            prev[2] += t
        else:
            result.append([s, e, t])
    return [tuple(r) for r in result]


# ── Pass 5: Write final srt ───────────────────────────────────────────────────

def write_srt(segs: list, out_path: Path, stem: str, source_note: str):
    total_secs = segs[-1][1] if segs else 0
    header = (
        f"[METADATA]\n"
        f"Source: {stem}.m4a\n"
        f"Method: Merged via merge_transcripts.py\n"
        f"Note: {source_note}\n"
        f"Generated-At: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M CST')}\n"
        f"---\n\n"
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(header)
        prev_text = None
        for start, end, text in segs:
            text = apply_corrections(text)
            if not text or text == prev_text: continue
            if is_hallucinated(text): continue
            mm = int(start // 60)
            ss = int(start % 60)
            ms = int(round((start % 1) * 1000))
            f.write(f"({mm:02d}:{ss:02d}.{ms:03d}) {text}\n")
            prev_text = text
    print(f"[out] Final transcript -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sandbox', default='mlx-api-server-whisper/whisper-sandbox')
    parser.add_argument('--stem',    default='2357_2025_q4')
    parser.add_argument('--output',  default=None)
    parser.add_argument('--window',  type=float, default=2.0)
    parser.add_argument('--gap',     type=float, default=1.5)
    args = parser.parse_args()

    sandbox = Path(args.sandbox)
    stem    = args.stem
    out     = Path(args.output) if args.output else sandbox / f"{stem}_final.srt"

    sources = {
        'exp1': sandbox / f"{stem}_exp1.srt",
        'exp2': sandbox / f"{stem}_exp2.srt",
        'exp3': sandbox / f"{stem}_exp3.srt",
    }

    all_segs = []
    counts   = {}
    for label, path in sources.items():
        if not path.exists(): continue
        segs = parse_srt(path)
        counts[label] = len(segs)
        for s, e, t in segs:
            all_segs.append((s, e, t, label))
        print(f"[parse] {label}: {len(segs)} segments")

    merged = merge_segments(all_segs, window=args.window)
    corrected = [(s, e, apply_corrections(t)) for s, e, t in merged]
    corrected = [(s, e, t) for s, e, t in corrected if t and not is_hallucinated(t)]
    smoothed = smooth(corrected, gap_threshold=args.gap)

    write_srt(smoothed, out, stem, "Names/Terms/Prompt corrections applied")

if __name__ == '__main__':
    main()
