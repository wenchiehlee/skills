"""Load a storyboard from JSON or from a Vids/Gemini-style master-prompt text file.

Text format (English or Chinese headings are both accepted):

    Scene 2 (9s) - Title            /  場景 2（9 秒）- 標題
    - Visual: ...                    /  - 畫面: ...
    - On-Screen Text: "..."          /  - 畫面文字: 「...」
    - Voiceover: "..."               /  - 旁白: 「...」
"""
import json
import os
import re

DEFAULT_VOICES = {"en": "en-US-AndrewNeural", "zh": "zh-TW-HsiaoChenNeural", "ja": "ja-JP-NanamiNeural"}

_SCENE_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:Scene|場景|镜头|鏡頭)\s*(\d+)\s*[\(（]\s*(\d+(?:\.\d+)?)\s*(?:s|sec|秒)\s*[\)）]\s*[-–—:：]?\s*(.*)$",
    re.I | re.M)
_FIELDS = {
    "on_screen": r"On[- ]Screen(?: Text)?|畫面文字|螢幕文字|屏幕文字|字卡",
    "voiceover": r"Voice[- ]?over|VO|旁白|配音",
    "visual": r"Visual(?: Prompt)?|畫面|画面|視覺",
    "camera": r"Camera|運鏡|运镜|鏡頭運動",
    "sfx": r"SFX|Sound|音效",
}

ICON_HINTS = [
    (r"robot|agent|ai\b|機器人|代理", "robot"), (r"team|people|meeting|團隊|會議|使用者", "people"),
    (r"deck|slide|簡報", "deck"), (r"wiki|doc|document|文件|文檔", "doc"), (r"chart|data|analytics|數據|圖表", "chart"),
    (r"code|repo|github|程式|代碼", "code"), (r"calendar|schedule|行事曆|日曆", "calendar"),
    (r"clock|time|second|時間|秒", "clock"), (r"launch|rocket|start|啟動|上線", "rocket"),
    (r"security|lock|安全", "lock"), (r"idea|insight|light|靈感|洞察", "bulb"), (r"globe|world|global|全球", "globe"),
    (r"goal|target|目標", "target"), (r"warning|risk|problem|bottleneck|風險|問題|瓶頸", "warning"),
    (r"fog|unknown|question|迷霧|疑問", "question"), (r"cloud|雲", "cloud"), (r"check|done|success|完成|成功", "check"),
]


def _strip_quotes(s):
    s = s.strip()
    for a, b in (('"', '"'), ("\u201c", "\u201d"), ("\u300c", "\u300d"), ("'", "'")):
        if len(s) >= 2 and s.startswith(a) and s.endswith(b):
            return s[1:-1].strip()
    return s


def guess_icon(*texts):
    blob = " ".join(t for t in texts if t).lower()
    for pat, name in ICON_HINTS:
        if re.search(pat, blob):
            return name
    return None


def parse_text(txt):
    heads = list(_SCENE_RE.finditer(txt))
    if not heads:
        raise ValueError("No 'Scene N (Xs) - Title' headings found")
    scenes = []
    for i, m in enumerate(heads):
        blk = txt[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(txt)]
        sc = {"id": int(m[1]), "duration": float(m[2]), "title": m[3].strip()}
        for key, pat in _FIELDS.items():
            f = re.search(r"^\s*[-*]?\s*(?:%s)\s*[:：]\s*(.+?)\s*$" % pat, blk, re.I | re.M)
            if f:
                sc[key] = _strip_quotes(f[1])
        scenes.append(sc)
    header = txt[: heads[0].start()]
    meta = {}
    lang = re.search(r"Voice[- ]?over Language\s*[:：]\s*(\w+)|旁白語言\s*[:：]\s*(\S+)", header, re.I)
    if lang:
        v = (lang[1] or lang[2] or "").lower()
        meta["language"] = "zh-TW" if v.startswith(("chin", "中", "zh", "mandarin")) else "en-US"
    first = header.strip().splitlines()[0] if header.strip() else ""
    meta["title"] = first[:120]
    for hexc, key in ((r"Background[^#\n]*?(#[0-9A-Fa-f]{6})", "background"),):
        mm = re.search(hexc, header, re.I)
        if mm:
            meta.setdefault("palette", {})[key] = mm[1]
    for sc in scenes:
        sc.setdefault("icon", guess_icon(sc.get("visual"), sc.get("title")))
    meta["scenes"] = scenes
    return meta


def load(path):
    raw = open(path, encoding="utf-8").read()
    sb = json.loads(raw) if path.lower().endswith(".json") or raw.lstrip().startswith("{") else parse_text(raw)
    sb.setdefault("scenes", [])
    if not sb["scenes"]:
        raise ValueError("Storyboard has no scenes")
    if "language" not in sb:
        sample = " ".join(s.get("voiceover", "") for s in sb["scenes"])
        sb["language"] = "zh-TW" if re.search(r"[\u4e00-\u9fff]", sample) else "en-US"
    sb.setdefault("voice", DEFAULT_VOICES.get(sb["language"][:2], DEFAULT_VOICES["en"]))
    for i, sc in enumerate(sb["scenes"]):
        sc.setdefault("id", i + 1)
        sc.setdefault("duration", 6)
        sc.setdefault("voiceover", "")
        if not sc.get("heading") and sc.get("items") and sc.get("on_screen"):
            sc["heading"] = sc["on_screen"]
    sb["base_dir"] = os.path.dirname(os.path.abspath(path))
    return sb
