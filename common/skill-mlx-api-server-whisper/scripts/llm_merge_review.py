"""
llm_merge_review.py — LLM-based smart merge + punctuation + review from Whisper experiments

Single-exp mode (recommended):  only exp1 needed — LLM adds punctuation + fixes terminology
Multi-exp mode:                  exp1+exp2+exp3 — LLM selects best version across 3 runs

Usage:
  export CODEX_API_URL=http://127.0.0.1:5001
  export CODEX_API_KEY=...

  # Single-exp (fast, exp1 only):
  python Whisper-API-Server/llm_merge_review.py --stem 2357_2025_q4 --single

  # Multi-exp (3 experiments):
  python Whisper-API-Server/llm_merge_review.py --stem 2357_2025_q4
"""

import re
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

try:
    from llm import LLMClient
except ImportError:
    print('ERROR: pip install "llm @ git+https://github.com/wenchiehlee/llm.git"')
    sys.exit(1)

# ── Config ─────────────────────────────────────────────────────────────────────
WINDOW_SEC  = 120   # 2-minute chunks per LLM call
OVERLAP_SEC = 10    # overlap to avoid boundary cuts
RETRY_MAX   = 3
RETRY_DELAY = 5

# ── Shared terminology correction rules (used in both prompts) ────────────────
TERM_RULES = """\
術語修正表（錯誤 → 正確）：
- 領主件 → 零組件
- 系統VG → 系統BG
- 領土建世界群 → 基礎設施事業群
- 基礎設施事業權 → 基礎設施事業群
- 共同指定長 → 共同執行長
- 商用PCE → 商用PC
- 廉政率 → 年增率（財務脈絡）
- 臺灣所創 → 臺灣首創
- 車類夥伴 → 策略夥伴（供應鏈/GPU合作夥伴脈絡）
- hypnose computing → hyperscale computing
- 上源到Clown / 上傳到Clown → 上傳到Cloud
- DeepSeq → DeepSeek
- Total Temp → Total TAM
- PG市場 → PC市場
- 年兌年 → 年對年
- 年份錯誤：2060年 → 2026年、20年底 → 2027年底、2020年第一季 → 2026年第一季"""

OUTPUT_RULES = """\
輸出規則：
- 每行格式：**[MM:SS -> MM:SS]** 文字內容
- 時間戳使用 `->` (非 `→`)，分秒格式各兩位數（如 **[06:28 -> 06:31]**）
- 只輸出轉錄內容行，不加說明、標題、空白行、編號
- 英文/數字保持原樣（AI Server、ROG、TOPS、GPU、EPS、Q4 等）
- 時間戳保持與輸入一致，不要發明新的時間段"""

# Single-exp prompt: punctuation + terminology correction only
PROMPT_SINGLE = """\
你是台灣上市公司法人說明會的專業逐字稿編輯。

以下是音頻（約 {start} 到 {end}）的 AI 語音辨識逐字稿。

請完成以下工作：
1. **加入標點符號**：使用繁體中文標點（，。！？、；：「」）
2. **修正語音辨識錯誤**：依下方術語表修正，只修正明確錯誤，不修改正確內容

{term_rules}

{output_rules}

=== 逐字稿 ===
{exp1_text}

請輸出修正後的版本（只有 **[MM:SS -> MM:SS]** 格式的行）："""

# Multi-exp prompt: select best version + punctuation + terminology correction
PROMPT_MULTI = """\
你是台灣上市公司法人說明會的專業逐字稿編輯。

以下是同一段音頻（約 {start} 到 {end}）的三個不同 AI 語音辨識版本（Exp1 / Exp2 / Exp3）。

請完成以下工作：
1. **選擇最準確的版本**：對每個時間段選擇語意最完整、錯誤最少的版本（可融合多版本優點）
2. **加入標點符號**：使用繁體中文標點（，。！？、；：「」）
3. **修正語音辨識錯誤**：依下方術語表修正

{term_rules}

{output_rules}

=== Exp1（StrongFilter / mlx-whisper）===
{exp1_text}

=== Exp2（Chunked / mlx-whisper）===
{exp2_text}

=== Exp3（faster-whisper + VAD）===
{exp3_text}

請輸出合併後的最終版本（只有 **[MM:SS -> MM:SS]** 格式的行）："""


# ── Parse ─────────────────────────────────────────────────────────────────────

def parse_exp(path: Path):
    """Return (header_lines, segments) where segments = [(start_sec, end_sec, text)]"""
    lines    = path.read_text(encoding='utf-8').splitlines()
    # Match both → and -> in timestamps
    pat      = re.compile(r'^\*\*\[(\d+):(\d+)\s*(?:→|->)\s*(\d+):(\d+)\]\*\*\s*(.*)')
    header   = []
    segments = []
    in_body  = False

    for line in lines:
        if line.startswith('---') and not in_body:
            in_body = True
            header.append(line)
            continue
        if not in_body:
            header.append(line)
            continue
        m = pat.match(line)
        if m:
            sm, ss = int(m.group(1)), int(m.group(2))
            em, es = int(m.group(3)), int(m.group(4))
            text   = m.group(5).strip()
            if text:
                segments.append((sm * 60 + ss, em * 60 + es, text))

    return header, segments


def segs_in_window(segments, start_sec, end_sec):
    """Return segments whose start falls within [start_sec, end_sec)."""
    return [(s, e, t) for s, e, t in segments if start_sec <= s < end_sec]


def fmt_seg(s, e, t):
    return f"**[{s//60:02d}:{s%60:02d} -> {e//60:02d}:{e%60:02d}]** {t}"


def fmt_time(sec):
    return f"{sec//60:02d}:{sec%60:02d}"


# ── LLM call ──────────────────────────────────────────────────────────────────

SEG_PAT = re.compile(r'^\*\*\[(\d+):(\d+)\s*->\s*(\d+):(\d+)\]\*\*\s*(.*)')


def call_llm(client: LLMClient, exp1_segs, exp2_segs, exp3_segs,
             win_start: int, win_end: int, single: bool = False) -> list:
    """
    Send segments to LLM; return list of (start_sec, end_sec, text).
    single=True: punctuation+correction only (exp1 only).
    single=False: 3-exp merge + punctuation + correction.
    Falls back to exp1 raw segments on any failure.
    """
    def fmt_block(segs):
        if not segs:
            return "（此時間段無內容）"
        return "\n".join(fmt_seg(s, e, t) for s, e, t in segs)

    if single:
        prompt = PROMPT_SINGLE.format(
            start=fmt_time(win_start),
            end=fmt_time(win_end),
            term_rules=TERM_RULES,
            output_rules=OUTPUT_RULES,
            exp1_text=fmt_block(exp1_segs),
        )
    else:
        prompt = PROMPT_MULTI.format(
            start=fmt_time(win_start),
            end=fmt_time(win_end),
            term_rules=TERM_RULES,
            output_rules=OUTPUT_RULES,
            exp1_text=fmt_block(exp1_segs),
            exp2_text=fmt_block(exp2_segs),
            exp3_text=fmt_block(exp3_segs),
        )

    for attempt in range(RETRY_MAX):
        try:
            raw = client.generate(prompt).strip()
            break
        except Exception as e:
            if attempt < RETRY_MAX - 1:
                print(f"  [retry {attempt+1}] {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [fail] {e} -- using exp1 fallback")
                return [(s, e, t) for s, e, t in exp1_segs]

    # Parse LLM output
    result = []
    for line in raw.splitlines():
        m = SEG_PAT.match(line.strip())
        if m:
            sm, ss = int(m.group(1)), int(m.group(2))
            em, es = int(m.group(3)), int(m.group(4))
            text   = m.group(5).strip()
            if text:
                result.append((sm * 60 + ss, em * 60 + es, text))

    if not result:
        print(f"  [warn] LLM returned no valid segments for {fmt_time(win_start)}-{fmt_time(win_end)} -- using exp1")
        return [(s, e, t) for s, e, t in exp1_segs]

    return result


# ── Dedup / stitch ─────────────────────────────────────────────────────────────

def dedup_segments(all_segs: list) -> list:
    """
    Remove duplicates arising from window overlap.
    Two segments are considered duplicates if they share the same start time;
    keep the longer text (more complete version).
    """
    # Group by start time, keep longest text
    best: dict[int, tuple] = {}
    for s, e, t in all_segs:
        if s not in best or len(t) > len(best[s][2]):
            best[s] = (s, e, t)
    return [best[s] for s in sorted(best)]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    sandbox = Path("Whisper-API-Server/whisper-sandbox")
    parser.add_argument('--stem',   default=None,
                        help='File stem (e.g. 2357_2025_q4); auto-builds paths')
    parser.add_argument('--exp1',   default=None)
    parser.add_argument('--exp2',   default=None)
    parser.add_argument('--exp3',   default=None)
    parser.add_argument('--output', default=None)
    parser.add_argument('--single', action='store_true',
                        help='Single-exp mode: use exp1 only (no exp2/exp3 needed)')
    parser.add_argument('--window', type=int, default=WINDOW_SEC,
                        help='Seconds per LLM window (default 120)')
    parser.add_argument('--overlap', type=int, default=OVERLAP_SEC)
    parser.add_argument('--provider', default=None,
                        help='Force provider: codex or gemini (default: auto)')
    args = parser.parse_args()

    if args.stem:
        base      = sandbox / args.stem
        exp1_path = Path(str(base) + '_exp1.md')
        exp2_path = Path(str(base) + '_exp2.md') if not args.single else None
        exp3_path = Path(str(base) + '_exp3.md') if not args.single else None
        out_path  = Path(str(base) + '_punct.md')
    else:
        if not args.exp1:
            parser.error("Provide --stem or --exp1")
        exp1_path = Path(args.exp1)
        exp2_path = Path(args.exp2) if args.exp2 else None
        exp3_path = Path(args.exp3) if args.exp3 else None
        out_path  = Path(args.output) if args.output else \
                    exp1_path.with_name(exp1_path.stem.replace('_exp1', '_punct') + '.md')

    if args.output:
        out_path = Path(args.output)

    # Determine mode
    single = args.single or (exp2_path is None and exp3_path is None)
    mode   = "single-exp (punct+review)" if single else "multi-exp (merge+punct+review)"

    # LLM client
    kwargs = {'app_name': 'whisper-merge-fix'}
    if args.provider:
        kwargs['providers'] = [args.provider]
    client = LLMClient(**kwargs)
    print(f"[llm]    provider={args.provider or 'auto (codex->gemini)'}  mode={mode}")

    # Parse
    print(f"[read]   {exp1_path.name}")
    hdr1, segs1 = parse_exp(exp1_path)
    segs2, segs3 = [], []
    if not single:
        print(f"[read]   {exp2_path.name}")
        _, segs2 = parse_exp(exp2_path)
        print(f"[read]   {exp3_path.name}")
        _, segs3 = parse_exp(exp3_path)
        print(f"[segs]   exp1={len(segs1)}  exp2={len(segs2)}  exp3={len(segs3)}")
    else:
        print(f"[segs]   exp1={len(segs1)}")

    max_sec = max(
        segs1[-1][1] if segs1 else 0,
        segs2[-1][1] if segs2 else 0,
        segs3[-1][1] if segs3 else 0,
    )
    print(f"[dur]    {fmt_time(max_sec)}  window={args.window}s  overlap={args.overlap}s\n")

    # Process windows
    all_output = []
    win  = args.window
    ovl  = args.overlap
    step = win - ovl

    for w_start in range(0, max_sec + win, step):
        w_end = w_start + win
        pct   = w_start / max_sec * 100 if max_sec else 0

        s1 = segs_in_window(segs1, w_start, w_end)
        s2 = segs_in_window(segs2, w_start, w_end)
        s3 = segs_in_window(segs3, w_start, w_end)

        if not (s1 or s2 or s3):
            continue

        if single:
            print(f"  [{pct:5.1f}%] {fmt_time(w_start)}-{fmt_time(w_end)}"
                  f"  segs={len(s1)} ...", end=' ', flush=True)
        else:
            print(f"  [{pct:5.1f}%] {fmt_time(w_start)}-{fmt_time(w_end)}"
                  f"  e1={len(s1)} e2={len(s2)} e3={len(s3)} ...", end=' ', flush=True)

        merged = call_llm(client, s1, s2, s3, w_start, w_end, single=single)
        all_output.extend(merged)
        print(f"-> {len(merged)} segs")
        time.sleep(0.3)

    # Dedup from window overlap
    final_segs = dedup_segments(all_output)
    print(f"\n[dedup]  {len(all_output)} raw -> {len(final_segs)} unique segments")

    # Write output
    now        = datetime.now().strftime('%Y-%m-%d')
    proc_label = "LLM punct+review (exp1)" if single else "LLM merge+punct+review (exp1+2+3)"
    with open(out_path, 'w', encoding='utf-8') as f:
        for line in hdr1:
            if line.startswith('# Transcript:'):
                f.write(f"# Transcript: {exp1_path.name.replace('_exp1','')}"
                        f"  [FINAL — LLM Reviewed]\n")
            elif '**Experiment**' in line:
                f.write(f"| **Process** | {proc_label} |\n")
            elif '**Segments**' in line:
                f.write(f"| **Segments** | {len(final_segs)} |\n")
            elif '**Reviewed**' in line:
                pass
            else:
                f.write(line + '\n')
        f.write(f"| **Reviewed** | LLMClient (Codex/Gemini) — {now} |\n")
        f.write('\n')

        for s, e, t in final_segs:
            f.write(fmt_seg(s, e, t) + '\n\n')

    print(f"[out]    -> {out_path}  ({len(final_segs)} segments)")


if __name__ == '__main__':
    main()
