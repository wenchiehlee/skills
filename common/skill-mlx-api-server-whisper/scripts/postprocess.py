"""
postprocess.py — Language-aware SRT rescue and dictionary correction.

Directly parses (MM:SS.mmm) SRT files for cross-model rescue.
"""

from __future__ import annotations
import argparse
import re
import sys
import io
from pathlib import Path

# Configs
SANDBOX = Path("mlx-api-server-whisper/whisper-sandbox")
EXPECTED_LANG: str = "zh" 
CORRECTIONS: dict[str, str] = {}
ENG_CORRECTIONS: dict[str, str] = {}

HALLUCINATION_BLACKLIST = [
    "中文字幕提供", "閱轉發打賞支持明鏡與點點", "點贊 訂閱 轉發 打賞", "中文字幕志願者",
    "不吝點贊", "感謝您的觀看", "請點贊訂閱", "打開旁邊的鈴鐺", "分享給你的朋友",
    "歡迎訂閱", "不吝点赞", "感谢您的观看",
    "請使用繁體字轉錄", "请使用繁体字转录"  # initial_prompt echo leakage
]

# ── Utilities ────────────────────────────────────────────────────────────────

def _load_config(stem: str) -> None:
    global EXPECTED_LANG, CORRECTIONS, ENG_CORRECTIONS
    stock_id = stem.split("_")[0]
    # cwd-relative (not __file__-relative): these live in mlx-api-server-whisper/ as
    # data/config that grows over time, independent of where this script itself lives.
    generic_path = Path("mlx-api-server-whisper/whisper.yaml")
    config_path = Path("mlx-api-server-whisper/company-configs") / stock_id / "whisper.yaml"
    EXPECTED_LANG, CORRECTIONS, ENG_CORRECTIONS = "zh", {}, {}

    def _load_file(p: Path):
        if p.exists():
            try:
                import yaml
                cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
                if isinstance(cfg, dict):
                    if "language" in cfg: globals()["EXPECTED_LANG"] = cfg["language"]
                    if "corrections" in cfg: CORRECTIONS.update(cfg["corrections"])
                    if "english_corrections" in cfg: ENG_CORRECTIONS.update(cfg["english_corrections"])
            except Exception: pass
    _load_file(generic_path)
    _load_file(config_path)
    print(f"  [config] Mode: {EXPECTED_LANG}, Corrections: {len(CORRECTIONS)} (ZH), {len(ENG_CORRECTIONS)} (EN)")

def parse_srt_to_segs(path: Path) -> list[dict]:
    """Parse (MM:SS.mmm) formatted SRT into segment list."""
    if not path.exists(): return []
    content = path.read_text(encoding="utf-8")
    if "---" in content: content = content.split("---", 1)[-1]
    
    segs = []
    pattern = re.compile(r"^\((\d+):(\d+\.\d+)\)\s*(.*)")
    for line in content.splitlines():
        m = pattern.match(line.strip())
        if m:
            mins, secs, txt = m.groups()
            start = int(mins) * 60 + float(secs)
            segs.append({"start": start, "text": txt})
    return segs

def is_compromised(text: str, lang: str = "zh") -> bool:
    if not text.strip(): return True
    if any(bad in text for bad in HALLUCINATION_BLACKLIST): return True
    # Density check (len/dur) skipped here as we don't have per-seg duration in SRT line
    if lang == "zh":
        cjk_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        if cjk_count == 0 and len(text) > 40: return True
    return False

def apply_fixes(text: str) -> str:
    for w, r in CORRECTIONS.items(): text = text.replace(w, r)
    if ENG_CORRECTIONS:
        for w in sorted(ENG_CORRECTIONS.keys(), key=len, reverse=True):
            text = re.sub(r'\b' + re.escape(w) + r'\b', ENG_CORRECTIONS[w], text, flags=re.IGNORECASE)
    return text

# ── Main Logic ───────────────────────────────────────────────────────────────

def step_rescue(stem: str, exps: list[int]):
    print(f"\n[rescue] {stem} (SRT-based voting)")
    results = {}
    for i in exps:
        segs = parse_srt_to_segs(SANDBOX / f"{stem}_exp{i}.srt")
        if segs: results[i] = segs
    
    if not results:
        print("  ERROR: No experiment SRT files found.")
        return
    
    # ── Language-Aware Anchor Selection ──────────────────────────────────────
    # Keep this aligned with run-pipeline.yml production auto exps:
    #   zh=1,6,11; mixed=1,6,11,14; en=1,13
    # Priority is GT-calibrated from 30 full-call FIN/GT samples (2026-08-12).
    if EXPECTED_LANG == "en":
        priority = [13, 1, 20, 15, 19, 7, 11, 0]
    elif EXPECTED_LANG == "mixed":
        priority = [14, 11, 6, 1, 7, 3, 0]
    else:
        priority = [11, 6, 1, 7, 3, 14, 0]

    anchor_id = next((i for i in priority if i in results), exps[0])
    rescue_order = [i for i in priority if i in results and i != anchor_id]
    rescue_order.extend(i for i in sorted(results) if i != anchor_id and i not in rescue_order)

    anchor_segs = results[anchor_id]
    print(f"  Anchor Model: exp{anchor_id} ({len(anchor_segs)} segments)")
    
    final_lines = [f"[METADATA]\nSource: {stem}_exp{anchor_id}\nLanguage: {EXPECTED_LANG}\n---"]
    
    for seg in anchor_segs:
        txt, start = seg["text"], seg["start"]
        if is_compromised(txt, EXPECTED_LANG):
            rescued = False
            for other_id in rescue_order:
                # Find roughly overlapping segment
                for o_seg in results[other_id]:
                    if abs(o_seg["start"] - start) < 1.5:
                        if not is_compromised(o_seg["text"], EXPECTED_LANG):
                            txt, rescued = o_seg["text"], True
                            break
                if rescued: break
            if not rescued: continue # Drop segment if no model has good version
            
        final_lines.append(f"({int(start//60):02d}:{start%60:06.3f}) {txt}")
    
    (SANDBOX / f"{stem}_merged.srt").write_text("\n".join(final_lines), encoding="utf-8")

def step_fix(stem: str):
    p = SANDBOX / f"{stem}_merged.srt"
    if not p.exists(): return
    lines = p.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if line.startswith("(") and ") " in line:
            ts, txt = line.split(") ", 1)
            out.append(f"{ts}) {apply_fixes(txt)}")
        else: out.append(line)
    (SANDBOX / f"{stem}_fix.srt").write_text("\n".join(out), encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stem")
    parser.add_argument("--step", default="best")
    parser.add_argument("--exps", default="1,7,11")
    args = parser.parse_args()
    _load_config(args.stem)
    exp_list = [int(x) for x in args.exps.split(",")]
    if args.step in ["rescue", "best"]:
        step_rescue(args.stem, exp_list)
        step_fix(args.stem)
    elif args.step == "fix": step_fix(args.stem)

if __name__ == "__main__":
    main()
