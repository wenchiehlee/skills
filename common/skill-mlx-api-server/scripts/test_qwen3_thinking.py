"""Verify Qwen3.5 enable_thinking=False behavior on MLX."""
import time, inspect
from mlx_lm import load, generate

MODEL = "mlx-community/Qwen3.5-9B-MLX-4bit"
PROMPT = "請用繁體中文，以兩句話摘要：台積電2024Q4營收8684億元，年增39%，受惠AI晶片需求強勁。"

print(f"generate() signature: {inspect.signature(generate)}")

print(f"\nLoading model: {MODEL}")
model, tokenizer = load(MODEL)
messages = [{"role": "user", "content": PROMPT}]

print("\n=== TEST 1: enable_thinking=True (default) ===")
txt = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True, enable_thinking=True
)
t0 = time.time()
out = generate(model, tokenizer, prompt=txt, max_tokens=512, verbose=False)
print(f"Duration: {time.time()-t0:.1f}s")
print(f"Output ({len(out)} chars): {out[:300]}")
print(f"Has </think>: {'</think>' in out}")

print("\n=== TEST 2: enable_thinking=False ===")
txt2 = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
)
t0 = time.time()
out2 = generate(model, tokenizer, prompt=txt2, max_tokens=512, verbose=False)
print(f"Duration: {time.time()-t0:.1f}s")
print(f"Output ({len(out2)} chars): {out2[:300]}")
print(f"Empty output: {len(out2.strip()) == 0}")
