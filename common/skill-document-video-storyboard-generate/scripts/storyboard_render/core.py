"""Drawing primitives (pycairo) shared by all layouts.

Generalised from the OpenRepo `dd_video` renderer. Colours live in the mutable PAL dict so a
storyboard can override them (`"palette": {...}`); fonts switch to a CJK face automatically when a
string contains CJK characters (the cairo toy font API has no glyph fallback).
"""
import math
import platform
import random
import re

import cairo
import numpy as np

W, H, FPS = 1920, 1080, 30
FLOOR_Y = 860

PAL = {
    "background": "#F5F2EB",  # warm cream
    "floor": "#E9DFCB",
    "floor_line": "#DCCFB4",
    "ink": "#0F172A",
    "title": "#1E293B",
    "accent": "#E30613",      # title underline / emphasis
    "primary": "#0EA5E9",     # teal
    "success": "#10B981",     # mint
    "success_dark": "#047857",
    "warn": "#F97316",        # orange
    "highlight": "#F5B301",   # gold
    "muted": "#64748B",       # slate
    "card": "#FFFFFF",
    "border": "#E2E8F0",
    "cta_bg": "#1E293B",
    "cta_fg": "#FFFFFF",
    "cta_sub": "#6EE7B7",
    "subtitle_bg": "#2E3440",
    "series": ["#0EA5E9", "#10B981", "#F97316", "#B9A6F2", "#F2A7C3", "#F5B301", "#8FB3F0"],
}

_SYS = platform.system()
FONTS = {
    "latin": {"Windows": "Segoe UI", "Darwin": "Helvetica Neue"}.get(_SYS, "DejaVu Sans"),
    "cjk": {"Windows": "Microsoft JhengHei", "Darwin": "PingFang TC"}.get(_SYS, "Noto Sans CJK TC"),
    "mono": {"Windows": "Consolas", "Darwin": "Menlo"}.get(_SYS, "DejaVu Sans Mono"),
}
CJK_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]")


def configure(palette=None, fonts=None):
    if palette:
        PAL.update(palette)
    if fonts:
        FONTS.update({k: v for k, v in fonts.items() if v})


def series(i):
    s = PAL["series"]
    return s[i % len(s)]


# ---------------------------------------------------------------- math / easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(t, start, dur):
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def eo(x):
    return 1 - (1 - x) ** 3


def eio(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def back(x):
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lerp(a, b, x):
    return a + (b - a) * x


def safe_scale(ctx, sx, sy=None):
    sy = sx if sy is None else sy
    ctx.scale(max(sx, 1e-4), max(sy, 1e-4))


# ---------------------------------------------------------------- colour / shapes
def rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255


def col(ctx, h, a=1.0):
    r, g, b = rgb(h)
    ctx.set_source_rgba(r, g, b, a)


def rrect(ctx, x, y, w, h, r):
    r = max(0, min(r, w / 2, h / 2))
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


def box(ctx, x, y, w, h, r, fill, stroke=None, lw=2, a=1.0, shadow=False):
    if a <= 0 or w <= 0 or h <= 0:
        return
    if shadow:
        col(ctx, "#000000", 0.07 * a)
        rrect(ctx, x + 5, y + 8, w, h, r)
        ctx.fill()
    if fill:
        col(ctx, fill, a)
        rrect(ctx, x, y, w, h, r)
        ctx.fill()
    if stroke:
        col(ctx, stroke, a)
        ctx.set_line_width(lw)
        rrect(ctx, x, y, w, h, r)
        ctx.stroke()


def circle(ctx, x, y, r, fill, a=1.0):
    if a <= 0:
        return
    col(ctx, fill, a)
    ctx.arc(x, y, max(r, 0.01), 0, 2 * math.pi)
    ctx.fill()


def glow(ctx, x, y, r, color, a=0.5):
    if a <= 0 or r <= 0:
        return
    cr, cg, cb = rgb(color)
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, cr, cg, cb, a)
    g.add_color_stop_rgba(1, cr, cg, cb, 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()


# ---------------------------------------------------------------- text
def font(ctx, size, bold=False, mono=False, s=""):
    face = FONTS["mono"] if mono else (FONTS["cjk"] if CJK_RE.search(s or "") else FONTS["latin"])
    ctx.select_font_face(face, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def text_w(ctx, s, size, bold=False, mono=False):
    font(ctx, size, bold, mono, s)
    return ctx.text_extents(s).x_advance


def text(ctx, s, x, y, size, color=None, bold=False, align="left", a=1.0, mono=False):
    """Draw text vertically centred on y; returns the advance width."""
    if a <= 0 or not s:
        return 0
    font(ctx, size, bold, mono, s)
    adv = ctx.text_extents(s).x_advance
    if align == "center":
        x -= adv / 2
    elif align == "right":
        x -= adv
    col(ctx, color or PAL["ink"], a)
    ctx.move_to(x, y + size * 0.35)
    ctx.show_text(s)
    return adv


def fit_size(ctx, s, size, maxw, bold=True, minimum=14):
    while size > minimum and text_w(ctx, s, size, bold) > maxw:
        size -= 1
    return size


_TOK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]|[^\s\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]+|\s+")


def wrap(ctx, s, size, maxw, bold=False):
    """Word wrap for Latin text, per-character wrap for CJK (mixed strings work)."""
    lines, cur = [], ""
    for tok in _TOK.findall(s or ""):
        trial = cur + tok
        if not cur.strip() or text_w(ctx, trial.strip(), size, bold) <= maxw:
            cur = trial
        else:
            lines.append(cur.strip())
            cur = "" if tok.isspace() else tok
    if cur.strip():
        lines.append(cur.strip())
    return lines


def para(ctx, s, x, y, size, maxw, color=None, bold=False, align="left", a=1.0, lh=1.35, max_lines=None):
    """Wrapped paragraph whose first line is centred on y. Returns total height."""
    lines = wrap(ctx, s, size, maxw, bold)
    if max_lines:
        lines = lines[:max_lines]
    for i, ln in enumerate(lines):
        text(ctx, ln, x, y + i * size * lh, size, color, bold, align, a)
    return len(lines) * size * lh


# ---------------------------------------------------------------- paths
def path_len(pts):
    acc = [0.0]
    for i in range(1, len(pts)):
        acc.append(acc[-1] + math.dist(pts[i - 1], pts[i]))
    return acc


def poly_partial(ctx, pts, frac):
    frac = clamp(frac)
    if frac <= 0 or len(pts) < 2:
        return False
    acc = path_len(pts)
    target = acc[-1] * frac
    ctx.move_to(*pts[0])
    for i in range(1, len(pts)):
        if acc[i] >= target:
            seg = acc[i] - acc[i - 1]
            u = (target - acc[i - 1]) / seg if seg else 0
            ctx.line_to(lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u))
            return True
        ctx.line_to(*pts[i])
    return True


def stroke_partial(ctx, pts, frac, color, lw=4, a=1.0, dash=None):
    if a <= 0:
        return
    ctx.save()
    if dash:
        ctx.set_dash(dash)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if poly_partial(ctx, pts, frac):
        col(ctx, color, a)
        ctx.set_line_width(lw)
        ctx.stroke()
    ctx.restore()


def point_at(pts, frac):
    acc = path_len(pts)
    target = acc[-1] * clamp(frac)
    for i in range(1, len(pts)):
        if acc[i] >= target:
            seg = acc[i] - acc[i - 1]
            u = (target - acc[i - 1]) / seg if seg else 0
            return lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u)
    return pts[-1]


def bezier(p0, p1, p2, p3, n=40):
    out = []
    for i in range(n + 1):
        u = i / n
        a, b, c, d = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u ** 2, u ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def scurve(a, b, n=40):
    mx = (a[0] + b[0]) / 2
    return bezier(a, (mx, a[1]), (mx, b[1]), b, n)


def flow_dots(ctx, pts, t, color, n=3, speed=0.35, r=6, a=1.0):
    if a <= 0:
        return
    for k in range(n):
        x, y = point_at(pts, (t * speed + k / n) % 1.0)
        glow(ctx, x, y, r * 3, color, 0.35 * a)
        circle(ctx, x, y, r, color, a)


def check(ctx, cx, cy, s, color, p=1.0, lw=6, a=1.0):
    pts = [(cx - 0.5 * s, cy), (cx - 0.15 * s, cy + 0.35 * s), (cx + 0.5 * s, cy - 0.4 * s)]
    stroke_partial(ctx, pts, p, color, lw, a)


def cross(ctx, cx, cy, s, color, p=1.0, lw=6, a=1.0):
    stroke_partial(ctx, [(cx - s / 2, cy - s / 2), (cx + s / 2, cy + s / 2)], clamp(p * 2), color, lw, a)
    stroke_partial(ctx, [(cx + s / 2, cy - s / 2), (cx - s / 2, cy + s / 2)], clamp(p * 2 - 1), color, lw, a)


def arrow(ctx, x0, y0, x1, y1, color, p=1.0, lw=5, a=1.0, head=16):
    if p <= 0 or a <= 0:
        return
    xe, ye = lerp(x0, x1, p), lerp(y0, y1, p)
    stroke_partial(ctx, [(x0, y0), (xe, ye)], 1, color, lw, a)
    ang = math.atan2(y1 - y0, x1 - x0)
    col(ctx, color, a)
    ctx.move_to(xe, ye)
    ctx.line_to(xe - head * math.cos(ang - 0.45), ye - head * math.sin(ang - 0.45))
    ctx.line_to(xe - head * math.cos(ang + 0.45), ye - head * math.sin(ang + 0.45))
    ctx.close_path()
    ctx.fill()


def sparkle(ctx, x, y, s, color=None, a=1.0):
    if a <= 0:
        return
    col(ctx, color or PAL["highlight"], a)
    ctx.move_to(x, y - s)
    ctx.curve_to(x, y, x, y, x + s, y)
    ctx.curve_to(x, y, x, y, x, y + s)
    ctx.curve_to(x, y, x, y, x - s, y)
    ctx.curve_to(x, y, x, y, x, y - s)
    ctx.fill()


# ---------------------------------------------------------------- backgrounds
_rng = np.random.default_rng(7)
_tex = np.zeros((H, W, 4), np.uint8)
_tex[..., 3] = ((_rng.random((H, W)) < 0.06) * 14).astype(np.uint8)
TEXTURE = cairo.ImageSurface.create_for_data(memoryview(_tex), cairo.FORMAT_ARGB32, W, H, W * 4)


def bg(ctx, floor=True):
    col(ctx, PAL["background"])
    ctx.paint()
    ctx.set_source_surface(TEXTURE, 0, 0)
    ctx.paint()
    if floor:
        col(ctx, PAL["floor"])
        ctx.rectangle(0, FLOOR_Y, W, H - FLOOR_Y)
        ctx.fill()
        col(ctx, PAL["floor_line"])
        ctx.rectangle(0, FLOOR_Y, W, 4)
        ctx.fill()


def bg_solid(ctx, color):
    col(ctx, color)
    ctx.paint()


def heading(ctx, s, t, y=105, color=None, size=48, start=0.15):
    """Scene title with an animated accent underline."""
    p = eo(prog(t, start, 0.6))
    if p <= 0 or not s:
        return
    size = fit_size(ctx, s, size, 1680)
    ctx.save()
    ctx.translate(0, (1 - p) * -24)
    text(ctx, s, W / 2, y, size, color or PAL["title"], True, "center", p)
    col(ctx, PAL["accent"], p)
    rrect(ctx, W / 2 - 45 * p, y + size * 0.85, 90 * p, 6, 3)
    ctx.fill()
    ctx.restore()


def subtitle(ctx, s, a=1.0):
    if not s or a <= 0:
        return
    size = 32
    lines = wrap(ctx, s, size, 1600, True)
    pw = max(text_w(ctx, ln, size, True) for ln in lines) + 70
    lh = 46
    ph = 26 + lh * len(lines)
    x, y = W / 2 - pw / 2, 1035 - ph
    col(ctx, PAL["subtitle_bg"], 0.93 * a)
    rrect(ctx, x, y, pw, ph, 16)
    ctx.fill()
    for i, ln in enumerate(lines):
        text(ctx, ln, W / 2, y + 13 + lh * i + lh / 2, size, "#FFFFFF", True, "center", a)


# ---------------------------------------------------------------- particles / fog / confetti
_r = random.Random(11)
FOG = [(_r.uniform(-100, W + 100), _r.uniform(200, 840), _r.uniform(140, 300),
        _r.uniform(0.2, 0.6), _r.uniform(0, 6.28)) for _ in range(34)]
PARTICLES = [(_r.uniform(0, W), _r.uniform(0, H), _r.uniform(-8, 8), _r.uniform(6, 22),
              _r.uniform(1.5, 4), _r.uniform(0, 6.28)) for _ in range(90)]
CONFETTI = [(_r.uniform(0, W), _r.uniform(-400, 0), _r.uniform(160, 320), _r.uniform(-3, 3), _r.randrange(7))
            for _ in range(120)]


def fog(ctx, t, a):
    if a <= 0:
        return
    for x, y, r, sp, ph in FOG:
        glow(ctx, x + math.sin(t * sp + ph) * 50, y, r, "#FFFFFF", 0.62 * a)


def particles(ctx, t, color, a=0.5):
    if a <= 0:
        return
    for x, y, vx, vy, r, ph in PARTICLES:
        circle(ctx, (x + vx * t) % W, (y - vy * t) % H, r, color, a * (0.5 + 0.5 * math.sin(t * 2 + ph)))


def confetti(ctx, t, a=1.0):
    if t <= 0:
        return
    for x, y0, sp, rot, ci in CONFETTI:
        y = y0 + t * sp
        if y > FLOOR_Y + 40:
            continue
        ctx.save()
        ctx.translate(x + math.sin(t * 2 + x) * 20, y)
        ctx.rotate(rot * t)
        col(ctx, series(ci), a)
        ctx.rectangle(-6, -3, 12, 6)
        ctx.fill()
        ctx.restore()
