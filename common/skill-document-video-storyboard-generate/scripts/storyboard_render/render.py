"""Render a storyboard (JSON or master-prompt text) to MP4 + SRT.

  python -m storyboard_render storyboard.json                 # full render -> storyboard.mp4 + .srt
  python -m storyboard_render master_prompt.txt --out demo.mp4
  python -m storyboard_render storyboard.json --preview       # PNG stills per scene
  python -m storyboard_render storyboard.json --scenes 2 3    # partial render
  python -m storyboard_render storyboard.json --no-tts        # silent, planned durations (offline check)

Requires: pycairo, numpy, edge-tts (unless --no-tts), ffmpeg on PATH.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import cairo
import numpy as np

from . import layouts
from .core import FPS, H, W, clamp, configure, eio, subtitle
from .loader import load

VO_LEAD, TAIL, XFADE, SR = 0.45, 0.8, 0.5, 48000
CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


# ------------------------------------------------------------------ voice
async def _tts(text, voice, rate, mp3):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append([ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]])
    return words


def synth(text, voice, rate, build):
    """TTS with a content-addressed cache. Returns (mono float32 @SR, word boundaries)."""
    if not text.strip():
        return np.zeros(0, np.float32), []
    key = hashlib.sha1(("%s|%s|%s" % (voice, rate, text)).encode("utf-8")).hexdigest()[:16]
    mp3, wav, wj = (os.path.join(build, "vo_%s.%s" % (key, e)) for e in ("mp3", "wav", "json"))
    if not (os.path.exists(wav) and os.path.exists(wj)):
        print("  TTS [%s] %s" % (voice, text[:50]))
        words = asyncio.run(_tts(text, voice, rate, mp3))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ac", "1", "-ar", str(SR), wav], check=True)
        json.dump(words, open(wj, "w", encoding="utf-8"), ensure_ascii=False)
    with wave.open(wav) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return data, json.load(open(wj, encoding="utf-8"))


# ------------------------------------------------------------------ subtitles
def chunk_vo(text):
    cjk = bool(CJK.search(text))
    maxc = 20 if cjk else 64
    parts = [p for p in re.split(r"(?<=[.!?:,;\u2014\u3002\uff0c\uff01\uff1f\u3001\uff1b\uff1a])\s*", text) if p.strip()]
    chunks, cur = [], ""
    for p in parts:
        sep = "" if cjk or cur.endswith("\u2014") else " "
        if not cur or len(cur) + len(p) + len(sep) <= maxc:
            cur = (cur + sep + p).strip() if cur else p.strip()
        else:
            chunks.append(cur)
            cur = p.strip()
    if cur:
        chunks.append(cur)
    out = []
    for c in chunks:  # hard-split anything still too long
        while len(c) > maxc * 1.4:
            cut = maxc if cjk else (c.rfind(" ", 0, maxc) if c.rfind(" ", 0, maxc) > 0 else maxc)
            out.append(c[:cut].strip())
            c = c[cut:].strip()
        out.append(c)
    return out


def subtitle_cues(text, start, words, audio_dur):
    chunks = chunk_vo(text)
    if not chunks:
        return []
    pos, wpos = 0, []
    for w in words:  # locate each spoken word in the source text
        i = text.find(w[2], pos)
        wpos.append(i if i >= 0 else pos)
        pos = i + len(w[2]) if i >= 0 else pos
    cues, cpos = [], 0
    for c in chunks:
        ci = text.find(c[: max(1, min(4, len(c)))], cpos)
        ci = ci if ci >= 0 else cpos
        s = next((w[0] for w, p in zip(words, wpos) if p >= ci), None)
        if s is None:
            s = audio_dur * ci / max(len(text), 1)
        cues.append([start + VO_LEAD + s, None, c])
        cpos = ci + len(c)
    for i in range(len(cues) - 1):
        cues[i][1] = cues[i + 1][0]
    cues[-1][1] = start + VO_LEAD + audio_dur + 0.4
    return [c for c in cues if c[1] > c[0]]


def fmt_ts(s):
    ms = int(round(s * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def write_srt(timeline, path):
    i = 1
    with open(path, "w", encoding="utf-8") as f:
        for sc in timeline:
            for s, e, c in sc["cues"]:
                f.write("%d\n%s --> %s\n%s\n\n" % (i, fmt_ts(s), fmt_ts(e), c))
                i += 1


# ------------------------------------------------------------------ music & sfx
def music(total):
    n = int(total * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    hz = lambda semi: 440.0 * 2 ** (semi / 12)
    chords = [[-24, -17, -13, -8], [-27, -20, -15, -10], [-31, -24, -19, -12], [-29, -22, -17, -10]]
    seg = 4.0
    for k in range(int(total / seg) + 1):
        chord = chords[k % 4]
        s0 = int(k * seg * SR)
        s1 = min(n, int((k + 1) * seg * SR + 1.5 * SR))
        if s0 >= n:
            break
        tt = t[s0:s1] - k * seg
        env = np.clip(tt / 1.2, 0, 1) * np.clip((seg + 1.5 - tt) / 1.5, 0, 1)
        for semi in chord:
            f = hz(semi)
            out[s0:s1] += 0.05 * env * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * f * 2.003 * tt))
        for j, semi in enumerate(chord + [chord[1] + 12]):
            b0 = s0 + int(j * 0.8 * SR)
            b1 = min(n, b0 + int(2.0 * SR))
            if b0 >= n:
                continue
            bt = np.arange(b1 - b0) / SR
            out[b0:b1] += 0.022 * np.exp(-bt * 3) * np.sin(2 * np.pi * hz(semi + 24) * bt)
    return out * np.clip(t / 1.5, 0, 1) * np.clip((total - t) / 2.5, 0, 1)


def _tt(d):
    return np.arange(int(d * SR)) / SR


SFX = {
    "chime": lambda: 0.10 * np.exp(-_tt(1.6) * 3) * sum(np.sin(2 * np.pi * f * _tt(1.6)) for f in (880, 1318.5, 1760)),
    "thud": lambda: 0.55 * np.exp(-_tt(0.5) * 14) * np.sin(2 * np.pi * (90 - 40 * _tt(0.5)) * _tt(0.5)),
    "pop": lambda: 0.25 * np.exp(-_tt(0.25) * 30) * np.sin(2 * np.pi * (600 + 900 * _tt(0.25)) * _tt(0.25)),
    "whoosh": lambda: 0.12 * np.sin(np.pi * _tt(0.6) / 0.6)
    * np.convolve(np.random.default_rng(3).standard_normal(len(_tt(0.6))), np.ones(24) / 24, "same"),
}


def mix_audio(timeline, total, path, with_music=True):
    n = int(total * SR) + SR
    vo = np.zeros(n, np.float32)
    fx = np.zeros(n, np.float32)
    for sc in timeline:
        s = int((sc["start"] + VO_LEAD) * SR)
        vo[s:s + len(sc["audio"])] += sc["audio"][: max(0, n - s)]
        name = sc.get("sfx")
        if name in SFX:
            clip = SFX[name]().astype(np.float32)
            a = int((sc["start"] + float(sc.get("sfx_at", 0.3))) * SR)
            fx[a:a + len(clip)] += clip[: max(0, n - a)]
    m = np.zeros(n, np.float32)
    if with_music:
        m[: int(total * SR)] = music(total)
    k = int(0.4 * SR)
    cs = np.cumsum(np.concatenate([[0], np.abs(vo)]))
    sm = (cs[k:] - cs[:-k]) / k
    sm = np.concatenate([sm, np.full(n - len(sm), sm[-1] if len(sm) else 0)])
    duck = 1.0 - 0.55 * np.clip(sm * 12, 0, 1)
    peak = np.max(np.abs(vo)) or 1
    mixv = np.tanh((vo * (0.89 / peak) + m * duck * 0.9 + fx) * 1.05)
    st = np.stack([mixv, mixv], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(st, -1, 1) * 32767).astype(np.int16).tobytes())


# ------------------------------------------------------------------ timeline / frames
def build_timeline(sb, build, tts=True):
    tl, cur = [], 0.0
    total_n = len(sb["scenes"])
    for i, sc in enumerate(sb["scenes"]):
        text = sc.get("voiceover", "")
        data, words = synth(text, sb["voice"], sb.get("rate", "+0%"), build) if tts else (np.zeros(0, np.float32), [])
        ad = len(data) / SR
        dur = max(float(sc["duration"]), VO_LEAD + ad + TAIL if ad else 0, 2.0)
        e = dict(sc, start=cur, dur=dur, audio=data, audio_dur=ad, fn=layouts.resolve(sc, i, total_n))
        if i == 0 and "sfx" not in sc:
            e["sfx"] = "chime"
        show_subs = sb.get("subtitles", True) and sc.get("subtitles", True)
        e["cues"] = subtitle_cues(text, cur, words, ad or max(dur - VO_LEAD - TAIL, 1)) if show_subs and text else []
        tl.append(e)
        cur += dur
    return tl, cur


def draw_frame(ctx, sc, T, env):
    t = T - sc["start"]
    ctx.save()
    sc["fn"](ctx, t, sc["dur"], sc, env)
    ctx.restore()
    for s, e, c in sc["cues"]:
        if s - 0.12 <= T < e:
            subtitle(ctx, c, clamp(min((T - s + 0.12) / 0.15, (e - T) / 0.15)))


def verify_mp4(path):
    """Fully decode the file; return decoder error lines (empty = clean)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", path, "-f", "null", "-"],
                       capture_output=True, text=True)
    return [ln for ln in r.stderr.splitlines() if ln.strip()]


def render(timeline, total, final_out, audio_wav, env):
    # Encode in a local temp dir, verify, then atomically move into place. Writing straight into a
    # synced folder (SynologyDrive/OneDrive/Dropbox) can corrupt packets mid-encode.
    tmp_dir = tempfile.mkdtemp(prefix="storyboard_render_")
    out = os.path.join(tmp_dir, os.path.basename(final_out))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    prev = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    pctx = cairo.Context(prev)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-", "-i", audio_wav, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int(math.ceil(total * FPS))
    si, have_prev = 0, False
    for i in range(nframes):
        T = i / FPS
        while si < len(timeline) - 1 and T >= timeline[si]["start"] + timeline[si]["dur"]:
            si += 1
        sc = timeline[si]
        draw_frame(ctx, sc, T, env)
        t = T - sc["start"]
        if have_prev and t < XFADE and si > 0:
            ctx.set_source_surface(prev, 0, 0)
            ctx.paint_with_alpha(1 - eio(t / XFADE))
        surf.flush()
        proc.stdin.write(surf.get_data())
        if (i + 1) / FPS >= sc["start"] + sc["dur"] and si < len(timeline) - 1:
            draw_frame(pctx, sc, T, env)
            have_prev = True
        if i % (FPS * 5) == 0:
            print("  frame %d/%d  (scene %s)" % (i, nframes, sc["id"]), flush=True)
    proc.stdin.close()
    proc.wait()
    if proc.returncode:
        raise SystemExit("ffmpeg failed")
    errs = verify_mp4(out)
    if errs:
        raise SystemExit("Encoded file failed decode check (kept at %s):\n%s" % (out, "\n".join(errs[:10])))
    shutil.copyfile(out, final_out + ".part")
    os.replace(final_out + ".part", final_out)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    errs = verify_mp4(final_out)
    if errs:
        raise SystemExit("Copied file is corrupt (sync interference?):\n%s" % "\n".join(errs[:10]))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # CJK titles on cp1252/cp950 consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="storyboard_render", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="storyboard .json or master-prompt .txt/.md")
    ap.add_argument("--out", help="output .mp4 (default: next to input)")
    ap.add_argument("--build", help="cache/preview dir (default: build_<name> next to output)")
    ap.add_argument("--voice", help="edge-tts voice, e.g. zh-TW-HsiaoChenNeural / en-US-AndrewNeural")
    ap.add_argument("--rate", help='speech rate, e.g. "+5%%"')
    ap.add_argument("--preview", action="store_true", help="write PNG stills instead of a video")
    ap.add_argument("--at", type=float, nargs="*", default=[0.3, 0.6, 0.95], help="preview points (0-1)")
    ap.add_argument("--scenes", type=int, nargs="*", help="only these scene ids")
    ap.add_argument("--no-tts", action="store_true", help="silent render with planned durations")
    ap.add_argument("--no-music", action="store_true")
    args = ap.parse_args(argv)

    sb = load(args.input)
    if args.voice:
        sb["voice"] = args.voice
    if args.rate:
        sb["rate"] = args.rate
    if str(sb.get("aspect_ratio", "16:9")) != "16:9":
        print("WARNING: renderer outputs 16:9 (1920x1080); aspect_ratio %s ignored" % sb["aspect_ratio"])
    configure(sb.get("palette"), sb.get("fonts"))
    stem = os.path.splitext(os.path.basename(args.input))[0]
    out = os.path.abspath(args.out or os.path.join(sb["base_dir"], stem + ".mp4"))
    build = os.path.abspath(args.build or os.path.join(os.path.dirname(out), "build_" + stem))
    os.makedirs(build, exist_ok=True)
    if args.scenes:
        sb["scenes"] = [s for s in sb["scenes"] if s["id"] in args.scenes] or sb["scenes"]
    env = {"base_dir": sb["base_dir"], "storyboard": sb}
    sys.path.insert(0, sb["base_dir"])  # `custom: "mod:fn"` plug-ins may live next to the storyboard

    print("Loaded %d scenes from %s  (voice %s)" % (len(sb["scenes"]), args.input, sb["voice"]))
    timeline, total = build_timeline(sb, build, tts=not args.no_tts)
    for sc in timeline:
        print("  scene %3s  start %6.2fs  dur %5.2fs  VO %5.2fs  %-9s %s" % (
            sc["id"], sc["start"], sc["dur"], sc["audio_dur"], sc["fn"].__name__, sc.get("title", "")))
    print("Total %.1fs" % total)

    if args.preview:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        ctx = cairo.Context(surf)
        for sc in timeline:
            for f in args.at:
                draw_frame(ctx, sc, sc["start"] + f * sc["dur"], env)
                surf.write_to_png(os.path.join(build, "preview_%02d_%03d.png" % (sc["id"], int(f * 100))))
        print("Previews written to", build)
        return
    wav = os.path.join(build, "mix.wav")
    mix_audio(timeline, total, wav, with_music=not (args.no_music or sb.get("music") is False))
    srt = os.path.splitext(out)[0] + ".srt"
    write_srt(timeline, srt)
    render(timeline, total, out, wav, env)
    print("Done:", out, "|", srt)
