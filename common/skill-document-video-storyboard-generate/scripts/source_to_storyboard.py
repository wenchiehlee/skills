#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_to_storyboard.py — source text / storyboard JSON -> tool-specific video deliverable.

One neutral storyboard (see references/storyboard-schema.md), four adapters:

  --target storyboard   neutral storyboard JSON (default; also what the renderer consumes)
  --target vids         Google Vids / Gemini master-prompt text (paste into Vids "Help me create")
  --target ai-video     per-shot prompts for Veo / Sora / Runway / Kling (--tool picks clip caps)
  --target render       storyboard JSON with layouts resolved, ready for `python -m storyboard_render`
  --target slides       slide outline + speaker notes (Markdown) for PPT / Google Slides

Examples:
  python source_to_storyboard.py -i article.txt --style cinematic                  # draft storyboard JSON
  python source_to_storyboard.py --from-storyboard sb.json --target vids > prompt.txt
  python source_to_storyboard.py --from-storyboard sb.json --target ai-video --tool veo
  python source_to_storyboard.py --from-storyboard sb.json --lint                  # QA only

The draft mode only *structures* facts; the agent (SKILL.md) is expected to rewrite voiceover and
visuals by hand following references/anti-ai-writing-guide.md before shipping.
"""

import argparse
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

AI_SLOP = {
    "zh": ["璀璨的明珠", "劃時代的里程碑", "不可抹滅", "在當今快節奏的世界中", "值得注意的是", "深入探討",
           "令人嘆為觀止", "留給後人無限的啟發", "猶如", "不可忽視", "讓我們一同", "你有沒有想過", "揭開神秘面紗",
           "賦能", "無縫", "顛覆性", "全方位"],
    "en": ["in today's fast-paced world", "it's worth noting", "delve into", "unlock the power", "game-changer",
           "game changer", "revolutionize", "seamless", "cutting-edge", "testament to", "tapestry",
           "ever-evolving", "embark on a journey", "unleash", "elevate your", "let's dive in", "harness the power",
           "in the realm of", "stands as a", "paving the way"],
}
VISUAL_SLOP = ["glowing brain", "neural network background", "hologram", "floating binary", "blue circuit",
               "robot hand shaking human hand", "lens flare", "epic", "4k ultra", "hyper-realistic", "8k"]

# Per-target scene/clip limits (seconds). AI-video caps are conservative defaults — verify against the
# current product docs; override with --max-clip.
TARGETS = {
    "vids": {"min": 3, "max": 10},
    "render": {"min": 2, "max": 30},
    "slides": {"min": 3, "max": 120},
    "storyboard": {"min": 2, "max": 30},
    "ai-video": {"min": 2, "max": 8},
}
TOOL_CLIP = {"veo": 8, "sora": 20, "runway": 10, "kling": 10, "generic": 8}
ZH_CPS, EN_WPS = 3.6, 2.5


def lang_of(text):
    return "zh" if re.search(r"[\u4e00-\u9fff]", text or "") else "en"


def estimate_seconds(script):
    zh = len(re.findall(r"[\u4e00-\u9fff]", script or ""))
    en = len(re.findall(r"[A-Za-z0-9']+", script or ""))
    return round(zh / ZH_CPS + en / EN_WPS, 1)


def find_slop(text):
    low = (text or "").lower()
    return [k for k in AI_SLOP["zh"] + AI_SLOP["en"] if k.lower() in low]


# ---------------------------------------------------------------- draft from source text
def parse_facts(text, top_n=6):
    lines = [ln.strip(" -*#\t") for ln in text.splitlines() if ln.strip()]
    year = re.compile(r"(\d{3,4}\s*年|\b(?:1[5-9]|20)\d{2}\b)")
    facts = []
    for ln in lines:
        if len(ln) < 12:
            continue
        m = year.search(ln)
        facts.append({"tag": m.group(1) if m else "", "text": ln})
        if len(facts) >= top_n:
            break
    return facts or [{"tag": "", "text": ln} for ln in lines[:top_n]]


def trim_to_budget(s, seconds):
    if lang_of(s) == "zh":
        n = int(seconds * ZH_CPS)
        return s if len(s) <= n else s[:n].rstrip("，、；：") + "…"
    words = s.split()
    n = int(seconds * EN_WPS)
    return s if len(words) <= n else " ".join(words[:n]).rstrip(",;:") + "…"


VECTOR = ("Minimalist 2D vector editorial illustration on warm cream paper (#F5F2EB); flat shapes, soft shadows; "
          "teal robot mascot with an orange backpack as the recurring anchor. Subject: {s}")
CINE = ("Documentary live-action, 35mm film grain, natural window light, period-accurate props and wardrobe. "
        "Subject: {s}")
STYLE_ANCHORS = {
    "vector-explainer": "Style: minimalist 2D vector editorial animation, warm cream paper (#F5F2EB), flat shapes with "
                        "soft shadows, teal robot mascot with a small orange backpack, palette teal/orange/navy.",
    "cinematic": "Style: documentary live-action, 35mm film grain, natural motivated light, muted period palette, "
                 "handheld-steady camera.",
}


def draft(text, style, aspect, top_n, title=""):
    facts = parse_facts(text, top_n)
    lang = lang_of(text)
    scenes = []
    cams = ["slow push-in", "lateral truck", "static wide", "gentle tilt-down", "over-the-shoulder"]
    for i, f in enumerate(facts, 1):
        vo = trim_to_budget(f["text"], 6.5)
        scenes.append({
            "id": i,
            "title": f["tag"] or ("重點 %d" % i if lang == "zh" else "Point %d" % i),
            "duration": int(min(max(estimate_seconds(vo) + 1.3, 4), 9)),
            "act": "setup" if i == 1 else ("payoff" if i == len(facts) else "development"),
            "on_screen": f["tag"] or f["text"][:14 if lang == "zh" else 40],
            "voiceover": vo,
            "visual": (VECTOR if style == "vector-explainer" else CINE).format(s=f["text"][:80]),
            "camera": cams[(i - 1) % len(cams)],
            "layout": "timeline" if f["tag"] else "statement",
            "sfx": "",
        })
    return {"title": title or (facts[0]["text"][:40] if facts else ""), "language": "zh-TW" if lang == "zh" else "en-US",
            "aspect_ratio": aspect, "style": style, "scenes": scenes}


# ---------------------------------------------------------------- lint
def lint(sb, target="storyboard", max_clip=None):
    lim = dict(TARGETS[target])
    if max_clip:
        lim["max"] = max_clip
    issues = []
    for sc in sb.get("scenes", []):
        sid = sc.get("id")
        vo, ost, vis = sc.get("voiceover", ""), sc.get("on_screen", ""), sc.get("visual", "")
        d = float(sc.get("duration", 0))
        need = estimate_seconds(vo) + 0.9
        if d and need > d + 0.5 and target != "render":
            issues.append((sid, "warn", "voiceover needs ~%.1fs but scene is %.0fs — cut words or lengthen" % (need, d)))
        if d < lim["min"] or d > lim["max"]:
            issues.append((sid, "error" if target in ("vids", "ai-video") else "warn",
                           "duration %.0fs outside %s range %d–%ds" % (d, target, lim["min"], lim["max"])))
        ost_len = len(re.sub(r"\s", "", ost)) if lang_of(ost) == "zh" else len(ost.split())
        if ost and ost_len > (16 if lang_of(ost) == "zh" else 9):
            issues.append((sid, "warn", "on-screen text is long (%d) — keep a headline, move detail to VO" % ost_len))
        for k in find_slop(vo + " " + ost):
            issues.append((sid, "error", "AI-slop phrase: %r" % k))
        for k in VISUAL_SLOP:
            if k in vis.lower():
                issues.append((sid, "warn", "visual cliché: %r" % k))
        if target in ("vids", "ai-video") and vis and len(vis) < 60:
            issues.append((sid, "warn", "visual prompt is thin — cover camera, framing, subject+action, light, texture"))
    return issues


# ---------------------------------------------------------------- adapters
def _q(s, lang):
    return "「%s」" % s if lang == "zh" else '"%s"' % s


def to_vids(sb):
    lang = lang_of(" ".join(s.get("voiceover", "") for s in sb["scenes"]))
    total = sum(float(s.get("duration", 0)) for s in sb["scenes"])
    style = sb.get("style", "vector-explainer")
    out = ["Create a %d-second %s video titled %s." % (round(total), "2D vector explainer" if style == "vector-explainer"
                                                       else "cinematic documentary", _q(sb.get("title", ""), "en")), ""]
    if sb.get("audience") or sb.get("goal"):
        out += ["--- GOAL & AUDIENCE ---"]
        if sb.get("goal"):
            out.append("Goal: " + sb["goal"])
        if sb.get("audience"):
            out.append("Target Audience: " + sb["audience"])
    out += ["Voiceover Language: %s" % ("Traditional Chinese (zh-TW)" if lang == "zh" else "English"),
            "Aspect Ratio: %s" % sb.get("aspect_ratio", "16:9"), ""]
    if sb.get("style_notes"):
        out += ["--- VISUAL AESTHETIC GUIDELINES ---", sb["style_notes"], ""]
    out.append("--- SCENE-BY-SCENE STORYBOARD (%d SCENES) ---" % len(sb["scenes"]))
    for sc in sb["scenes"]:
        out += ["", "Scene %s (%ds) - %s" % (sc["id"], round(float(sc.get("duration", 6))), sc.get("title", "")),
                "- Visual: %s%s" % (sc.get("visual", ""), (" Camera: %s." % sc["camera"]) if sc.get("camera") else ""),
                "- On-Screen Text: %s" % _q(sc.get("on_screen", ""), "en"),
                "- Voiceover: %s" % _q(sc.get("voiceover", ""), "en")]
    return "\n".join(out) + "\n"


def to_ai_video(sb, tool="generic", max_clip=None):
    cap = max_clip or TOOL_CLIP.get(tool, 8)
    anchor = sb.get("style_notes") or STYLE_ANCHORS.get(sb.get("style", ""), STYLE_ANCHORS["vector-explainer"])
    out = ["# Shot list for %s — %s" % (tool, sb.get("title", "")), "",
           "> Paste each shot as a separate generation. Keep the **style anchor** identical in every prompt so "
           "characters and palette stay consistent. Clip cap: %ds (split longer scenes)." % cap,
           "> Voiceover and on-screen text are added in the editor afterwards — most video models render text poorly.",
           "", "**Style anchor:** " + anchor, ""]
    n = 0
    for sc in sb["scenes"]:
        d = float(sc.get("duration", 6))
        parts = max(1, -(-int(round(d)) // cap))
        for k in range(parts):
            n += 1
            seg = round(d / parts, 1)
            out += ["## Shot %d  (scene %s%s, %.1fs)" % (n, sc["id"], " part %d/%d" % (k + 1, parts) if parts > 1 else "", seg),
                    "```text",
                    "%s. %s %s Duration %.0fs, aspect %s. No on-screen text, no logos, no subtitles." % (
                        sc.get("camera", "Static shot").rstrip(".").capitalize(),
                        sc.get("visual", "").rstrip(". ") + ".", anchor, seg, sb.get("aspect_ratio", "16:9")),
                    "```",
                    "- On-screen (add in editor): %s" % (sc.get("on_screen") or "—"),
                    "- VO: %s" % (sc.get("voiceover") or "—"), ""]
    return "\n".join(out)


def to_slides(sb):
    """Pandoc-flavoured Markdown: `pandoc slides.md -o deck.pptx` turns `::: notes` into speaker notes."""
    out = []
    if (sb["scenes"][0].get("layout") if sb.get("scenes") else None) != "title":
        out = ["---", "title: %s" % json.dumps(sb.get("title", ""), ensure_ascii=False), "---", ""]
    for sc in sb["scenes"]:
        out.append("## %s" % (sc.get("heading") or sc.get("on_screen") or sc.get("title", "")))
        out.append("")
        for it in sc.get("items") or []:
            it = {"label": it} if isinstance(it, str) else it
            out.append("- **%s**%s" % (it.get("label", ""), (" — " + it["text"]) if it.get("text") else ""))
        sub = [x for x in (sc.get("center"), sc.get("on_screen") if sc.get("heading") else None,
                           sc.get("subheading")) if x]
        if sub:
            out += ([""] if sc.get("items") else []) + ["*%s*" % " · ".join(sub)]
        out += ["", "::: notes", "%s" % (sc.get("voiceover") or ""),
                "", "(~%ds%s)" % (round(float(sc.get("duration", 6))),
                                  "; visual: " + sc["visual"] if sc.get("visual") else ""), ":::", ""]
    return "\n".join(out)


def write_pptx(md, out):
    """Convert slide Markdown to .pptx via the pandoc CLI or pypandoc (pip install pypandoc_binary)."""
    import shutil
    import subprocess
    import tempfile
    md_path = Path(tempfile.mkdtemp()) / "slides.md"
    md_path.write_text(md, encoding="utf-8")
    if shutil.which("pandoc"):
        subprocess.run(["pandoc", str(md_path), "-o", out], check=True)
    else:
        try:
            import pypandoc
        except ImportError:
            sys.exit("pandoc not found: install pandoc or `pip install pypandoc_binary`, or write .md instead")
        pypandoc.convert_file(str(md_path), "pptx", outputfile=out)
    print("wrote", out, file=sys.stderr)


def to_render(sb):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from storyboard_render.layouts import resolve  # noqa: E402  (needs pycairo)
    sb = json.loads(json.dumps(sb))
    n = len(sb["scenes"])
    for i, sc in enumerate(sb["scenes"]):
        if not sc.get("layout") and not sc.get("custom"):
            sc["layout"] = resolve(sc, i, n).__name__
    return json.dumps(sb, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--input", "-i", help="source text/markdown file (Wikipedia extract, PPT outline, notes)")
    src.add_argument("--text", "-t", help="source text string")
    src.add_argument("--from-storyboard", "-s", help="existing storyboard JSON to convert/lint")
    ap.add_argument("--target", choices=["storyboard", "vids", "ai-video", "render", "slides"], default="storyboard")
    ap.add_argument("--tool", choices=sorted(TOOL_CLIP), default="generic", help="ai-video tool (clip cap)")
    ap.add_argument("--max-clip", type=int, help="override per-clip cap in seconds")
    ap.add_argument("--style", choices=["vector-explainer", "cinematic"], default="vector-explainer")
    ap.add_argument("--aspect-ratio", choices=["16:9", "9:16", "1:1"], default="16:9")
    ap.add_argument("--top-facts", type=int, default=6)
    ap.add_argument("--title", default="")
    ap.add_argument("--lint", action="store_true", help="only run QA checks (exit 1 on errors)")
    ap.add_argument("--out", "-o", help="write to file instead of stdout")
    a = ap.parse_args()

    if a.from_storyboard:
        sb = json.loads(Path(a.from_storyboard).read_text(encoding="utf-8"))
    else:
        text = Path(a.input).read_text(encoding="utf-8") if a.input else a.text
        if not text:
            ap.error("give --input, --text or --from-storyboard")
        sb = draft(text, a.style, a.aspect_ratio, a.top_facts, a.title)

    issues = lint(sb, a.target, a.max_clip or (TOOL_CLIP.get(a.tool) if a.target == "ai-video" else None))
    for sid, lvl, msg in issues:
        print("[%s] scene %s: %s" % (lvl.upper(), sid, msg), file=sys.stderr)
    if a.lint:
        print("%d issue(s), %d error(s)" % (len(issues), sum(1 for i in issues if i[1] == "error")), file=sys.stderr)
        sys.exit(1 if any(i[1] == "error" for i in issues) else 0)

    if a.target == "vids":
        result = to_vids(sb)
    elif a.target == "ai-video":
        result = to_ai_video(sb, a.tool, a.max_clip)
    elif a.target == "slides":
        result = to_slides(sb)
    elif a.target == "render":
        result = to_render(sb)
    else:
        result = json.dumps(sb, ensure_ascii=False, indent=2)
    if a.out and a.target == "slides" and a.out.lower().endswith(".pptx"):
        write_pptx(result, a.out)
    elif a.out:
        Path(a.out).write_text(result, encoding="utf-8")
        print("wrote", a.out, file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
