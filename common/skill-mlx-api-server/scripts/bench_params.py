"""Benchmark --kv-bits and --max-kv-size effect on speed and output quality."""
import subprocess, sys, time, re

MODEL = "mlx-community/Qwen3.5-9B-MLX-4bit"
PROMPT = "請用繁體中文，以兩句話摘要：台積電2024Q4營收8684億元，年增39%，受惠AI晶片需求強勁。"
MAX_TOKENS = 200

CONFIGS = [
    ("baseline",              []),
    ("kv-bits-8",             ["--kv-bits", "8"]),
    ("kv-bits-4",             ["--kv-bits", "4"]),
    ("max-kv-1024",           ["--max-kv-size", "1024"]),
    ("kv-bits-4+max-kv-1024", ["--kv-bits", "4", "--max-kv-size", "1024"]),
]

print(f"Model: {MODEL}")
print(f"Prompt length: {len(PROMPT)} chars\n")
print(f"{'Config':<26} {'Duration':>8} {'Prompt tok/s':>13} {'Gen tok/s':>10} {'Peak mem':>9} {'Output snippet'}")
print("-" * 110)

for name, extra_args in CONFIGS:
    cmd = [
        sys.executable, "-m", "mlx_lm", "generate",
        "--model", MODEL,
        "--prompt", PROMPT,
        "--max-tokens", str(MAX_TOKENS),
        "--temp", "0.0",
        "--verbose", "True",
    ] + extra_args

    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    duration = round(time.time() - t0, 1)

    stdout = result.stdout + result.stderr
    prompt_tps  = re.search(r"Prompt:.*?([\d.]+) tokens-per-sec", stdout)
    gen_tps     = re.search(r"Generation:.*?([\d.]+) tokens-per-sec", stdout)
    peak_mem    = re.search(r"Peak memory:\s*([\d.]+)", stdout)

    # Extract generated text (between ========== markers)
    text_match = re.search(r"={10}\n(.*?)\n={10}", stdout, re.DOTALL)
    snippet = text_match.group(1).strip()[:60] if text_match else stdout[:60]
    snippet = snippet.replace("\n", " ")

    p_tps = prompt_tps.group(1) if prompt_tps else "?"
    g_tps = gen_tps.group(1) if gen_tps else "?"
    mem   = peak_mem.group(1) + " GB" if peak_mem else "?"

    print(f"{name:<26} {duration:>7}s {p_tps:>12} {g_tps:>10} {mem:>9}  {snippet}")
