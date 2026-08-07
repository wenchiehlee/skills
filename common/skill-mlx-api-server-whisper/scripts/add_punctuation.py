"""
add_punctuation.py — LLM-based punctuation restoration for Whisper transcripts

Uses ../llm (LLMClient) with Codex-API-Server -> Gemini fallback.

Usage:
  pip install "llm @ git+https://github.com/wenchiehlee/llm.git"
  export CODEX_API_URL=https://...
  export CODEX_API_KEY=...
  python Whisper-API-Server/add_punctuation.py \\
      --input  Whisper-API-Server/whisper-sandbox/2357_2025_q4_final.md \\
      --output Whisper-API-Server/whisper-sandbox/2357_2025_q4_punct.md
"""

import re
import sys
import time
import argparse
from pathlib import Path

try:
    from llm import LLMClient
except ImportError:
    print('ERROR: pip install "llm @ git+https://github.com/wenchiehlee/llm.git"')
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_SEGS  = 15    # segments per API call
RETRY_MAX   = 3
RETRY_DELAY = 5

PROMPT_TEMPLATE = """你是台灣上市公司法人說明會的逐字稿標點符號編輯。

規則：
1. 只加入標點符號，絕對不修改、刪除、增加任何文字
2. 使用繁體中文標點：，。！？、；：「」
3. 英文/數字維持原樣（如 AI Server、ROG、48 TOPS、445.6億、4.9%）
4. 每個 segment 獨立一行，行數必須與輸入完全相同
5. 口語停頓用，　句子結束用。　疑問用？　強調用！
6. 直接輸出結果，不要加任何說明或編號

請為以下逐字稿加上標點（共 {n} 行，輸出也必須是 {n} 行）：

{text}"""


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_md(path: Path):
    """Return (header_lines, segments) where segments = [(ts_tag, text), ...]"""
    lines    = path.read_text(encoding='utf-8').splitlines()
    header   = []
    segments = []
    pat      = re.compile(r'^(\*\*\[\d+:\d+ -> \d+:\d+\]\*\*)\s+(.*)')
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
            segments.append((m.group(1), m.group(2).strip()))
        elif line.strip() == '':
            pass
        else:
            segments.append(('', line))

    return header, segments


# ── LLM call ─────────────────────────────────────────────────────────────────

def add_punctuation_chunk(client: LLMClient, texts: list) -> list:
    """Send plain texts, get back punctuated versions (same count)."""
    joined = '\n'.join(texts)
    prompt = PROMPT_TEMPLATE.format(n=len(texts), text=joined)

    for attempt in range(RETRY_MAX):
        try:
            raw = client.generate(prompt).strip()
            break
        except Exception as e:
            if attempt < RETRY_MAX - 1:
                print(f"  [retry {attempt+1}] {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [fail] {e} -- returning originals")
                return texts

    result = [line.strip() for line in raw.splitlines() if line.strip()]

    if len(result) != len(texts):
        print(f"  [warn] got {len(result)} lines, expected {len(texts)} -- using originals")
        return texts

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',    required=True)
    parser.add_argument('--output',   default=None)
    parser.add_argument('--chunk',    type=int, default=CHUNK_SEGS)
    parser.add_argument('--provider', default=None,
                        help='Force provider: codex or gemini (default: auto)')
    args = parser.parse_args()

    in_path  = Path(args.input)
    out_path = Path(args.output) if args.output else \
               in_path.with_name(in_path.stem + '_punct.md')

    # LLMClient auto-detects codex -> gemini from env vars
    kwargs = {'app_name': 'whisper-punctuation'}
    if args.provider:
        kwargs['providers'] = [args.provider]
    client = LLMClient(**kwargs)
    print(f"[llm]   provider={args.provider or 'auto (codex->gemini)'}")

    print(f"[read]  {in_path}")
    header, segments = parse_md(in_path)

    to_process = [(i, ts, txt) for i, (ts, txt) in enumerate(segments) if ts and txt]
    total      = len(to_process)
    print(f"[segs]  {total} segments  |  chunk={args.chunk}\n")

    result_texts = {idx: txt for idx, ts, txt in to_process}

    chunks = [to_process[i:i+args.chunk] for i in range(0, total, args.chunk)]
    done   = 0
    for chunk in chunks:
        texts   = [txt for _, _, txt in chunk]
        indices = [idx for idx, _, _ in chunk]
        pct     = done / total * 100
        print(f"  [{pct:5.1f}%] segs {done+1}-{done+len(chunk)}/{total} ...",
              end=' ', flush=True)

        punctuated = add_punctuation_chunk(client, texts)

        for idx, new_txt in zip(indices, punctuated):
            result_texts[idx] = new_txt
        done += len(chunk)
        print("done")
        time.sleep(0.2)

    # Write output
    with open(out_path, 'w', encoding='utf-8') as f:
        for line in header:
            f.write(line + '\n')
        f.write('\n')
        for i, (ts, _) in enumerate(segments):
            txt = result_texts.get(i, '')
            if ts and txt:
                f.write(f"{ts} {txt}\n\n")

    print(f"\n[out]  -> {out_path}  ({total} segments)")


if __name__ == '__main__':
    main()
