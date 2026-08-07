"""
probe_mlx_truncation.py
=======================
Probe script to investigate Qwen2.5-14B truncation behaviour.

For each test case (a real truncated example from stage2), we run the
same merge task under different parameter / prompt style combinations
and report whether the model outputs the full text or truncates.

Usage (on Mac mini):
    python mlx-api-server-whisper/probe_mlx_truncation.py

Output: a table showing which combos produce full output vs truncation.
"""

import sys
import time
import textwrap

# ── Real truncation examples from stage2 diff (Gemini=correct, MLX=truncated) ─
CASES = [
    {
        "id": "case1_ai_demand",
        "ts": "[05:38 → 05:41]",
        "versions": {
            "Exp1": "雖然說現在大家看到整個AI的需求非常的強勁",
            "Exp2": "雖然說現在大家看到整個AI需求非常強勁",
            "Exp3": "雖然說現在大家看到整個AI的需求非常的強勁",
        },
        "expected": "雖然說現在大家看到整個AI的需求非常的強勁",
        "mlx_was":  "雖然說現在大家看到",
    },
    {
        "id": "case2_server_q3",
        "ts": "[12:22 → 12:26]",
        "versions": {
            "Exp1": "Server在第三季跟第四季其實營收佔比都已經超過20%了",
            "Exp2": "server在第三季跟第四季其實營收佔比都已超過20%了",
            "Exp3": "Server在第三季跟第四季其實營收占比都已經超過20%了",
        },
        "expected": "Server在第三季跟第四季其實營收佔比都已經超過20%了",
        "mlx_was":  "Server在第三季跟第四季",
    },
    {
        "id": "case3_follow_pattern",
        "ts": "[05:14 → 05:17]",
        "versions": {
            "Exp1": "其實目前我們除了follow過去的pattern",
            "Exp2": "其實目前我們除了follow過去的pattern",
            "Exp3": "其實目前我們除了follow過去的pattern",
        },
        "expected": "其實目前我們除了follow過去的pattern",
        "mlx_was":  "其實目前我們除了跟隨過去的模式",  # translation, not truncation
    },
    {
        "id": "case4_stone_advantage",
        "ts": "[00:35 → 00:41]",
        "versions": {
            "Exp1": "還有板卡的巨石地位 在市場上取得絕對的優勢",
            "Exp2": "還有板卡的巨石地位在市場上取得絕對的優勢",
            "Exp3": "還有板卡的市場地位 在市場上取得絕對的優勢",
        },
        "expected": "還有板卡的巨石地位 在市場上取得絕對的優勢",
        "mlx_was":  "還有板卡的巨石地位",
    },
]

# ── Parameter grid ─────────────────────────────────────────────────────────────
TEMPS   = [0.0, 0.1, 0.3]
REP_PEN = [1.0, 1.05, 1.1, 1.2]

# ── Prompt style builders ──────────────────────────────────────────────────────

def prompt_current(case: dict) -> str:
    """Replicates the current production prompt style."""
    versions_block = "\n".join(
        f"【{label}】\n{case['ts']} {text}"
        for label, text in case["versions"].items()
    )
    return textwrap.dedent(f"""\
        你是台灣上市公司法人說明會的專業逐字稿編輯。
        以下是同一小段音頻的 {len(case['versions'])} 個 AI 轉錄版本。
        請合併成一份逐字稿：對每個時間段選出最準確的版本。

        規則：
        1. 保留繁體中文，不轉換為簡體
        2. 輸出格式：每行 [MM:SS → MM:SS] 文字
        3. 只輸出逐字稿，不要任何說明
        4. 【嚴格禁止】不得截斷句子——每個時間段的文字必須完整輸出
        5. 選擇各版本中文字最完整的版本，除非有明顯錯誤

        {versions_block}
    """)


def prompt_verbatim_pick(case: dict) -> str:
    """Ask model to pick ONE version verbatim, no rewriting."""
    versions_block = "\n".join(
        f"版本{i+1}（{label}）：{text}"
        for i, (label, text) in enumerate(case["versions"].items())
    )
    return textwrap.dedent(f"""\
        以下是同一時段 {case['ts']} 的 {len(case['versions'])} 個逐字稿版本。
        請選出文字最完整、最準確的版本，直接輸出該版本的原文（不得修改、不得縮短）。
        只輸出時間戳記加文字，格式：{case['ts']} 文字

        {versions_block}
    """)


def prompt_length_aware(case: dict) -> str:
    """Explicitly tell the model the expected character count range."""
    min_len = min(len(t) for t in case["versions"].values())
    max_len = max(len(t) for t in case["versions"].values())
    versions_block = "\n".join(
        f"【{label}】\n{case['ts']} {text}"
        for label, text in case["versions"].items()
    )
    return textwrap.dedent(f"""\
        你是台灣上市公司法人說明會的專業逐字稿編輯。
        以下是同一小段音頻的 {len(case['versions'])} 個 AI 轉錄版本。
        請選出最準確的版本。

        【重要】輸出文字長度必須在 {min_len}～{max_len} 字之間，不得截短。
        輸出格式：{case['ts']} 文字（只輸出一行，不要說明）

        {versions_block}
    """)


def prompt_fewshot(case: dict) -> str:
    """Few-shot example showing correct (full) vs wrong (truncated) output."""
    versions_block = "\n".join(
        f"【{label}】\n{case['ts']} {text}"
        for label, text in case["versions"].items()
    )
    return textwrap.dedent(f"""\
        你是台灣上市公司法人說明會的專業逐字稿編輯。
        對每個時間段選出最準確、最完整的版本並輸出。

        示範（正確）：
        輸入：
        【A】[00:10 → 00:15] 我們在AI伺服器這塊的競爭力非常強
        【B】[00:10 → 00:15] 我們在AI伺服器的競爭力非常強
        輸出：[00:10 → 00:15] 我們在AI伺服器這塊的競爭力非常強

        示範（錯誤，不可截斷）：
        ❌ 輸出：[00:10 → 00:15] 我們在AI伺服器

        示範（英文保留）：
        輸入：
        【A】[01:00 → 01:05] 除了follow過去的pattern我們也在觀察
        輸出：[01:00 → 01:05] 除了follow過去的pattern我們也在觀察
        ❌ 錯誤輸出：[01:00 → 01:05] 除了跟隨過去的模式我們也在觀察

        現在請處理：
        {versions_block}
        輸出：
    """)


PROMPT_STYLES = {
    "current":        prompt_current,
    "verbatim_pick":  prompt_verbatim_pick,
    "length_aware":   prompt_length_aware,
    "fewshot":        prompt_fewshot,
}

# ── Scoring ────────────────────────────────────────────────────────────────────

def score(output: str, case: dict) -> str:
    """
    Returns one of:
      FULL    — output contains expected text verbatim
      PARTIAL — output contains at least 85% of expected chars
      TRUNC   — output shorter than 85% of expected
      TRANSL  — English terms translated (case3 specific)
    """
    # strip leading timestamp if present
    text = output.strip()
    if text.startswith("["):
        idx = text.find("]")
        if idx != -1:
            text = text[idx+1:].strip()

    expected = case["expected"]

    if expected in text or text in expected and len(text) >= len(expected) * 0.95:
        return "FULL ✓"
    if len(text) >= len(expected) * 0.85:
        return "PARTIAL ~"
    # check for English-to-Chinese translation (case3)
    if "跟隨" in text or "模式" in text or "伺服器" in text:
        return "TRANSL ✗"
    return f"TRUNC ✗ ({len(text)}/{len(expected)})"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    try:
        from mlx_lm import load, generate
    except ImportError:
        print("ERROR: mlx-lm not installed. Run: pip install mlx-lm")
        sys.exit(1)

    model_path = "mlx-community/Qwen2.5-14B-Instruct-4bit"
    print(f"Loading model: {model_path} …")
    model, tokenizer = load(model_path)
    print("Model ready.\n")

    # ── Detect generate() parameter names for this mlx-lm version ────────────
    import inspect
    try:
        from mlx_lm.utils import generate_step
        sig_params = set(inspect.signature(generate_step).parameters.keys())
    except Exception:
        sig_params = set(inspect.signature(generate).parameters.keys())

    TEMP_KEY  = "temperature" if "temperature" in sig_params else (
                "temp"        if "temp"        in sig_params else None)
    REP_KEY   = "repetition_penalty" if "repetition_penalty" in sig_params else None

    print(f"  [api] generate_step params: {sorted(sig_params)}")
    print(f"  [api] temp key={TEMP_KEY!r}  rep_penalty key={REP_KEY!r}\n")

    # Results table: (case_id, style, temp, rep_pen) -> score
    results = []

    for case in CASES:
        print(f"\n{'='*70}")
        print(f"CASE: {case['id']}")
        print(f"  Expected : {case['expected']}")
        print(f"  MLX was  : {case['mlx_was']}")
        print(f"{'='*70}")

        for style_name, prompt_fn in PROMPT_STYLES.items():
            prompt_text = prompt_fn(case)
            messages = [{"role": "user", "content": prompt_text}]
            formatted = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            for temp in TEMPS:
                for rp in REP_PEN:
                    t0 = time.time()
                    gen_kwargs: dict = {"max_tokens": 256, "verbose": False}
                    if TEMP_KEY:
                        gen_kwargs[TEMP_KEY] = temp
                    if REP_KEY:
                        gen_kwargs[REP_KEY] = rp
                    output = generate(
                        model, tokenizer,
                        prompt=formatted,
                        **gen_kwargs,
                    )
                    elapsed = time.time() - t0
                    sc = score(output, case)
                    tag = f"style={style_name:14s} temp={temp} rep={rp}"
                    print(f"  [{tag}] {sc:12s} | out: {output.strip()[:60]!r}")
                    results.append({
                        "case": case["id"], "style": style_name,
                        "temp": temp, "rep_pen": rp,
                        "score": sc, "output": output.strip()[:80],
                    })

    # ── Summary table ──────────────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print("SUMMARY — FULL ✓ combinations")
    print(f"{'='*70}")
    full_results = [r for r in results if r["score"].startswith("FULL")]
    if full_results:
        for r in full_results:
            print(f"  {r['case']:30s} style={r['style']:14s} temp={r['temp']} rep={r['rep_pen']}")
    else:
        print("  (none fully matched — check PARTIAL results)")
        partial = [r for r in results if r["score"].startswith("PARTIAL")]
        for r in partial:
            print(f"  {r['case']:30s} style={r['style']:14s} temp={r['temp']} rep={r['rep_pen']}")

    print(f"\nTotal runs: {len(results)}")


if __name__ == "__main__":
    main()
