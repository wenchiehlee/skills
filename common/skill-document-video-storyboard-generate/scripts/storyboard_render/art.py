"""Characters and generic icons. Every icon is drawn at (x, y) with a scale and alpha."""
import math

import cairo

from .core import FLOOR_Y, PAL, box, check, circle, col, glow, safe_scale, series, text


def _limb(ctx, sx, sy, side, raise_, length, lw, color, hand, hand_r):
    th = math.radians(12 + raise_ * 150)
    ex = sx + side * math.sin(th) * length
    ey = sy + math.cos(th) * length
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    col(ctx, color)
    ctx.set_line_width(lw)
    ctx.move_to(sx, sy)
    ctx.line_to(ex, ey)
    ctx.stroke()
    circle(ctx, ex, ey, hand_r, hand)
    return ex, ey


def _shadow(ctx, r):
    col(ctx, "#000000", 0.10)
    ctx.save()
    ctx.scale(1, 0.22)
    ctx.arc(0, 0, r, 0, 2 * math.pi)
    ctx.fill()
    ctx.restore()


def robot(ctx, cx, fy=FLOOR_Y, s=1.0, t=0.0, mood="happy", arm_l=0.0, arm_r=0.0, walk=False, look=0.0, a=1.0):
    """Teal robot mascot with an orange backpack (the vector-explainer protagonist)."""
    if a <= 0:
        return
    body, dark, pack = PAL["primary"], "#0B7FB5", PAL["warn"]
    ctx.save()
    ctx.push_group()
    ctx.translate(cx, fy)
    safe_scale(ctx, s)
    _shadow(ctx, 75)
    lift = (abs(math.sin(t * 9)) * 10) if walk else 0
    box(ctx, -42, -44 - (lift if walk and math.sin(t * 9) > 0 else 0), 28, 44, 8, dark)
    box(ctx, 14, -44 - (lift if walk and math.sin(t * 9) <= 0 else 0), 28, 44, 8, dark)
    b = math.sin(t * 9) * 3 if walk else math.sin(t * 3) * 4
    ctx.translate(0, b)
    box(ctx, -82, -150, 42, 92, 14, pack)
    box(ctx, -88, -128, 18, 46, 7, "#EA580C")
    box(ctx, -60, -165, 120, 128, 32, body)
    circle(ctx, 0, -100, 20, "#7DD3FC", 0.9)
    circle(ctx, 0, -100, 9, "#FFFFFF", 0.8)
    _limb(ctx, -62, -142, -1, arm_l, 62, 22, dark, "#38BDF8", 14)
    _limb(ctx, 62, -142, 1, arm_r, 62, 22, dark, "#38BDF8", 14)
    box(ctx, -14, -185, 28, 24, 6, dark)
    box(ctx, -96, -262, 16, 44, 7, body)
    box(ctx, 80, -262, 16, 44, 7, body)
    box(ctx, -84, -306, 168, 128, 38, "#E0F2FE", body, 6)
    box(ctx, -64, -288, 128, 90, 26, "#1E293B")
    ex = look * 10
    blink = (t % 3.3) < 0.12
    col(ctx, "#5EEAD4")
    ctx.set_line_width(7)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for dx in (-28, 28):
        if blink:
            ctx.move_to(dx - 12 + ex, -244)
            ctx.line_to(dx + 12 + ex, -244)
            ctx.stroke()
        elif mood == "happy":
            ctx.arc(dx + ex, -238, 13, math.pi * 1.1, math.pi * 1.9)
            ctx.stroke()
        else:
            circle(ctx, dx + ex, -244, 11, "#5EEAD4")
            circle(ctx, dx + ex + 3, -247, 4, "#1E293B")
    col(ctx, "#5EEAD4")
    ctx.set_line_width(5)
    if mood == "focus":
        ctx.move_to(-12 + ex, -218)
        ctx.line_to(12 + ex, -218)
    elif mood == "sad":
        ctx.arc_negative(ex, -206, 14, -math.pi * 0.2, -math.pi * 0.8)
    else:
        ctx.arc(ex, -226, 14, math.pi * 0.2, math.pi * 0.8)
    ctx.stroke()
    col(ctx, body)
    ctx.set_line_width(6)
    ctx.move_to(0, -306)
    ctx.line_to(0, -334)
    ctx.stroke()
    glow(ctx, 0, -340, 26, PAL["highlight"], 0.25 + 0.25 * math.sin(t * 5))
    circle(ctx, 0, -340, 10, "#5EEAD4")
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


def person(ctx, cx, fy=FLOOR_Y, s=1.0, shirt="#8FB3F0", hair="#6B4F3A", skin="#F2C9A0", t=0.0,
           arm_l=0.0, arm_r=0.0, nod=0.0, hair_style="short", glasses=False, a=1.0):
    if a <= 0:
        return
    ctx.save()
    ctx.push_group()
    ctx.translate(cx, fy)
    safe_scale(ctx, s)
    _shadow(ctx, 62)
    box(ctx, -32, -96, 28, 96, 10, "#334155")
    box(ctx, 4, -96, 28, 96, 10, "#334155")
    ctx.translate(math.sin(t * 2.2) * 1.5, 0)
    _limb(ctx, -50, -200, -1, arm_l, 74, 22, shirt, skin, 12)
    _limb(ctx, 50, -200, 1, arm_r, 74, 22, shirt, skin, 12)
    box(ctx, -52, -222, 104, 140, 34, shirt)
    hy = -262 + nod * 7
    box(ctx, -12, -236, 24, 22, 6, skin)
    if hair_style == "long":
        box(ctx, -46, hy - 44, 92, 104, 40, hair)
    circle(ctx, 0, hy, 40, skin)
    if hair_style == "bun":
        circle(ctx, 0, hy - 50, 18, hair)
    col(ctx, hair)
    ctx.arc(0, hy - 4, 42, math.pi, 2 * math.pi)
    ctx.close_path()
    ctx.fill()
    if hair_style in ("short", "bun"):
        box(ctx, -42, hy - 12, 14, 22, 6, hair)
    circle(ctx, -14, hy + 6, 4, PAL["ink"])
    circle(ctx, 14, hy + 6, 4, PAL["ink"])
    if glasses:
        col(ctx, PAL["ink"])
        ctx.set_line_width(3)
        for dx in (-14, 14):
            ctx.new_sub_path()
            ctx.arc(dx, hy + 6, 11, 0, 2 * math.pi)
        ctx.stroke()
    col(ctx, "#B45309")
    ctx.set_line_width(3.5)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.arc(0, hy + 18, 11, math.pi * 0.15, math.pi * 0.85)
    ctx.stroke()
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


PEOPLE = [
    dict(shirt="#8FB3F0", hair="#6B4F3A", hair_style="short"),
    dict(shirt="#F2A7C3", hair="#3B2A20", hair_style="long"),
    dict(shirt="#B9A6F2", hair="#1F2937", hair_style="bun", glasses=True),
    dict(shirt="#9ED9B7", hair="#7C4A2D", hair_style="short", glasses=True),
]


# ---------------------------------------------------------------- icons (centred at cx, cy; ~120px at s=1)
def _lines(ctx, x, y, w, n, gap, a, lw=8, color="#CBD5E1"):
    for i in range(n):
        box(ctx, x, y + i * gap, w * (0.92, 0.75, 0.86, 0.6, 0.8)[i % 5], lw, lw / 2, color, a=a)


def icon_doc(ctx, cx, cy, s=1.0, a=1.0, color=None):
    w, h = 96 * s, 124 * s
    x, y = cx - w / 2, cy - h / 2
    box(ctx, x, y, w, h, 10 * s, PAL["card"], PAL["border"], 2, a=a, shadow=True)
    box(ctx, x, y, w, 22 * s, 10 * s, color or PAL["primary"], a=a)
    _lines(ctx, x + 12 * s, y + 38 * s, w - 24 * s, 4, 18 * s, a, 7 * s)


def icon_deck(ctx, cx, cy, s=1.0, a=1.0, color=None):
    w, h = 140 * s, 96 * s
    x, y = cx - w / 2, cy - h / 2
    box(ctx, x + 14 * s, y - 12 * s, w, h, 10 * s, "#E2E8F0", a=a)
    box(ctx, x, y, w, h, 10 * s, PAL["card"], PAL["border"], 2, a=a, shadow=True)
    for i, f in enumerate((0.35, 0.6, 0.85)):
        bh = (h - 30 * s) * f
        box(ctx, x + w * 0.2 + i * w * 0.22, y + h - 12 * s - bh, w * 0.14, bh, 3, series(i), a=a)


def icon_chart(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    w, h = 140 * s, 110 * s
    x, y = cx - w / 2, cy - h / 2
    box(ctx, x, y, w, h, 12 * s, PAL["card"], PAL["border"], 2, a=a, shadow=True)
    pts = [(x + w * f, y + h * (0.8 - 0.55 * v)) for f, v in ((0.12, 0.1), (0.35, 0.35), (0.6, 0.3), (0.88, 0.9))]
    col(ctx, color or PAL["success"], a)
    ctx.set_line_width(6 * s)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)
    ctx.stroke()
    for p in pts:
        circle(ctx, p[0], p[1], 7 * s, color or PAL["success"], a)


def icon_gear(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    r = 50 * s
    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(t * 0.8)
    col(ctx, color or PAL["muted"], a)
    for k in range(8):
        ctx.save()
        ctx.rotate(k * math.pi / 4)
        ctx.rectangle(-10 * s, -r - 14 * s, 20 * s, 24 * s)
        ctx.restore()
    ctx.arc(0, 0, r, 0, 2 * math.pi)
    ctx.fill()
    circle(ctx, 0, 0, r * 0.42, PAL["background"], a)
    ctx.restore()


def icon_bulb(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    glow(ctx, cx, cy - 10 * s, 110 * s, PAL["highlight"], 0.35 * a)
    circle(ctx, cx, cy - 12 * s, 46 * s, color or PAL["highlight"], a)
    box(ctx, cx - 22 * s, cy + 28 * s, 44 * s, 30 * s, 6 * s, PAL["muted"], a=a)


def icon_cloud(ctx, cx, cy, s=1.0, a=1.0, color=None):
    col(ctx, color or "#FFFFFF", a)
    for dx, dy, r in [(-50, 8, 36), (-14, -18, 46), (32, -4, 40), (60, 14, 28), (0, 18, 40)]:
        ctx.new_sub_path()
        ctx.arc(cx + dx * s, cy + dy * s, r * s, 0, 2 * math.pi)
    ctx.fill()


def icon_globe(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    r = 56 * s
    circle(ctx, cx, cy, r, "#BFDBFE", a)
    col(ctx, color or "#3B82F6", a * 0.8)
    ctx.set_line_width(3)
    ctx.arc(cx, cy, r, 0, 2 * math.pi)
    ctx.stroke()
    for k in range(3):
        ctx.save()
        ctx.translate(cx, cy)
        ctx.scale(max(abs(math.cos(t * 0.6 + k * 1.05)), 0.05), 1)
        ctx.arc(0, 0, r, 0, 2 * math.pi)
        ctx.restore()
        ctx.stroke()


def icon_calendar(ctx, cx, cy, s=1.0, a=1.0, color=None, label=""):
    w = h = 120 * s
    x, y = cx - w / 2, cy - h / 2
    box(ctx, x, y, w, h, 14 * s, PAL["card"], PAL["border"], 2, a=a, shadow=True)
    box(ctx, x, y, w, 32 * s, 14 * s, color or PAL["accent"], a=a)
    text(ctx, label or "31", cx, cy + 16 * s, 46 * s, PAL["title"], True, "center", a)


def icon_check(ctx, cx, cy, s=1.0, a=1.0, color=None, p=1.0):
    circle(ctx, cx, cy, 52 * s, "#D1FAE5", a)
    check(ctx, cx, cy, 52 * s, color or PAL["success"], p, 9 * s, a)


def icon_warning(ctx, cx, cy, s=1.0, a=1.0, color=None):
    col(ctx, color or PAL["warn"], a)
    ctx.move_to(cx, cy - 56 * s)
    ctx.line_to(cx + 62 * s, cy + 48 * s)
    ctx.line_to(cx - 62 * s, cy + 48 * s)
    ctx.close_path()
    ctx.fill()
    text(ctx, "!", cx, cy + 10 * s, 64 * s, "#FFFFFF", True, "center", a)


def icon_question(ctx, cx, cy, s=1.0, a=1.0, color=None):
    ctx.save()
    ctx.set_dash([6, 8])
    col(ctx, color or "#94A3B8", a)
    ctx.set_line_width(3)
    ctx.arc(cx, cy, 46 * s, 0, 2 * math.pi)
    ctx.stroke()
    ctx.restore()
    text(ctx, "?", cx, cy - 3 * s, 64 * s, color or "#94A3B8", True, "center", a)


def icon_people(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    for i, dx in enumerate((-60, 0, 60)):
        person(ctx, cx + dx * s, cy + 70 * s, 0.42 * s, t=t + i, a=a, **PEOPLE[i])


def icon_robot(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    robot(ctx, cx, cy + 80 * s, 0.45 * s, t=t, a=a)


def icon_code(ctx, cx, cy, s=1.0, a=1.0, color=None):
    w, h = 150 * s, 104 * s
    x, y = cx - w / 2, cy - h / 2
    box(ctx, x, y, w, h, 12 * s, "#1E293B", a=a, shadow=True)
    for i, c in enumerate(("#F87171", "#FBBF24", "#34D399")):
        circle(ctx, x + 16 * s + i * 14 * s, y + 14 * s, 5 * s, c, a)
    for i, (off, ww, c) in enumerate(((0, 0.5, "#7DD3FC"), (16, 0.6, "#A7F3D0"), (16, 0.4, "#FCA5A5"), (0, 0.3, "#7DD3FC"))):
        box(ctx, x + (14 + off) * s, y + (34 + i * 16) * s, w * ww, 7 * s, 3, c, a=a)


def icon_lock(ctx, cx, cy, s=1.0, a=1.0, color=None):
    col(ctx, color or PAL["muted"], a)
    ctx.set_line_width(12 * s)
    ctx.arc(cx, cy - 14 * s, 32 * s, math.pi, 2 * math.pi)
    ctx.stroke()
    box(ctx, cx - 50 * s, cy - 14 * s, 100 * s, 76 * s, 14 * s, color or PAL["muted"], a=a)
    circle(ctx, cx, cy + 22 * s, 10 * s, PAL["background"], a)


def icon_clock(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    circle(ctx, cx, cy, 56 * s, PAL["card"], a)
    col(ctx, color or PAL["title"], a)
    ctx.set_line_width(5 * s)
    ctx.arc(cx, cy, 56 * s, 0, 2 * math.pi)
    ctx.stroke()
    for ang, ln in ((t * 0.3, 30), (t * 3.6, 44)):
        ctx.move_to(cx, cy)
        ctx.line_to(cx + math.sin(ang) * ln * s, cy - math.cos(ang) * ln * s)
        ctx.stroke()


def icon_rocket(ctx, cx, cy, s=1.0, a=1.0, color=None, t=0.0):
    cy += math.sin(t * 4) * 4 * s
    glow(ctx, cx, cy + 62 * s, 46 * s, PAL["warn"], 0.6 * a)
    col(ctx, color or PAL["accent"], a)
    ctx.move_to(cx - 26 * s, cy + 30 * s)
    ctx.line_to(cx - 48 * s, cy + 56 * s)
    ctx.line_to(cx + 48 * s, cy + 56 * s)
    ctx.line_to(cx + 26 * s, cy + 30 * s)
    ctx.fill()
    box(ctx, cx - 26 * s, cy - 40 * s, 52 * s, 90 * s, 24 * s, PAL["card"], PAL["border"], 2, a=a)
    col(ctx, color or PAL["accent"], a)
    ctx.move_to(cx - 26 * s, cy - 28 * s)
    ctx.curve_to(cx - 24 * s, cy - 60 * s, cx, cy - 70 * s, cx, cy - 70 * s)
    ctx.curve_to(cx, cy - 70 * s, cx + 24 * s, cy - 60 * s, cx + 26 * s, cy - 28 * s)
    ctx.fill()
    circle(ctx, cx, cy - 4 * s, 12 * s, PAL["primary"], a)


def icon_target(ctx, cx, cy, s=1.0, a=1.0, color=None):
    for i, r in enumerate((56, 40, 24, 10)):
        circle(ctx, cx, cy, r * s, (color or PAL["accent"]) if i % 2 == 0 else "#FFFFFF", a)


def icon_number(ctx, cx, cy, s=1.0, a=1.0, color=None, label="1"):
    circle(ctx, cx, cy, 52 * s, color or PAL["primary"], a)
    text(ctx, label, cx, cy, 56 * s, "#FFFFFF", True, "center", a)


ICONS = {
    "doc": icon_doc, "document": icon_doc, "deck": icon_deck, "slides": icon_deck, "chart": icon_chart,
    "gear": icon_gear, "settings": icon_gear, "bulb": icon_bulb, "idea": icon_bulb, "cloud": icon_cloud,
    "globe": icon_globe, "web": icon_globe, "calendar": icon_calendar, "check": icon_check, "ok": icon_check,
    "warning": icon_warning, "alert": icon_warning, "question": icon_question, "people": icon_people,
    "team": icon_people, "robot": icon_robot, "ai": icon_robot, "code": icon_code, "lock": icon_lock,
    "security": icon_lock, "clock": icon_clock, "time": icon_clock, "rocket": icon_rocket, "launch": icon_rocket,
    "target": icon_target, "goal": icon_target,
}


def draw_icon(ctx, name, cx, cy, s=1.0, a=1.0, t=0.0, color=None, label=""):
    """Draw a named icon. Unknown names fall back to a numbered badge showing `label` or the name's initial."""
    if a <= 0 or not name:
        return
    fn = ICONS.get(str(name).lower())
    kw = {}
    if fn is None:
        fn, kw = icon_number, {"label": label or str(name)[:2].upper()}
    elif fn in (icon_calendar,):
        kw = {"label": label}
    elif "t" in fn.__code__.co_varnames:
        kw = {"t": t}
    fn(ctx, cx, cy, s, a, color, **kw)
