"""JSON-driven scene layouts. Each layout is `fn(ctx, t, dur, scene, env)`.

`scene` keys used here: heading, on_screen, items[{label,text,icon,color}], icon, image, center,
character ("robot"|"people"|"none"), mood. See references/storyboard-schema.md.
"""
import importlib
import math
import os

import cairo

from . import art
from .core import (FLOOR_Y, H, PAL, W, arrow, back, bg, bg_solid, box, check, circle, clamp, col, confetti,
                   cross, eo, fit_size, glow, heading, lerp, para, particles, prog, rrect, safe_scale, scurve,
                   series, sparkle, stroke_partial, flow_dots, text, wrap)


def _items(scene):
    out = []
    for i, it in enumerate(scene.get("items") or []):
        if isinstance(it, str):
            it = {"label": it}
        out.append(dict(it, color=it.get("color") or series(i)))
    return out


def _stagger(t, dur, n, start=0.6, span=None):
    """Entrance progress for item i: spread over ~55% of the scene."""
    span = span if span is not None else max(0.6, dur * 0.55 - start)
    step = span / max(n, 1)
    return [eo(prog(t, start + i * step, 0.55)) for i in range(n)]


def _character(ctx, t, scene, x, s=0.9, arm=0.0):
    ch = scene.get("character", "robot")
    if ch == "robot":
        art.robot(ctx, x, FLOOR_Y, s, t, scene.get("mood", "happy"), arm_r=arm, look=0.3)
    elif ch == "people":
        for i, dx in enumerate((-90, 0, 90)):
            art.person(ctx, x + dx * s, FLOOR_Y, 0.8 * s, t=t + i, nod=math.sin(t * 2 + i), **art.PEOPLE[i])


def _heading(ctx, t, scene, y=105):
    heading(ctx, scene.get("heading") or "", t, y)


# ---------------------------------------------------------------- layouts
def title(ctx, t, dur, scene, env):
    bg(ctx)
    p = back(prog(t, 0.2, 0.8))
    main = scene.get("heading") or scene.get("on_screen") or scene.get("title", "")
    sub = scene.get("on_screen") if scene.get("heading") else scene.get("subheading", "")
    size = fit_size(ctx, main, 88, 1500)
    ctx.save()
    ctx.translate(W / 2, 330)
    safe_scale(ctx, 0.85 + 0.15 * p)
    lines = wrap(ctx, main, size, 1500, True)
    for i, ln in enumerate(lines[:2]):
        text(ctx, ln, 0, (i - (len(lines[:2]) - 1) / 2) * size * 1.15, size, PAL["title"], True, "center",
             clamp(p))
    ctx.restore()
    q = eo(prog(t, 0.7, 0.6))
    col(ctx, PAL["accent"], q)
    rrect(ctx, W / 2 - 70 * q, 330 + size * 1.0, 140 * q, 8, 4)
    ctx.fill()
    if sub:
        para(ctx, sub, W / 2, 330 + size * 1.0 + 70, 40, 1400, PAL["muted"], False, "center", eo(prog(t, 1.0, 0.6)))
    for i, (sx, sy) in enumerate(((420, 250), (1500, 220), (1380, 470), (520, 500))):
        sparkle(ctx, sx, sy, 16 + 6 * math.sin(t * 3 + i), PAL["highlight"], eo(prog(t, 1.2 + i * 0.15, 0.4)))
    if scene.get("icon"):
        art.draw_icon(ctx, scene["icon"], W / 2 + 520, 720, 1.2, eo(prog(t, 1.2, 0.6)), t)
    _character(ctx, t, scene, W / 2 if not scene.get("icon") else W / 2 - 520, 0.75,
               arm=0.5 + 0.3 * math.sin(t * 4) if t > 1 else 0)


def statement(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    s = scene.get("on_screen") or scene.get("title", "")
    p = eo(prog(t, 0.35, 0.7))
    has_side = bool(scene.get("icon")) or scene.get("character", "robot") != "none"
    cx = W / 2 + (180 if has_side else 0)
    maxw = 1150 if has_side else 1500
    size = 72 if len(s) < 40 else 58
    lines = wrap(ctx, s, size, maxw, True)[:4]
    y0 = 470 - (len(lines) - 1) * size * 0.65
    ctx.save()
    ctx.translate(0, (1 - p) * 30)
    for i, ln in enumerate(lines):
        text(ctx, ln, cx, y0 + i * size * 1.3, size, PAL["title"], True, "center", p)
    ctx.restore()
    if scene.get("icon"):
        art.draw_icon(ctx, scene["icon"], 330, 470, 1.5 + 0.04 * math.sin(t * 2), eo(prog(t, 0.2, 0.6)), t)
    elif has_side:
        _character(ctx, t, scene, 330, 0.85, arm=0.4 * eo(prog(t, 0.8, 0.5)))


def bullets(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:6]
    ps = _stagger(t, dur, len(items))
    x0 = 700 if scene.get("character", "robot") != "none" else 360
    gap = min(120, 560 / max(len(items), 1))
    for i, (it, p) in enumerate(zip(items, ps)):
        y = 270 + i * gap
        ctx.save()
        ctx.translate((1 - p) * 60, 0)
        box(ctx, x0 - 20, y - 42, 1180 - (x0 - 700), 84, 18, PAL["card"], PAL["border"], 2, a=p, shadow=True)
        if it.get("icon"):
            art.draw_icon(ctx, it["icon"], x0 + 30, y, 0.42, p, t, it["color"])
        else:
            circle(ctx, x0 + 30, y, 24, it["color"], p)
            check(ctx, x0 + 30, y, 24, "#FFFFFF", p, 5, p)
        lab = it.get("label", "")
        adv = text(ctx, lab, x0 + 80, y, 34, PAL["title"], True, a=p)
        if it.get("text"):
            text(ctx, "  " + it["text"], x0 + 80 + adv, y, 28, PAL["muted"], a=p)
        ctx.restore()
    _character(ctx, t, scene, 330, 0.85, arm=0.5 * eo(prog(t, 0.6, 0.5)))


def cards(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:4]
    n = max(len(items), 1)
    cw = min(400, (1700 - (n - 1) * 40) / n)
    x0 = W / 2 - (n * cw + (n - 1) * 40) / 2
    ps = _stagger(t, dur, n)
    for i, (it, p) in enumerate(zip(items, ps)):
        x = x0 + i * (cw + 40)
        y = 260 + (1 - back(clamp(p))) * 80
        box(ctx, x, y, cw, 460, 26, PAL["card"], PAL["border"], 2, a=clamp(p), shadow=True)
        box(ctx, x, y, cw, 14, 7, it["color"], a=clamp(p))
        art.draw_icon(ctx, it.get("icon") or "number", x + cw / 2, y + 130, 1.0, clamp(p), t, it["color"],
                      label=str(i + 1))
        size = fit_size(ctx, it.get("label", ""), 36, cw - 40)
        text(ctx, it.get("label", ""), x + cw / 2, y + 250, size, PAL["title"], True, "center", clamp(p))
        if it.get("text"):
            para(ctx, it["text"], x + cw / 2, y + 315, 26, cw - 50, PAL["muted"], False, "center", clamp(p),
                 max_lines=4)
    if scene.get("on_screen") and scene.get("heading"):
        text(ctx, scene["on_screen"], W / 2, 800, 34, PAL["muted"], True, "center", eo(prog(t, dur * 0.6, 0.6)))


def flow(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:6]
    n = max(len(items), 1)
    nw = min(260, (1700 - (n - 1) * 70) / n)
    x0 = W / 2 - (n * nw + (n - 1) * 70) / 2
    y = 470
    ps = _stagger(t, dur, n)
    for i, (it, p) in enumerate(zip(items, ps)):
        x = x0 + i * (nw + 70)
        if i and p > 0:
            arrow(ctx, x - 62, y, x - 10, y, PAL["muted"], p, 5)
        sc = 0.6 + 0.4 * back(clamp(p))
        ctx.save()
        ctx.translate(x + nw / 2, y)
        safe_scale(ctx, sc)
        box(ctx, -nw / 2, -150, nw, 300, 24, PAL["card"], it["color"], 4, a=clamp(p), shadow=True)
        art.draw_icon(ctx, it.get("icon") or "number", 0, -60, 0.8, clamp(p), t, it["color"], label=str(i + 1))
        size = fit_size(ctx, it.get("label", ""), 30, nw - 24)
        text(ctx, it.get("label", ""), 0, 40, size, PAL["title"], True, "center", clamp(p))
        if it.get("text"):
            para(ctx, it["text"], 0, 88, 22, nw - 30, PAL["muted"], False, "center", clamp(p), max_lines=2)
        ctx.restore()
    if n > 1 and t > dur * 0.6:
        pts = [(x0 + nw / 2, y + 190), (x0 + (n - 1) * (nw + 70) + nw / 2, y + 190)]
        stroke_partial(ctx, pts, 1, PAL["border"], 4, 1)
        flow_dots(ctx, pts, t, PAL["primary"], 3, 0.25, 7, eo(prog(t, dur * 0.6, 0.5)))
    if scene.get("on_screen") and scene.get("heading"):
        text(ctx, scene["on_screen"], W / 2, 790, 34, PAL["muted"], True, "center", eo(prog(t, dur * 0.6, 0.6)))


def hub(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:8]
    cx, cy, R = W / 2, 500, 300
    p0 = back(prog(t, 0.3, 0.7))
    ps = _stagger(t, dur, len(items), start=0.9)
    for i, (it, p) in enumerate(zip(items, ps)):
        ang = -math.pi / 2 + i * 2 * math.pi / max(len(items), 1)
        x, y = cx + math.cos(ang) * R * 1.35, cy + math.sin(ang) * R
        stroke_partial(ctx, [(cx, cy), (x, y)], p, it["color"], 4, 0.7)
        if p >= 1:
            flow_dots(ctx, [(x, y), (cx, cy)], t + i * 0.3, it["color"], 2, 0.3, 5, 0.9)
        box(ctx, x - 130, y - 50, 260, 100, 22, PAL["card"], it["color"], 3, a=p, shadow=True)
        art.draw_icon(ctx, it.get("icon"), x - 85, y, 0.35, p, t, it["color"])
        size = fit_size(ctx, it.get("label", ""), 28, 160 if it.get("icon") else 220)
        text(ctx, it.get("label", ""), x + (20 if it.get("icon") else 0), y, size, PAL["title"], True, "center", p)
    glow(ctx, cx, cy, 200, PAL["primary"], 0.25 * clamp(p0))
    circle(ctx, cx, cy, 110 * max(p0, 0.001), PAL["primary"], clamp(p0))
    center = scene.get("center") or scene.get("on_screen") or ""
    if center:
        lines = wrap(ctx, center, 30, 190, True)[:3]
        for i, ln in enumerate(lines):
            text(ctx, ln, cx, cy + (i - (len(lines) - 1) / 2) * 36, 30, "#FFFFFF", True, "center", clamp(p0))


def timeline(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:7]
    n = max(len(items), 1)
    x0, x1, y = 180, W - 180, 500
    stroke_partial(ctx, [(x0, y), (x1, y)], eo(prog(t, 0.3, dur * 0.5)), PAL["border"], 8)
    ps = _stagger(t, dur, n)
    for i, (it, p) in enumerate(zip(items, ps)):
        x = lerp(x0 + 80, x1 - 80, i / max(n - 1, 1)) if n > 1 else W / 2
        up = i % 2 == 0
        circle(ctx, x, y, 18 * back(clamp(p)) if p > 0 else 0.01, it["color"], clamp(p))
        stroke_partial(ctx, [(x, y), (x, y + (-90 if up else 90))], p, it["color"], 3, p)
        ty = y + (-150 if up else 150)
        text(ctx, it.get("label", ""), x, ty + (-30 if up else 0), 40, it["color"], True, "center", p)
        if it.get("text"):
            para(ctx, it["text"], x, ty + (14 if up else 46), 24, 230, PAL["muted"], False, "center", p, max_lines=2)


def split(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    items = _items(scene)[:2] or [{"label": "Before"}, {"label": "After"}]
    while len(items) < 2:
        items.append({"label": ""})
    for i, it in enumerate(items):
        p = eo(prog(t, 0.5 + i * dur * 0.3, 0.6))
        x = 140 + i * 860
        good = i == 1
        color = it.get("color") if it.get("color") not in (None, series(i)) else (PAL["success"] if good else PAL["warn"])
        box(ctx, x, 210, 780, 560, 30, PAL["card"], color, 4, a=p, shadow=True)
        if good:
            check(ctx, x + 80, 290, 60, color, eo(prog(t, 0.8 + dur * 0.3, 0.5)), 10, p)
        else:
            cross(ctx, x + 80, 290, 50, color, eo(prog(t, 0.8, 0.5)), 10, p)
        text(ctx, it.get("label", ""), x + 140, 290, 44, PAL["title"], True, a=p)
        if it.get("icon"):
            art.draw_icon(ctx, it["icon"], x + 390, 470, 1.2, p, t, color)
        if it.get("text"):
            para(ctx, it["text"], x + 390, 640 if it.get("icon") else 440, 32, 680, PAL["muted"], False, "center", p,
                 max_lines=3)
    arrow(ctx, 925, 490, 995, 490, PAL["muted"], eo(prog(t, 0.5 + dur * 0.3, 0.4)), 7, 1, 22)


def stat(ctx, t, dur, scene, env):
    bg(ctx)
    _heading(ctx, t, scene)
    it = (_items(scene) or [{"label": "100%", "color": PAL["primary"]}])[0]
    raw = str(it.get("label", ""))
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    p = eo(prog(t, 0.4, min(2.0, dur * 0.4)))
    shown = raw
    if digits:
        try:
            val = float(digits) * p
            fmt = ("%.1f" % val) if "." in digits else ("%d" % round(val))
            shown = raw.replace(digits, fmt, 1)
        except ValueError:
            pass
    glow(ctx, W / 2, 440, 380, it["color"], 0.18 * p)
    text(ctx, shown, W / 2, 430, fit_size(ctx, raw, 220, 1500), it["color"], True, "center", clamp(p * 3))
    if it.get("text") or scene.get("on_screen"):
        para(ctx, it.get("text") or scene.get("on_screen"), W / 2, 640, 44, 1400, PAL["title"], True, "center",
             eo(prog(t, 1.0, 0.6)), max_lines=2)


def quote(ctx, t, dur, scene, env):
    bg(ctx)
    p = eo(prog(t, 0.3, 0.8))
    text(ctx, "\u201c", 260, 300, 300, PAL["accent"], True, "left", 0.3 * p)
    s = scene.get("on_screen") or ""
    para(ctx, s, W / 2, 400, 56, 1300, PAL["title"], True, "center", p, max_lines=4)
    who = scene.get("attribution") or scene.get("heading")
    if who:
        text(ctx, "\u2014 " + who, W / 2, 740, 36, PAL["muted"], False, "center", eo(prog(t, 1.2, 0.6)))


def cta(ctx, t, dur, scene, env):
    bg_solid(ctx, PAL["cta_bg"])
    particles(ctx, t, PAL["cta_sub"], 0.35)
    p = back(prog(t, 0.2, 0.8))
    main = scene.get("on_screen") or scene.get("heading") or ""
    size = fit_size(ctx, main, 84, 1600)
    lines = wrap(ctx, main, size, 1600, True)[:3]
    for i, ln in enumerate(lines):
        text(ctx, ln, W / 2, 420 + (i - (len(lines) - 1) / 2) * size * 1.2, size, PAL["cta_fg"], True, "center",
             clamp(p))
    sub = scene.get("subheading") or (scene.get("heading") if scene.get("on_screen") else "")
    if sub:
        text(ctx, sub, W / 2, 600, 40, PAL["cta_sub"], True, "center", eo(prog(t, 0.9, 0.6)))
    if scene.get("icon"):
        art.draw_icon(ctx, scene["icon"], W / 2, 780, 1.0, eo(prog(t, 1.2, 0.6)), t)
    if scene.get("confetti", True):
        confetti(ctx, max(0, t - 0.6), 0.9)


_IMG_CACHE = {}


def image(ctx, t, dur, scene, env):
    """Full-bleed image (PNG) with a slow Ken Burns push; caption = on_screen."""
    bg_solid(ctx, "#000000")
    path = scene.get("image", "")
    if path and not os.path.isabs(path):
        path = os.path.join(env.get("base_dir", "."), path)
    if path and os.path.exists(path):
        if path not in _IMG_CACHE:
            _IMG_CACHE[path] = cairo.ImageSurface.create_from_png(path)
        img = _IMG_CACHE[path]
        sc = max(W / img.get_width(), H / img.get_height()) * (1.0 + 0.06 * t / max(dur, 1))
        ctx.save()
        ctx.translate(W / 2, H / 2)
        safe_scale(ctx, sc)
        ctx.set_source_surface(img, -img.get_width() / 2, -img.get_height() / 2)
        ctx.paint()
        ctx.restore()
    else:
        bg(ctx)
        art.icon_question(ctx, W / 2, 440, 2.0)
    if scene.get("on_screen"):
        p = eo(prog(t, 0.5, 0.6))
        box(ctx, 120, 120, 1680, 110, 20, "#000000", a=0.45 * p)
        text(ctx, scene["on_screen"], W / 2, 175, 48, "#FFFFFF", True, "center", p)


LAYOUTS = {
    "title": title, "statement": statement, "bullets": bullets, "cards": cards, "flow": flow, "hub": hub,
    "timeline": timeline, "split": split, "stat": stat, "quote": quote, "cta": cta, "image": image,
}


def resolve(scene, index, total):
    """Pick the layout function for a scene (explicit `custom`, explicit `layout`, or auto)."""
    if scene.get("custom"):
        mod, _, fn = scene["custom"].partition(":")
        return getattr(importlib.import_module(mod), fn)
    name = scene.get("layout")
    if name in LAYOUTS:
        return LAYOUTS[name]
    n_items = len(scene.get("items") or [])
    if index == 0:
        return title
    if index == total - 1:
        return cta
    if n_items >= 5:
        return bullets
    if n_items >= 2:
        return cards
    return statement
