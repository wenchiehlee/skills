"""
whisper_exp.py — Hallucination fix experiments
Target: Mac-mini M4 (Apple Silicon)

Three experiments to address hallucination / incomplete transcription:

  Exp 1 — Stronger hallucination filters (mlx-whisper)
           condition_on_previous_text=False, lower compression_ratio_threshold,
           logprob_threshold, temperature fallback

  Exp 2 — Chunked transcription (mlx-whisper)
           Split audio into 5-min chunks via ffmpeg, transcribe each separately,
           merge with adjusted timestamps → avoids long-context hallucination drift

  Exp 3 — faster-whisper backend
           beam_size=5, vad_filter=True, condition_on_previous_text=False

Usage:
  python whisper_exp.py <audio> --exp 1
  python whisper_exp.py <audio> --exp 2
  python whisper_exp.py <audio> --exp 3
  python whisper_exp.py <audio> --exp all   # run all three sequentially

  python whisper_exp.py <audio> --exp all \\
      --company-config company-configs/2357/whisper.yaml \\
      --output-dir whisper-sandbox
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
import json
import shutil
import tempfile
import argparse
import subprocess
from pathlib import Path

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

try:
    import opencc
    _OPENCC = opencc.OpenCC("s2tw")
except ImportError:
    _OPENCC = None


# ── Shared helpers ────────────────────────────────────────────────────────────

def load_config(config_path: Path):
    """Return (language, initial_prompt) from whisper.yaml."""
    if not _YAML_AVAILABLE:
        raise RuntimeError("pyyaml not installed: pip install pyyaml")
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    language = cfg.get("language", "zh")
    company  = cfg.get("company_name", "")
    execs    = cfg.get("executives", [])
    exec_str = "、".join(f"{e.get('title','')}{e.get('name','')}" for e in execs)
    products = "、".join(str(p) for p in cfg.get("products", []))
    terms    = "、".join(str(t) for t in cfg.get("terms", []))
    examples = cfg.get("example_sentences", [])
    parts = [f"以下是{company}法人說明會的繁體中文逐字稿。"]
    if exec_str: parts.append(f"出席人員：{exec_str}。")
    if products: parts.append(f"產品：{products}。")
    if terms:    parts.append(f"專業術語：{terms}。")
    if examples: parts.append(" ".join(str(e) for e in examples))
    parts.append("請使用繁體字轉錄。")
    return language, "".join(parts)


def get_duration(audio_path: Path) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            text=True,
        ).strip()
        return float(out)
    except Exception as e:
        print(f"[ffprobe] {e}")
        return 0.0


def to_trad(text: str) -> str:
    return _OPENCC.convert(text) if _OPENCC else text


def is_valid_segment(seg: dict) -> bool:
    """Filter out empty / hallucinated / repetitive segments."""
    text = seg.get("text", "").strip()
    if not text:
        return False
    # Hebrew / exotic script hallucinations
    non_normal = sum(
        1 for c in text
        if ord(c) > 0x05FF
        and not (0x4E00 <= ord(c) <= 0x9FFF)
        and not (0x3400 <= ord(c) <= 0x4DBF)
        and not (0x3000 <= ord(c) <= 0x303F)   # CJK punctuation
        and not c.isascii()
    )
    if len(text) > 0 and non_normal / len(text) > 0.4:
        return False
    # Repetition loops
    words = text.split()
    if len(words) >= 4:
        most = max(words.count(w) for w in set(words))
        if most / len(words) > 0.5:
            return False
    return True


def save_md(out_path: Path, segments: list, meta: dict):
    """Write a Markdown transcript file."""
    duration  = meta.get("duration", 0)
    elapsed   = meta.get("elapsed", 0)
    rtf       = meta.get("rtf", 0)
    backend   = meta.get("backend", "?")
    model     = meta.get("model", "?")
    exp_label = meta.get("exp_label", "")
    audio_name= meta.get("audio_name", "?")

    anе_label = (
        "✓ ANE accelerated"        if rtf < 0.15 else
        "✓ GPU/MLX accelerated"    if rtf < 0.50 else
        "~ partial acceleration"   if rtf < 1.00 else
        "⚠ slower than real-time"
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Transcript: {audio_name}  [{exp_label}]\n\n")
        f.write("| Field | Value |\n|-------|-------|\n")
        f.write(f"| **Experiment** | {exp_label} |\n")
        f.write(f"| **Source** | `{audio_name}` |\n")
        f.write(f"| **Model** | `{model}` ({backend}) |\n")
        f.write(f"| **Duration** | {duration/60:.1f} min ({duration:.0f}s) |\n")
        f.write(f"| **Elapsed** | {elapsed:.1f}s |\n")
        f.write(f"| **RTF** | `{rtf:.3f}` — {anе_label} |\n")
        f.write(f"| **Segments** | {len(segments)} |\n")
        f.write(f"| **Now** | {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M CST')} |\n")
        f.write("\n---\n\n")
        prev = None
        for seg in segments:
            text = to_trad(seg.get("text", "").strip())
            if not text or text == prev:
                continue
            prev = text
            s, e = seg.get("start", 0), seg.get("end", 0)
            ms, ss = divmod(int(s), 60)
            me, se = divmod(int(e), 60)
            f.write(f"**[{ms:02d}:{ss:02d} → {me:02d}:{se:02d}]** {text}\n\n")
    print(f"[out] {exp_label} → {out_path}  ({len(segments)} segments)")


# ── Experiment 1: Stronger hallucination filters ──────────────────────────────

def exp1_strong_filters(audio_path: Path, model_name: str, language: str,
                         initial_prompt: str, out_path: Path, duration: float):
    """
    mlx-whisper with:
      - condition_on_previous_text=False   (no context bleed-over between chunks)
      - compression_ratio_threshold=1.8    (stricter — default is 2.4)
      - logprob_threshold=-0.5             (reject low-confidence segments)
      - no_speech_threshold=0.3            (more aggressive silence skip)
      - temperature fallback tuple         (auto-retry with higher temp on failure)
    """
    print("\n── Experiment 1: Strong hallucination filters (mlx-whisper) ──")
    try:
        import mlx_whisper
    except ImportError:
        print("[exp1] mlx-whisper not installed. Skipping.")
        return

    mlx_models = {
        "distil-whisper-large-v3": "mlx-community/distil-whisper-large-v3",
        "whisper-large-v3":        "mlx-community/whisper-large-v3-mlx",
        "whisper-large-v3-turbo":  "mlx-community/whisper-large-v3-turbo",
    }
    mlx_model = mlx_models.get(model_name, f"mlx-community/{model_name}")
    print(f"  model : {mlx_model}")
    print(f"  params: condition_on_previous_text=False, compression_ratio=1.8, logprob=-0.5")

    t0 = time.monotonic()
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=mlx_model,
        verbose=False,
        language=language,
        initial_prompt=initial_prompt,
        condition_on_previous_text=False,   # KEY: no hallucination drift
        no_speech_threshold=0.3,
        compression_ratio_threshold=1.8,
        logprob_threshold=-0.5,
        temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        word_timestamps=False,
    )
    elapsed = time.monotonic() - t0
    rtf = elapsed / duration if duration else 0

    segs = [s for s in result.get("segments", []) if is_valid_segment(s)]
    save_md(out_path, segs, dict(
        duration=duration, elapsed=elapsed, rtf=rtf,
        backend="mlx-whisper", model=model_name,
        exp_label="Exp1-StrongFilter", audio_name=audio_path.name,
    ))


# ── Experiment 2: Chunked transcription ──────────────────────────────────────

def exp2_chunked(audio_path: Path, model_name: str, language: str,
                  initial_prompt: str, out_path: Path, duration: float,
                  chunk_min: int = 5, overlap_sec: int = 10):
    """
    Split audio into N-minute chunks (with overlap), transcribe each with
    mlx-whisper, merge segments with adjusted timestamps.

    Avoids the long-context hallucination drift that hits large-v3 on 60-min audio.
    """
    print(f"\n── Experiment 2: Chunked ({chunk_min}min chunks, {overlap_sec}s overlap) ──")
    try:
        import mlx_whisper
    except ImportError:
        print("[exp2] mlx-whisper not installed. Skipping.")
        return

    mlx_models = {
        "distil-whisper-large-v3": "mlx-community/distil-whisper-large-v3",
        "whisper-large-v3":        "mlx-community/whisper-large-v3-mlx",
        "whisper-large-v3-turbo":  "mlx-community/whisper-large-v3-turbo",
    }
    mlx_model = mlx_models.get(model_name, f"mlx-community/{model_name}")

    chunk_sec  = chunk_min * 60
    all_segs   = []
    t0         = time.monotonic()
    tmpdir     = Path(tempfile.mkdtemp(prefix="whisper_exp2_"))

    try:
        # Generate chunk start times
        starts = list(range(0, int(duration), chunk_sec))
        print(f"  Splitting into {len(starts)} chunks of {chunk_min}min each...")

        for i, start in enumerate(starts):
            chunk_file = tmpdir / f"chunk_{i:03d}.wav"
            end        = min(start + chunk_sec + overlap_sec, duration)

            # Extract chunk with ffmpeg
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(start), "-to", str(end),
                "-i", str(audio_path),
                "-ar", "16000", "-ac", "1",
                str(chunk_file),
            ], check=True)

            pct = (i + 1) / len(starts) * 100
            print(f"  [{pct:5.1f}%] Transcribing chunk {i+1}/{len(starts)}  "
                  f"({start//60:.0f}min – {end//60:.0f}min)...", end="\r")

            result = mlx_whisper.transcribe(
                str(chunk_file),
                path_or_hf_repo=mlx_model,
                verbose=False,
                language=language,
                initial_prompt=initial_prompt,
                condition_on_previous_text=False,
                no_speech_threshold=0.3,
                compression_ratio_threshold=1.8,
                logprob_threshold=-0.5,
                temperature=(0.0, 0.2, 0.4),
                word_timestamps=False,
            )

            for seg in result.get("segments", []):
                if not is_valid_segment(seg):
                    continue
                # Adjust timestamps to global timeline
                seg_start = seg.get("start", 0) + start
                seg_end   = seg.get("end", 0)   + start
                # Skip overlap region (except for last chunk)
                if i < len(starts) - 1 and seg_start >= start + chunk_sec:
                    continue
                all_segs.append(dict(seg, start=seg_start, end=seg_end))

        print()  # newline after \r progress
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    elapsed = time.monotonic() - t0
    rtf = elapsed / duration if duration else 0

    save_md(out_path, all_segs, dict(
        duration=duration, elapsed=elapsed, rtf=rtf,
        backend="mlx-whisper (chunked)",
        model=model_name,
        exp_label=f"Exp2-Chunked{chunk_min}min",
        audio_name=audio_path.name,
    ))


# ── Experiment 3: faster-whisper ─────────────────────────────────────────────

def exp3_faster_whisper(audio_path: Path, model_name: str, language: str,
                         initial_prompt: str, out_path: Path, duration: float):
    """
    faster-whisper with:
      - beam_size=5
      - vad_filter=True (Silero VAD — skips silence before decoding)
      - condition_on_previous_text=False
      - compression_ratio_threshold=1.8
    """
    print("\n── Experiment 3: faster-whisper (VAD + beam_size=5) ──")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[exp3] faster-whisper not installed. Run: pip install faster-whisper")
        return

    # faster-whisper model name mapping
    fw_models = {
        "whisper-large-v3":        "large-v3",
        "distil-whisper-large-v3": "distil-large-v3",
        "whisper-large-v3-turbo":  "large-v3-turbo",
        "whisper-medium":          "medium",
    }
    fw_model = fw_models.get(model_name, model_name)
    print(f"  model : {fw_model}")
    print(f"  params: beam_size=5, vad_filter=True, condition_on_previous_text=False")

    t0 = time.monotonic()
    model = WhisperModel(fw_model, device="auto", compute_type="auto")

    segments_gen, info = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(
            min_silence_duration_ms=500,
            speech_pad_ms=200,
        ),
        condition_on_previous_text=False,
        compression_ratio_threshold=1.8,
        log_prob_threshold=-0.5,
        no_speech_threshold=0.3,
        without_timestamps=False,
    )

    segs = []
    for seg in segments_gen:
        d = {"start": seg.start, "end": seg.end, "text": seg.text}
        if is_valid_segment(d):
            segs.append(d)

    elapsed = time.monotonic() - t0
    rtf = elapsed / duration if duration else 0

    save_md(out_path, segs, dict(
        duration=duration, elapsed=elapsed, rtf=rtf,
        backend="faster-whisper",
        model=fw_model,
        exp_label="Exp3-FasterWhisper",
        audio_name=audio_path.name,
    ))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Whisper hallucination fix experiments"
    )
    parser.add_argument("audio", help="Path to .m4a / .mp3 / .wav")
    parser.add_argument(
        "--exp", default="all", choices=["1", "2", "3", "all"],
        help="Experiment to run (default: all)"
    )
    parser.add_argument(
        "--model", default="whisper-large-v3",
        help="Model name (default: whisper-large-v3)"
    )
    parser.add_argument(
        "--language", default=None,
        help="Language code (default: auto)"
    )
    parser.add_argument(
        "--company-config", default=None,
        help="Path to whisper.yaml company config"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory for .md files (default: alongside audio)"
    )
    parser.add_argument(
        "--chunk-min", type=int, default=5,
        help="Chunk size in minutes for Exp 2 (default: 5)"
    )
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: File not found: {audio_path}")
        sys.exit(1)

    # ── Language + prompt ─────────────────────────────────────────────────────
    language       = args.language
    initial_prompt = None
    if args.company_config:
        cfg_path = Path(args.company_config)
        if not cfg_path.exists():
            print(f"ERROR: Config not found: {cfg_path}")
            sys.exit(1)
        language, initial_prompt = load_config(cfg_path)
        print(f"[config] language={language}, prompt loaded from {cfg_path.name}")

    # ── Output dir ────────────────────────────────────────────────────────────
    out_dir = Path(args.output_dir) if args.output_dir else audio_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem

    duration = get_duration(audio_path)
    print(f"\n=== whisper_exp.py  |  {audio_path.name}  |  {duration/60:.1f} min ===")
    print(f"    model={args.model}  language={language}  exp={args.exp}")
    print(f"    output → {out_dir}/\n")

    run = lambda n: args.exp == str(n) or args.exp == "all"

    if run(1):
        exp1_strong_filters(
            audio_path, args.model, language, initial_prompt,
            out_dir / f"{stem}_exp1.md", duration,
        )

    if run(2):
        exp2_chunked(
            audio_path, args.model, language, initial_prompt,
            out_dir / f"{stem}_exp2.md", duration,
            chunk_min=args.chunk_min,
        )

    if run(3):
        exp3_faster_whisper(
            audio_path, args.model, language, initial_prompt,
            out_dir / f"{stem}_exp3.md", duration,
        )

    print("\n=== All requested experiments complete ===")


if __name__ == "__main__":
    main()
