"""
whisper_poc.py — WhisperKit / MLX-Whisper Transcription POC
Target: Mac-mini M4 (Apple Silicon, Core ML / ANE acceleration)

Backends (in priority order):
  1. mlx-whisper     — Apple MLX framework, fastest on M-series
                       pip install mlx-whisper
  2. whisperkittools — WhisperKit Core ML (official Apple ANE path)
                       pip install whisperkittools

Usage:
  python whisper_poc.py <audio_file>
  python whisper_poc.py <audio_file> --model distil-whisper-large-v3
  python whisper_poc.py <audio_file> --backend mlx
  python whisper_poc.py <audio_file> --backend whisperkittools

Output:
  - Console: RTF, words/min, hardware confirmation
  - File:    <audio_file>.md   (full transcript in Markdown with timestamps)
  - File:    <audio_file>.json (segments with timestamps)
"""

import os
import sys
import time
import json
import platform
import subprocess
import argparse
import warnings
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))
from pathlib import Path

# Suppress known harmless warnings from faster-whisper / torch dependencies
warnings.filterwarnings("ignore", category=FutureWarning, module="torch.cuda")
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*matmul.*")

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

# ── Amplitude Analytics ───────────────────────────────────────────────────────
_analytics_path = Path(__file__).parent
if str(_analytics_path) not in sys.path:
    sys.path.insert(0, str(_analytics_path))

try:
    from analytics.amplitude import WhisperCallTracker, configure as amplitude_configure
    amplitude_configure(os.getenv("LLM_APP_NAME", "whisper-transcription-stage"))
except ImportError:
    WhisperCallTracker = None
    amplitude_configure = None

try:
    import opencc
    _OPENCC = opencc.OpenCC("s2tw")  # Simplified → Traditional (character-level, no phrase variants)
except ImportError:
    _OPENCC = None


class _NullContext:
    """Amplitude 未安裝時的空 context manager，確保 with 語法不報錯。"""
    def __enter__(self): return self
    def __exit__(self, *_): return False


def _resolve_tracking_model_info(provider: str, requested_model: str) -> tuple[str, str]:
    """Return (model, model_repo) for reporting / Amplitude tracking."""
    mlx_models = {
        "distil-whisper-large-v3": "mlx-community/distil-whisper-large-v3",
        "whisper-large-v3": "mlx-community/whisper-large-v3-mlx",
        "whisper-large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "whisper-medium": "mlx-community/whisper-medium-mlx",
    }
    fw_models = {
        "whisper-large-v3": "large-v3",
        "distil-whisper-large-v3": "distil-large-v3",
        "whisper-large-v3-turbo": "large-v3-turbo",
        "whisper-medium": "medium",
    }

    if provider == "mlx-whisper":
        return requested_model, mlx_models.get(requested_model, f"mlx-community/{requested_model}")
    if provider == "faster-whisper":
        return requested_model, fw_models.get(requested_model, requested_model)
    if provider == "whisperkittools":
        return requested_model, requested_model.replace("-", "_").replace("/", "_")
    if provider == "sensevoice":
        return "SenseVoiceSmall", "iic/SenseVoiceSmall"
    if provider == "paraformer":
        return "paraformer-zh", "paraformer-zh"
    if provider == "mlx-qwen3":
        return "Qwen/Qwen3-ASR-0.6B", "Qwen/Qwen3-ASR-0.6B"
    if provider == "qwen3-asr":
        return "Qwen/Qwen3-ASR-1.7B", "Qwen/Qwen3-ASR-1.7B"
    return requested_model, requested_model


# ── Company Config / Prompt Builder ──────────────────────────────────────────

def _load_yaml_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def build_prompt_from_config(config_path: Path | list[Path], max_chars: int = 200) -> tuple:
    """
    Load one or more config files and return (language, initial_prompt).

    For English tracks, prompt sources may be layered as:
      1. company whisper.yaml      (base language/company metadata)
      2. generic whisper-en.yaml   (shared investor-call glossary)
      3. company whisper-en.yaml   (company-specific executives / terms)

    Budget: max_chars (default 200) — Whisper large-v3 decoder context is 448 tokens;
    the first half (~224 tokens) is reserved for initial_prompt. Chinese text is
    roughly 1 char ≈ 1 token, so 200 chars gives a safe margin.
    """
    if not _YAML_AVAILABLE:
        raise RuntimeError("pyyaml is not installed. Run: pip install pyyaml")

    config_paths = config_path if isinstance(config_path, list) else [config_path]
    cfgs = [_load_yaml_config(path) for path in config_paths]

    language = next((cfg.get("language") for cfg in reversed(cfgs) if cfg.get("language")), "zh")
    company = next((cfg.get("company_name") for cfg in reversed(cfgs) if cfg.get("company_name")), "")

    if language == "en":
        header = f"This is an English earnings conference call transcript for {company}." if company else "This is an English earnings conference call transcript."
        footer = "Use accurate English names and financial terms."
        exec_prefix, term_prefix, term_sep, sent_sep = "Participants: ", "Key terms: ", ", ", " "
    else:
        header = f"以下是{company}法人說明會的繁體中文逐字稿。"
        footer = "請使用繁體字轉錄。"
        exec_prefix, term_prefix, term_sep, sent_sep = "出席人員：", "專業術語：", "、", " "

    budget = max_chars - len(header) - len(footer)
    parts: list[str] = []

    exec_parts: list[str] = []
    seen_execs: set[str] = set()
    for cfg in cfgs:
        for e in cfg.get("executives", []) or []:
            if language == "en":
                item = " ".join(x for x in [str(e.get("title", "")).strip(), str(e.get("name", "")).strip()] if x).strip()
            else:
                item = f"{e.get('title','')}{e.get('name','')}"
            if item and item not in seen_execs:
                seen_execs.add(item)
                exec_parts.append(item)
    if exec_parts:
        exec_section = f"{exec_prefix}{term_sep.join(exec_parts)}."
        if len(exec_section) <= budget:
            parts.append(exec_section)
            budget -= len(exec_section)

    all_terms: list[str] = []
    seen_terms: set[str] = set()
    for cfg in cfgs:
        for term in cfg.get("terms", []) or []:
            item = str(term).strip()
            if item and item not in seen_terms:
                seen_terms.add(item)
                all_terms.append(item)
    fitted_terms: list[str] = []
    overhead = len(term_prefix) + 1
    for t in all_terms:
        if overhead + len(term_sep.join(fitted_terms + [t])) <= budget:
            fitted_terms.append(t)
        else:
            break
    if fitted_terms:
        term_section = f"{term_prefix}{term_sep.join(fitted_terms)}."
        parts.append(term_section)
        budget -= len(term_section)

    all_examples: list[str] = []
    seen_examples: set[str] = set()
    for cfg in cfgs:
        for ex in cfg.get("example_sentences", []) or []:
            item = str(ex).strip()
            if item and item not in seen_examples:
                seen_examples.add(item)
                all_examples.append(item)
    fitted_examples: list[str] = []
    for ex in all_examples:
        sep = sent_sep if fitted_examples else ""
        if len(sep) + len(ex) <= budget:
            fitted_examples.append(ex)
            budget -= len(sep) + len(ex)
    if fitted_examples:
        parts.append(sent_sep.join(fitted_examples))

    initial_prompt = header + (" " if language == "en" else "") + "".join(parts) + (" " if language == "en" and parts else "") + footer

    skipped_terms = len(all_terms) - len(fitted_terms)
    skipped_examples = len(all_examples) - len(fitted_examples)
    source_names = ", ".join(path.name for path in config_paths)
    print(
        f"[config] initial_prompt: {len(initial_prompt)} chars / ~{max_chars} budget  "
        f"terms={len(fitted_terms)}/{len(all_terms)}"
        + (f" (skipped {skipped_terms})" if skipped_terms else "")
        + f"  examples={len(fitted_examples)}/{len(all_examples)}"
        + (f" (skipped {skipped_examples})" if skipped_examples else "")
        + f"  sources={source_names}",
        file=sys.stderr,
    )

    return (language, initial_prompt)


# ── Hardware Check ────────────────────────────────────────────────────────────

def check_hardware() -> dict:
    """Confirm native ARM64 (not Rosetta) and report chip info."""
    info = {
        "platform": platform.platform(),
        "machine":  platform.machine(),
        "native":   False,
        "chip":     "unknown",
    }

    if platform.system() != "Darwin":
        print("[hw] WARNING: Not macOS — ANE acceleration unavailable.")
        return info

    # Check Rosetta translation
    try:
        translated = subprocess.check_output(
            ["sysctl", "-in", "sysctl.proc_translated"], text=True
        ).strip()
        info["native"] = (translated != "1")
    except Exception:
        info["native"] = (platform.machine() == "arm64")

    # Get chip model (e.g. "Apple M4")
    try:
        chip = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
        info["chip"] = chip
    except Exception:
        pass

    status = "Native ARM64" if info["native"] else "Rosetta (SLOW — use native Python)"
    print(f"[hw] {info['chip']}  |  {status}")
    return info


# ── Audio Duration ────────────────────────────────────────────────────────────

def get_audio_duration(audio_path: Path) -> float:
    """Return duration in seconds via ffprobe."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(audio_path)],
            text=True,
        ).strip()
        return float(out)
    except Exception as e:
        print(f"[ffprobe] Could not get duration: {e}")
        return 0.0


# ── Backend: MLX-Whisper ──────────────────────────────────────────────────────

def transcribe_mlx(audio_path: Path, model_name: str, language: str = None, initial_prompt: str = None,
                   temperature: float = 0.0, no_speech_threshold: float = 0.6,
                   compression_ratio_threshold: float = 2.4,
                   max_seg_sec: float = 0.0) -> dict:
    """
    Transcribe using mlx-whisper (Apple MLX framework).
    Supports distil-whisper-large-v3, whisper-large-v3, etc.

    Install: pip install mlx-whisper

    max_seg_sec: if > 0, enable word_timestamps and split long segments at 。！？ then ，
    """
    try:
        import mlx_whisper
    except ImportError:
        raise RuntimeError("mlx-whisper not installed. Run: pip install mlx-whisper")

    # MLX model name mapping
    mlx_models = {
        "distil-whisper-large-v3":  "mlx-community/distil-whisper-large-v3",
        "whisper-large-v3":         "mlx-community/whisper-large-v3-mlx",
        "whisper-large-v3-turbo":   "mlx-community/whisper-large-v3-turbo",
        "whisper-medium":           "mlx-community/whisper-medium-mlx",
    }
    mlx_model = model_name if "/" in model_name else mlx_models.get(model_name, f"mlx-community/{model_name}")
    use_word_ts = max_seg_sec > 0
    print(f"[mlx] Model: {mlx_model}")
    print(f"[mlx] Transcribing {audio_path.name} ...")
    if use_word_ts:
        print(f"[mlx] word_timestamps=True (max_seg_sec={max_seg_sec}s, splits at 。！？ then ，)")

    kwargs = dict(
        path_or_hf_repo=mlx_model,
        verbose=False,
        word_timestamps=use_word_ts,
        condition_on_previous_text=False,
        no_speech_threshold=no_speech_threshold,
        compression_ratio_threshold=compression_ratio_threshold,
        temperature=temperature,
    )
    if language:
        kwargs["language"] = language
    if initial_prompt:
        # initial_prompt primes the decoder context for all chunks
        kwargs["initial_prompt"] = initial_prompt
    result = mlx_whisper.transcribe(str(audio_path), **kwargs)

    if use_word_ts:
        segs = result.get("segments", [])
        before = len(segs)
        segs = _resegment_by_words(segs, max_seg_sec)
        # Strip word lists from final output
        result["segments"] = [{"start": s["start"], "end": s["end"], "text": s["text"]}
                               for s in segs]
        print(f"[mlx] resegment: {before} → {len(result['segments'])} segments (max {max_seg_sec}s)")

    return result


# ── Backend: WhisperKit (Core ML / ANE) ──────────────────────────────────────

def transcribe_whisperkittools(audio_path: Path, model_name: str, language: str = None, initial_prompt: str = None) -> dict:
    """
    Transcribe using whisperkittools (Apple WhisperKit — Core ML, ANE-optimized).

    Install: pip install whisperkittools
    """
    try:
        from whisperkittools import WhisperKit
    except ImportError:
        raise RuntimeError(
            "whisperkittools not installed. Run: pip install whisperkittools"
        )

    # WhisperKit model name format uses underscores
    wk_model = model_name.replace("-", "_").replace("/", "_")
    print(f"[whisperkittools] Model: {wk_model}")
    print(f"[whisperkittools] Transcribing {audio_path.name} ...")

    wk = WhisperKit(model_name=wk_model)
    result = wk.transcribe(str(audio_path))

    # Normalise to Whisper-style output dict
    if isinstance(result, str):
        result = {"text": result, "segments": []}
    return result


# ── Backend: faster-whisper (CTranslate2) ────────────────────────────────────

_SPLIT_PUNCT = frozenset("。！？")
_SPLIT_COMMA = frozenset("，,")  # include ASCII comma — faster-whisper sometimes outputs , instead of ，


def _w(word, attr: str):
    """Get attribute from a word that is either a named tuple or a dict."""
    return getattr(word, attr, None) if hasattr(word, attr) else word.get(attr)


def _split_segments_at(segments: list[dict], max_seg_sec: float,
                        split_chars: frozenset) -> list[dict]:
    """Single-pass: split segments longer than max_seg_sec at split_chars."""
    result = []
    for seg in segments:
        duration = seg["end"] - seg["start"]
        words = seg.get("words", [])
        if duration <= max_seg_sec or not words:
            result.append(seg)
            continue

        chunks: list[tuple[float, float, str, list]] = []
        chunk_start = _w(words[0], "start")
        chunk_text: list[str] = []
        chunk_words: list = []
        chunk_end = _w(words[0], "end")

        for w in words:
            chunk_text.append(_w(w, "word"))
            chunk_words.append(w)
            chunk_end = _w(w, "end")
            wtext = (_w(w, "word") or "").rstrip()
            if wtext and wtext[-1] in split_chars:
                chunks.append((chunk_start, chunk_end,
                               "".join(chunk_text).strip(), chunk_words))
                chunk_text, chunk_words = [], []
                chunk_start = chunk_end

        if chunk_text:
            chunks.append((chunk_start, chunk_end,
                           "".join(chunk_text).strip(), chunk_words))

        if len(chunks) <= 1:
            result.append(seg)
        else:
            for c_start, c_end, c_text, c_words in chunks:
                if c_text:
                    result.append({"start": c_start, "end": c_end, "text": c_text,
                                   "words": c_words})
    return result


def _resegment_by_words(segments: list[dict], max_seg_sec: float) -> list[dict]:
    """Split segments longer than max_seg_sec using word-level timestamps.
    Pass 1: split at 。！？ (sentence boundaries).
    Pass 2: split remaining long segments at ，(clause boundaries)."""
    after_pass1 = _split_segments_at(segments, max_seg_sec, _SPLIT_PUNCT)
    after_pass2 = _split_segments_at(after_pass1, max_seg_sec, _SPLIT_COMMA)
    return after_pass2


def transcribe_faster_whisper(audio_path: Path, model_name: str, language: str = None,
                              initial_prompt: str = None,
                              no_speech_threshold: float = 0.6,
                              compression_ratio_threshold: float = 2.4,
                              beam_size: int = 5,
                              vad_min_silence_ms: int = 500,
                              max_seg_sec: float = 0.0) -> dict:
    """
    Transcribe using faster-whisper (CTranslate2).

    Install: pip install faster-whisper
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")

    fw_models = {
        "whisper-large-v3":        "large-v3",
        "distil-whisper-large-v3": "distil-large-v3",
        "whisper-large-v3-turbo":  "large-v3-turbo",
        "whisper-medium":          "medium",
    }
    fw_model = fw_models.get(model_name, model_name)
    print(f"[faster-whisper] Model: {fw_model}")
    print(f"[faster-whisper] Transcribing {audio_path.name} ...")

    use_word_ts = max_seg_sec > 0
    if use_word_ts:
        print(f"[faster-whisper] word_timestamps=True (max_seg_sec={max_seg_sec}s)")

    model = WhisperModel(fw_model, device="auto", compute_type="auto")
    segments_gen, _ = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt,
        beam_size=beam_size,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=vad_min_silence_ms, speech_pad_ms=200),
        condition_on_previous_text=False,
        compression_ratio_threshold=compression_ratio_threshold,
        no_speech_threshold=no_speech_threshold,
        without_timestamps=False,
        word_timestamps=use_word_ts,
    )
    segments = [{"start": s.start, "end": s.end, "text": s.text,
                 **({"words": s.words} if use_word_ts else {})}
                for s in segments_gen]

    if use_word_ts:
        before = len(segments)
        segments = _resegment_by_words(segments, max_seg_sec)
        print(f"[faster-whisper] resegment: {before} → {len(segments)} segments (max {max_seg_sec}s)")

    # Strip word lists from final output (not needed downstream)
    segments = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments]
    text = " ".join(s["text"].strip() for s in segments)
    return {"text": text, "segments": segments}


# ── Backend: SenseVoice-Small (non-autoregressive, FunASR) ───────────────────

def transcribe_sensevoice(audio_path: Path, language: str = "zh",
                           max_seg_sec: float = 0.0) -> dict:
    """
    Transcribe using FunAudioLLM/SenseVoiceSmall via funasr.
    Architecture: non-autoregressive end-to-end (completely different from Whisper).
    RTF ~0.008× — ~15× faster than Whisper-Large. Apache 2.0 license.

    Install: pip install funasr torch torchaudio
    Model:   FunAudioLLM/SenseVoiceSmall (~250M, auto-downloaded from HuggingFace)
    Output:  Simplified Chinese → OpenCC s2tw applied by main pipeline
    """
    try:
        from funasr import AutoModel as FunASRAutoModel
        import torch
        import librosa
        import re
    except ImportError:
        raise RuntimeError("sensevoice requires: pip install funasr torch torchaudio")

    try:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
    except ImportError:
        _TAG_RE = re.compile(r"<\|[^|]+\|>")
        rich_transcription_postprocess = lambda t: _TAG_RE.sub("", t)

    MODEL_ID = "iic/SenseVoiceSmall"  # ModelScope hub ID required by FunASR registry
    print(f"[sensevoice] Model: {MODEL_ID}")
    print(f"[sensevoice] Transcribing {audio_path.name} ...")

    device = "mps" if torch.backends.mps.is_available() else "cpu"

    sv_model = FunASRAutoModel(
        model=MODEL_ID,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},  # 30s max VAD segment
        trust_remote_code=True,
        device=device,
    )

    audio_full, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    duration_total = len(audio_full) / 16000

    raw_result = sv_model.generate(
        input=audio_full,
        cache={},
        language=language,
        use_itn=True,
        batch_size_s=300,
        merge_vad=True,
        merge_length_s=15,
    )

    segments = []
    for item in (raw_result or []):
        text = rich_transcription_postprocess(item.get("text", "")).strip()
        if not text:
            continue
        ts = item.get("timestamp")
        if ts and isinstance(ts, (list, tuple)) and len(ts) > 0:
            # timestamp: list of [start_ms, end_ms] pairs
            first = ts[0] if isinstance(ts[0], (list, tuple)) else ts
            last  = ts[-1] if isinstance(ts[-1], (list, tuple)) else ts
            t_start = (first[0] if isinstance(first[0], (int, float)) else first[0]) / 1000.0
            t_end   = (last[-1] if isinstance(last[-1], (int, float)) else last[1]) / 1000.0
        else:
            t_start, t_end = 0.0, duration_total
        segments.append({"start": t_start, "end": t_end, "text": text})

    print(f"[sensevoice] Segments: {len(segments)}  total={duration_total:.1f}s")

    if max_seg_sec > 0:
        segments = _resegment_by_sentences(segments, max_seg_sec)

    text = " ".join(s["text"] for s in segments)
    return {"text": text, "segments": segments}


# ── Backend: Paraformer-zh (non-autoregressive CIF, RTF~0.008) ──────────────────

def transcribe_paraformer(audio_path: Path, language: str = "zh",
                           max_seg_sec: float = 0.0) -> dict:
    """
    Paraformer-zh via FunASR — non-autoregressive, RTF~0.0076.
    Model:  iic/paraformer-zh (ModelScope, ~220M)
    Output: Simplified Chinese → OpenCC s2tw applied by main pipeline
    """
    try:
        from funasr import AutoModel as FunASRAutoModel
        import torch
        import librosa
    except ImportError:
        raise RuntimeError("paraformer requires: pip install funasr torch torchaudio librosa")

    # FunASR short name — registry key is "paraformer-zh" (not "iic/paraformer-zh")
    # iic/paraformer-zh causes "not registered" because FunASR registry uses short names
    MODEL_SHORT = "paraformer-zh"
    print(f"[paraformer] Model: {MODEL_SHORT}")
    print(f"[paraformer] Transcribing {audio_path.name} ...")

    device = "cpu"  # paraformer-zh not verified on MPS — CPU is fast enough (RTF~0.008)

    import os as _os

    # Ensure HF token is visible to huggingface_hub (older versions use HUGGING_FACE_HUB_TOKEN)
    _hf_token = _os.environ.get("HF_TOKEN", "")
    if _hf_token:
        _os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", _hf_token)

    # hub_configs: (hub, MODELSCOPE_DOMAIN)
    # ms: try international modelscope.ai (www.modelscope.cn 404s in Taiwan)
    # hf: FunASR resolves "paraformer-zh" → iic/paraformer-zh on HuggingFace
    hub_configs = [
        ("ms", "modelscope.ai"),
        ("hf", ""),
    ]
    pf_model = None
    for hub, ms_domain in hub_configs:
        try:
            if ms_domain:
                _os.environ["MODELSCOPE_DOMAIN"] = ms_domain
            pf_model = FunASRAutoModel(
                model=MODEL_SHORT,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                punc_model="ct-punc",
                trust_remote_code=True,
                device=device,
                disable_update=True,
                hub=hub,
            )
            print(f"[paraformer] Loaded from hub={hub} domain={ms_domain or 'huggingface.co'}")
            break
        except Exception as e:
            print(f"[paraformer] hub={hub} failed: {e}")
    if pf_model is None:
        raise RuntimeError("paraformer: model load failed from modelscope.ai and HuggingFace")

    audio_full, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    duration_total = len(audio_full) / 16000

    raw_result = pf_model.generate(
        input=audio_full,
        cache={},
        language=language,
        use_itn=True,
        batch_size_s=300,
        merge_vad=True,
        merge_length_s=15,
    )

    segments = []
    for item in (raw_result or []):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        ts = item.get("timestamp")
        if ts and isinstance(ts, (list, tuple)) and len(ts) > 0:
            first = ts[0] if isinstance(ts[0], (list, tuple)) else ts
            last  = ts[-1] if isinstance(ts[-1], (list, tuple)) else ts
            t_start = first[0] / 1000.0
            t_end   = last[-1] / 1000.0
        else:
            t_start, t_end = 0.0, duration_total
        segments.append({"start": t_start, "end": t_end, "text": text})

    print(f"[paraformer] Segments: {len(segments)}  total={duration_total:.1f}s")

    if max_seg_sec > 0:
        segments = _resegment_by_sentences(segments, max_seg_sec)

    text = " ".join(s["text"] for s in segments)
    return {"text": text, "segments": segments}


# ── Backend: mlx-qwen3-asr (MLX native, Apple Silicon, 0.6B/1.7B) ──────────────

def transcribe_mlx_qwen3(audio_path: Path, language: str = "zh",
                          max_seg_sec: float = 0.0,
                          model_id: str = "Qwen/Qwen3-ASR-0.6B") -> dict:
    """
    Qwen3-ASR via mlx-qwen3-asr — pure MLX, no PyTorch/CUDA, RTF~0.08x on M4.
    Model:  Qwen/Qwen3-ASR-0.6B (default, ~1.2 GB) or Qwen/Qwen3-ASR-1.7B (~3.4 GB)
    Install: pip install mlx-qwen3-asr
    Output: may be Simplified Chinese → OpenCC s2tw applied by main pipeline
    """
    try:
        from mlx_qwen3_asr import Session
    except ImportError:
        raise RuntimeError("mlx-qwen3-asr requires: pip install mlx-qwen3-asr")

    print(f"[mlx-qwen3] Model: {model_id}")
    print(f"[mlx-qwen3] Transcribing {audio_path.name} ...")

    import librosa
    audio_full, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    duration_total = len(audio_full) / 16000

    session = Session(model=model_id)
    raw = session.transcribe(audio_full)

    # mlx-qwen3-asr returns a result object with .text and optionally .segments
    segments = []
    if hasattr(raw, "segments") and raw.segments:
        for seg in raw.segments:
            t_start = getattr(seg, "start", 0.0)
            t_end   = getattr(seg, "end", duration_total)
            text    = (getattr(seg, "text", "") or "").strip()
            if text:
                segments.append({"start": t_start, "end": t_end, "text": text})
    else:
        # fallback: single segment for full audio
        text = (getattr(raw, "text", "") or "").strip()
        if text:
            segments = [{"start": 0.0, "end": duration_total, "text": text}]

    print(f"[mlx-qwen3] Segments: {len(segments)}  total={duration_total:.1f}s")

    if max_seg_sec > 0:
        segments = _resegment_by_sentences(segments, max_seg_sec)

    text = " ".join(s["text"] for s in segments)
    return {"text": text, "segments": segments}


# ── Backend: Qwen3-ASR (LLM-based, 52 languages + 22 Chinese dialects) ────────

def transcribe_qwen3_asr(audio_path: Path, language: str = "zh",
                          max_seg_sec: float = 0.0) -> dict:
    """
    Transcribe using Qwen3-ASR-1.7B via transformers (Alibaba Qwen team).
    Architecture: LLM-based encoder-decoder, completely different from Whisper.
    Supports 52 languages + 22 Chinese dialects (Mandarin, Taiwanese, Cantonese…).

    Install: pip install transformers librosa accelerate torch
    Model:   Qwen/Qwen3-ASR-1.7B (auto-downloaded from HuggingFace, ~3.2 GB)
    """
    try:
        from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration
        import torch
        import librosa
    except ImportError:
        raise RuntimeError(
            "qwen3-asr requires: pip install transformers librosa accelerate torch"
        )

    MODEL_ID = "Qwen/Qwen3-ASR-1.7B"
    print(f"[qwen3-asr] Model: {MODEL_ID}")
    print(f"[qwen3-asr] Transcribing {audio_path.name} ...")

    audio_full, _ = librosa.load(str(audio_path), sr=16000, mono=True)
    duration_total = len(audio_full) / 16000

    # Qwen2AudioForConditionalGeneration bypasses AutoConfig (which blocks on
    # unknown model type qwen3_asr). The model loads with UNEXPECTED thinker.*
    # keys (ignored) but the base Qwen2-Audio weights are fully compatible.
    torch_dtype = torch.float16 if torch.backends.mps.is_available() else "auto"
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = Qwen2AudioForConditionalGeneration.from_pretrained(
        MODEL_ID, device_map="auto", torch_dtype=torch_dtype, trust_remote_code=True
    )
    model.eval()

    # Build prompt manually — Qwen3-ASR processor has no chat_template so
    # apply_chat_template() fails. Construct the Qwen2-Audio format directly.
    # <|AUDIO|> is the placeholder that processor replaces with audio embeddings.
    PROMPT = (
        "<|im_start|>user\n"
        "Audio 1: <|audio_bos|><|AUDIO|><|audio_eos|>\n"
        "請轉錄音頻的繁體中文內容，只輸出逐字稿，不要添加解釋或標題。<|im_end|>\n"
        "<|im_start|>assistant\n"
    )

    CHUNK_SEC   = 28        # stay within 30s model context
    chunk_len   = CHUNK_SEC * 16000
    segments    = []
    chunk_count = 0

    for offset in range(0, len(audio_full), chunk_len):
        chunk   = audio_full[offset : offset + chunk_len]
        t_start = offset / 16000
        t_end   = min(t_start + CHUNK_SEC, duration_total)

        inputs = processor(
            text=[PROMPT], audios=[chunk], sampling_rate=16000,
            return_tensors="pt", padding=True,
        ).to(model.device)

        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=512)

        out_ids  = generated[:, inputs["input_ids"].shape[1]:]
        text_out = processor.batch_decode(out_ids, skip_special_tokens=True)[0].strip()
        if text_out:
            segments.append({"start": t_start, "end": t_end, "text": text_out})
        chunk_count += 1

    print(f"[qwen3-asr] Chunks processed: {chunk_count} × {CHUNK_SEC}s  "
          f"total={duration_total:.1f}s")

    if max_seg_sec > 0:
        # Qwen3-ASR returns chunk-level segments; apply sentence-boundary split
        segments = _resegment_by_sentences(segments, max_seg_sec)

    text = " ".join(s["text"] for s in segments)
    return {"text": text, "segments": segments}


def _resegment_by_sentences(segments: list, max_seg_sec: float) -> list:
    """Split chunk-level segments at sentence boundaries (。！？) to honour max_seg_sec.
    Used for Qwen3-ASR which returns 28s chunk segments without word timestamps.
    """
    import re
    out = []
    for seg in segments:
        dur = seg["end"] - seg["start"]
        if dur <= max_seg_sec:
            out.append(seg)
            continue
        # Split text at 。！？ boundaries
        parts = re.split(r"(?<=[。！？])", seg["text"])
        parts = [p for p in parts if p.strip()]
        if len(parts) <= 1:
            out.append(seg)
            continue
        # Distribute time proportionally by character count
        total_chars = sum(len(p) for p in parts)
        t = seg["start"]
        for part in parts:
            frac = len(part) / total_chars if total_chars else 1 / len(parts)
            t_end = t + dur * frac
            out.append({"start": round(t, 3), "end": round(t_end, 3), "text": part.strip()})
            t = t_end
    return out


# ── Dedup helper ──────────────────────────────────────────────────────────────

def _dedup_text(result: dict) -> str:
    """Return deduplicated, Traditional-Chinese-converted transcript text."""
    parts, prev = [], None
    for seg in result.get("segments", []):
        t = seg.get("text", "").strip()
        if _OPENCC:
            t = _OPENCC.convert(t)
        if t and t != prev:
            parts.append(t)
            prev = t
    if parts:
        return "".join(parts)
    raw = result.get("text", "")
    return _OPENCC.convert(raw) if _OPENCC and raw else raw


# ── Transcript Writer ─────────────────────────────────────────────────────────

def save_transcript(audio_path: Path, result: dict, backend: str,
                    model: str, rtf: float, duration: float,
                    json_dir: Path = None, exp_label: str = None,
                    model_repo: str | None = None) -> Path:
    """Save .srt transcript with Metadata. If json_dir given, writes .srt there (sandbox); otherwise alongside audio."""
    stem     = audio_path.stem + (f"_{exp_label}" if exp_label else "")
    out_dir  = json_dir if json_dir is not None else audio_path.parent

    # Filter out empty, duplicate, and hallucinated segments
    def _is_valid(seg: dict) -> bool:
        text = seg.get("text", "").strip()
        if not text:
            return False
        # Skip if > 50% characters are non-CJK non-ASCII (e.g. Hebrew hallucinations)
        non_normal = sum(1 for c in text if ord(c) > 0x05FF and not (0x4E00 <= ord(c) <= 0x9FFF) and not (0x3400 <= ord(c) <= 0x4DBF))
        if len(text) > 0 and non_normal / len(text) > 0.5:
            return False
        # Skip repetition loops (e.g. "Confeder Confeder Confeder")
        words = text.split()
        if len(words) >= 3:
            most_common_count = max(words.count(w) for w in set(words))
            if most_common_count / len(words) > 0.6:
                return False
        return True

    def _to_trad(text: str) -> str:
        return _OPENCC.convert(text) if _OPENCC else text

    raw_segments = result.get("segments", [])
    # Deduplicate consecutive identical texts, convert to Traditional Chinese
    segments, prev_text = [], None
    for seg in raw_segments:
        if not _is_valid(seg):
            continue
        text = _to_trad(seg.get("text", "").strip())
        if text != prev_text:
            seg = dict(seg, text=text)
            segments.append(seg)
            prev_text = text

    # Also convert full text
    if _OPENCC and result.get("text"):
        result = dict(result, text=_OPENCC.convert(result["text"]))

    # ── .srt transcript (Metadata Style) ──────────────────────────────────────
    srt_path = out_dir / f"{stem}.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        # Metadata block
        f.write("[METADATA]\n")
        f.write(f"Source: {audio_path.name}\n")
        f.write(f"Provider: {backend}\n")
        f.write(f"Model: {model}\n")
        if model_repo:
            f.write(f"Model-Repo: {model_repo}\n")
        f.write(f"Duration: {duration/60:.1f} min ({duration:.0f}s)\n")
        f.write(f"Transcription-Time: {rtf * duration:.1f}s\n")
        f.write(f"RTF: {rtf:.3f}\n")
        f.write(f"Generated-At: {datetime.now(_CST).strftime('%Y-%m-%d %H:%M CST')}\n")
        f.write("---\n\n")

        # Segmented body (timestamp + text per segment) or plain fallback
        if segments:
            for seg in segments:
                start = seg.get("start", 0.0)
                text  = seg.get("text",  "").strip()
                mm = int(start // 60)
                ss = int(start % 60)
                ms = int(round((start % 1) * 1000))
                # Format: (MM:SS.mmm)
                f.write(f"({mm:02d}:{ss:02d}.{ms:03d}) {text}\n")
        else:
            # No segments — write full text with paragraph breaks every ~500 chars
            text = result.get("text", "").strip()
            words = text.split()
            line, lines = [], []
            for w in words:
                line.append(w)
                if len(" ".join(line)) >= 500 and w.endswith((".", "?", "!", "。", "？", "！")):
                    lines.append(" ".join(line))
                    line = []
            if line:
                lines.append(" ".join(line))
            f.write("\n\n".join(lines))

    print(f"[out] Transcript → {srt_path}")

    # ── JSON segments (optional, only if json_dir specified) ──────────────────
    if segments and json_dir is not None:
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{stem}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"model": model, "provider": backend, "backend": backend,
                       "model_repo": model_repo or "",
                       "rtf": rtf, "segments": segments},
                      f, ensure_ascii=False, indent=2)
        print(f"[out] Segments  → {json_path}")

    return srt_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WhisperKit / MLX-Whisper POC — Mac-mini M4 ANE"
    )
    parser.add_argument("audio", help="Path to .m4a / .mp3 / .wav file")
    parser.add_argument(
        "--model", default="distil-whisper-large-v3",
        help="Model name (default: distil-whisper-large-v3)"
    )
    parser.add_argument(
        "--backend", choices=["mlx", "whisperkittools", "faster-whisper", "qwen3-asr", "sensevoice", "paraformer", "mlx-qwen3", "auto"], default="auto",
        help="Backend to use (default: auto — tries mlx first)"
    )
    parser.add_argument(
        "--language", default=None,
        help="Language code (e.g. zh, en). Default: auto-detect."
    )
    parser.add_argument(
        "--initial-prompt", default=None,
        help="Initial prompt to bias output (e.g. use Traditional Chinese text to force 繁體字)."
    )
    parser.add_argument(
        "--company-config", default=None,
        help="Path to company whisper.yaml config file for domain-specific vocabulary"
    )
    parser.add_argument(
        "--json-dir", default=None,
        help="Directory to save .json segments file. Omit to skip JSON output."
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="Decoding temperature (default: 0.0 — greedy)"
    )
    parser.add_argument(
        "--no-speech-threshold", type=float, default=0.6,
        help="Probability threshold to skip silence segments (default: 0.6)"
    )
    parser.add_argument(
        "--compression-ratio-threshold", type=float, default=2.4,
        help="Threshold to discard hallucinated repetitions (default: 2.4)"
    )
    parser.add_argument(
        "--beam-size", type=int, default=5,
        help="Beam size for faster-whisper (default: 5; use 1 for greedy/no-hallucination)"
    )
    parser.add_argument(
        "--vad-min-silence-ms", type=int, default=500,
        help="VAD min silence duration in ms for faster-whisper (default: 500; lower=more segments)"
    )
    parser.add_argument(
        "--max-seg-sec", type=float, default=0.0,
        help="Split segments longer than N seconds: pass1=。！？ pass2=，using word timestamps (0=disabled; works for both mlx and faster-whisper)"
    )
    parser.add_argument(
        "--extra-prompt", default=None,
        help="Additional text appended to company-config initial_prompt (e.g. quarterly-specific terms)"
    )
    parser.add_argument(
        "--prompt-max-chars", type=int, default=200,
        help="Budget (chars) for build_prompt_from_config (default 200; increase to fit more terms+examples)"
    )
    parser.add_argument(
        "--no-prompt", action="store_true",
        help="Disable initial_prompt even when --company-config is set (used for exp0 no-prompt baseline)"
    )
    parser.add_argument(
        "--use-english-prompt-layers", action="store_true",
        help="Opt in to layered English prompt configs (generic whisper-en.yaml + company whisper-en.yaml)"
    )
    parser.add_argument(
        "--exp-label", default=None,
        help="Experiment label appended to output filename (e.g. exp1 → *_exp1.md)"
    )
    args = parser.parse_args()

    # ── Apply company config (only if explicit args were NOT provided) ─────────
    if args.company_config is not None:
        config_path = Path(args.company_config)
        # cwd-relative (not __file__-relative): these live in mlx-api-server-whisper/ as
        # data/config that grows over time, independent of where this script itself lives.
        generic_config_path = Path("mlx-api-server-whisper/whisper.yaml")
        generic_en_config_path = Path("mlx-api-server-whisper/whisper-en.yaml")
        if not config_path.exists():
            if generic_config_path.exists():
                print(
                    f"WARN: Company config not found: {config_path} "
                    f"-> fallback to generic config: {generic_config_path}"
                )
                config_path = generic_config_path
            else:
                print(
                    f"ERROR: Company config not found: {config_path} "
                    f"(generic fallback also missing: {generic_config_path})"
                )
                sys.exit(1)
        try:
            base_cfg = _load_yaml_config(config_path)
            cfg_language = base_cfg.get("language", "zh")
            effective_language = args.language or cfg_language
            prompt_paths = [config_path]
            if effective_language == "en" and args.use_english_prompt_layers:
                company_en_config_path = config_path.with_name("whisper-en.yaml")
                english_layers = []
                if generic_en_config_path.exists():
                    english_layers.append(generic_en_config_path)
                if company_en_config_path.exists():
                    english_layers.append(company_en_config_path)
                if english_layers:
                    prompt_paths.extend(english_layers)
                    print("[config] English prompt layering enabled: " + ", ".join(path.name for path in english_layers))
            cfg_language, cfg_prompt = build_prompt_from_config(prompt_paths, max_chars=args.prompt_max_chars)
            if args.language is None:
                if cfg_language in ["mixed", "auto"]:
                    args.language = None
                else:
                    args.language = cfg_language
                print(f"[config] Language set from config: {args.language} (raw={cfg_language})")
            if args.initial_prompt is None and not args.no_prompt:
                args.initial_prompt = cfg_prompt
                print(f"[config] Initial prompt set from config ({', '.join(path.name for path in prompt_paths)})")
            elif args.no_prompt:
                print("[config] Initial prompt disabled (--no-prompt / exp0 baseline)")
        except Exception as e:
            print(f"ERROR: Failed to load company config: {e}")
            sys.exit(1)

    # ── Append extra_prompt (quarterly-specific terms) ─────────────────────
    if args.extra_prompt:
        args.initial_prompt = (args.initial_prompt or "") + args.extra_prompt
        print(f"[config] Extra prompt appended ({len(args.extra_prompt)} chars)")

    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: File not found: {audio_path}")
        sys.exit(1)

    print(f"\n=== Whisper POC — {audio_path.name} ===")
    hw = check_hardware()

    duration = get_audio_duration(audio_path)
    if duration:
        print(f"[audio] Duration: {duration/60:.1f} min ({duration:.0f}s)")

    # ── Select backend ────────────────────────────────────────────────────────
    backend_used = None
    result = None

    def try_mlx():
        nonlocal result, backend_used
        t0 = time.monotonic()
        result = transcribe_mlx(
            audio_path, args.model, args.language, args.initial_prompt,
            temperature=args.temperature,
            no_speech_threshold=args.no_speech_threshold,
            compression_ratio_threshold=args.compression_ratio_threshold,
            max_seg_sec=args.max_seg_sec,
        )
        elapsed = time.monotonic() - t0
        backend_used = "mlx-whisper"
        return elapsed

    def try_wkt():
        nonlocal result, backend_used
        t0 = time.monotonic()
        result = transcribe_whisperkittools(audio_path, args.model, args.language, args.initial_prompt)
        elapsed = time.monotonic() - t0
        backend_used = "whisperkittools"
        return elapsed

    def try_fw():
        nonlocal result, backend_used
        t0 = time.monotonic()
        result = transcribe_faster_whisper(
            audio_path, args.model, args.language, args.initial_prompt,
            no_speech_threshold=args.no_speech_threshold,
            compression_ratio_threshold=args.compression_ratio_threshold,
            beam_size=args.beam_size,
            vad_min_silence_ms=args.vad_min_silence_ms,
            max_seg_sec=args.max_seg_sec,
        )
        elapsed = time.monotonic() - t0
        backend_used = "faster-whisper"
        return elapsed

    def try_sensevoice():
        nonlocal result, backend_used
        t0 = time.monotonic()
        result = transcribe_sensevoice(
            audio_path,
            language=args.language or "zh",
            max_seg_sec=args.max_seg_sec,
        )
        elapsed = time.monotonic() - t0
        backend_used = "sensevoice"
        return elapsed

    def try_paraformer():
        nonlocal result, backend_used
        t0 = time.monotonic()
        try:
            result = transcribe_paraformer(
                audio_path,
                language=args.language or "zh",
                max_seg_sec=args.max_seg_sec,
            )
        except Exception as e:
            print(f"[paraformer] ⚠ Failed: {e}")
            print("[paraformer] Skipping — no output file written.")
            raise SystemExit(0)
        elapsed = time.monotonic() - t0
        backend_used = "paraformer"
        return elapsed

    def try_mlx_qwen3():
        nonlocal result, backend_used
        t0 = time.monotonic()
        try:
            result = transcribe_mlx_qwen3(
                audio_path,
                language=args.language or "zh",
                max_seg_sec=args.max_seg_sec,
            )
        except Exception as e:
            print(f"[mlx-qwen3] ⚠ Failed: {e}")
            print("[mlx-qwen3] Skipping — no output file written.")
            raise SystemExit(0)
        elapsed = time.monotonic() - t0
        backend_used = "mlx-qwen3"
        return elapsed

    def try_qwen3():
        nonlocal result, backend_used
        t0 = time.monotonic()
        try:
            result = transcribe_qwen3_asr(
                audio_path,
                language=args.language or "zh",
                max_seg_sec=args.max_seg_sec,
            )
        except Exception as e:
            print(f"[qwen3-asr] ⚠ Failed: {e}")
            print("[qwen3-asr] Skipping — no output file written.")
            raise SystemExit(0)
        elapsed = time.monotonic() - t0
        backend_used = "qwen3-asr"
        return elapsed

    # ── Amplitude tracker（backend 確定後填入，成功後更新 result/rtf）────────
    _tracker = (
        WhisperCallTracker(
            backend="pending",
            model=args.model,
            model_repo="",
            audio_file=audio_path.name,
            language=args.language,
            audio_duration=duration,
        )
        if WhisperCallTracker is not None else None
    )

    elapsed = 0.0
    rtf = 0.0
    _tracker_ctx = _tracker if _tracker is not None else _NullContext()
    with _tracker_ctx:
        if args.backend == "mlx":
            elapsed = try_mlx()
        elif args.backend == "whisperkittools":
            elapsed = try_wkt()
        elif args.backend == "faster-whisper":
            elapsed = try_fw()
        elif args.backend == "sensevoice":
            elapsed = try_sensevoice()
        elif args.backend == "paraformer":
            elapsed = try_paraformer()
        elif args.backend == "mlx-qwen3":
            elapsed = try_mlx_qwen3()
        elif args.backend == "qwen3-asr":
            elapsed = try_qwen3()
        else:  # auto
            try:
                elapsed = try_mlx()
            except RuntimeError as e:
                print(f"[auto] mlx-whisper unavailable ({e}), trying whisperkittools...")
                try:
                    elapsed = try_wkt()
                except RuntimeError as e2:
                    print(f"[auto] whisperkittools unavailable ({e2})")
                    print("\nInstall one of:")
                    print("  pip install mlx-whisper")
                    print("  pip install whisperkittools")
                    sys.exit(1)

        # 計算 RTF 並更新 tracker（__exit__ 觸發前完成）
        rtf = (elapsed / duration) if duration else 0.0
        if _tracker is not None:
            _tracker.backend = backend_used or "unknown"
            tracked_model, tracked_model_repo = _resolve_tracking_model_info(_tracker.backend, args.model)
            _tracker.model = tracked_model
            _tracker.model_repo = tracked_model_repo
            _tracker.result = _dedup_text(result) if result else ""
            _tracker.rtf = rtf

    # ── Performance Report ────────────────────────────────────────────────────
    deduped = _dedup_text(result)
    chars = len(deduped.replace(" ", ""))
    cpm = (chars / (elapsed / 60)) if elapsed > 0 else 0

    print(f"\n{'='*50}")
    tracked_model, tracked_model_repo = _resolve_tracking_model_info(backend_used or "unknown", args.model)
    print(f"Provider : {backend_used}")
    print(f"Model    : {tracked_model}")
    if tracked_model_repo:
        print(f"ModelRepo: {tracked_model_repo}")
    print(f"Duration : {duration/60:.1f} min")
    print(f"Elapsed  : {elapsed:.1f}s")
    print(f"RTF      : {rtf:.3f}  (transcription / audio duration)")

    if rtf < 0.15:
        print(f"ANE      : ✓ CONFIRMED — M4 Neural Engine active (RTF {rtf:.3f} << 0.15)")
    elif rtf < 0.5:
        print(f"ANE      : ✓ Likely ANE/GPU accelerated (RTF {rtf:.3f})")
    elif rtf < 1.0:
        print(f"ANE      : ~ Partial acceleration (RTF {rtf:.3f})")
    else:
        print(f"ANE      : ✗ No acceleration detected — check native ARM64 Python")

    print(f"Chars    : {chars}  ({cpm:.0f} chars/min processed)")
    print(f"Preview  : {deduped[:200].strip()} ...")
    print(f"{'='*50}\n")

    # ── Save output ───────────────────────────────────────────────────────────
    json_dir = Path(args.json_dir) if args.json_dir else None
    save_transcript(audio_path, result, backend_used, tracked_model, rtf, duration, json_dir,
                    exp_label=args.exp_label, model_repo=tracked_model_repo)


if __name__ == "__main__":
    main()
