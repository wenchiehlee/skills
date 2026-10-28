---
name: skill-document-video-storyboard-generate
description: Turn Wikipedia articles, PPT decks, specs or notes into a tool-neutral, anti-AI-slop video storyboard (voiceover + on-screen text + director-grade visual prompts), then export it to Google Vids / Gemini, Veo / Sora / Runway / Kling shot lists, a programmatic pycairo+edge-tts MP4 render, or slides with speaker notes. 將長文、簡報或規格轉成與工具無關的影片分鏡，並輸出至 Google Vids、AI 影片工具、程式化渲染或簡報旁白。
---

# Video Storyboard Generator / 影片分鏡產生器

Write the story **once** as a neutral storyboard, then export it to whichever video tool you use.
先寫出一份**與工具無關**的分鏡，再依目標工具輸出交付物。

> Replaces `skill-document-vids-prompt-generate` (v1, Google Vids only). 取代 v1 僅支援 Google Vids 的版本。

---

## Naming / 命名

`skill-<domain>-<object>-<action>` → **document** (input is documents/decks) · **video-storyboard** (deliverable) ·
**generate**. Category: `media-production`.

---

## Workflow / 工作流

```text
[Source: Wikipedia / PPT / spec / notes]   來源
        │
        ▼
Step 0  Style system ─ vector-explainer │ cinematic          風格體系
Step 1  Narrative    ─ 3-act arc │ timeline │ deck story     敘事結構
Step 2  Storyboard   ─ neutral JSON (scenes: VO, on-screen, visual, layout)   中性分鏡
Step 3  Anti-slop QA ─ word budget, ban lists, five-element visuals (--lint)  防 AI 罐頭
        │
        ▼
Step 4  Adapter  ─┬─ vids      → Google Vids / Gemini master prompt
                  ├─ ai-video  → Veo / Sora / Runway / Kling shot list
                  ├─ render    → MP4 + SRT (pycairo + edge-tts + ffmpeg)
                  └─ slides    → Markdown / .pptx with speaker notes
```

### Step 0 — Style system / 風格體系
- **`vector-explainer`** — tech, product, process, business decks. Warm cream `#F5F2EB`, flat shapes, one recurring
  mascot (teal robot + orange backpack). 技術、流程、商業簡報。
- **`cinematic`** — history, biography, science stories. 35 mm grain, real props, natural light, slow dolly.
  歷史、人物、科學發現。
- Pick one per video; keep the anchor identical in every scene. Details: `references/narrative-and-style-patterns.md`.

### Step 1 — Narrative / 敘事
- **Explainer (3-act)**: pain → why the obvious fix breaks → breakthrough + human sign-off.
  痛點 → 瓶頸 → 突破與閉環。
- **Wikipedia**: 5–12 causally linked facts on a timeline; end on a concrete object, not a moral.
- **Deck**: 1–2 scenes per slide; never read bullets aloud.

### Step 2 — Storyboard / 中性分鏡
Write `storyboard.json` per `references/storyboard-schema.md`. Every scene has `voiceover`, `on_screen`, `duration`;
add `visual` + `camera` for AI tools, and `layout` + `items` for the renderer/slides.
Draft from raw text if useful (then **rewrite by hand**):

```bash
python scripts/source_to_storyboard.py -i article.txt --style cinematic -o storyboard.json
```

### Step 3 — Anti-AI-slop QA / 防 AI 罐頭
- Voiceover: short sentences (zh 8–18 字), concrete verbs, no puffery ("In today's fast-paced world", 「值得注意的是」).
- Budget: zh ≈ 3.5–4 字/s, en ≈ 2.5 words/s; on-screen ≤ 9 words / ≤ 16 字.
- Visual = camera + framing + subject & action + light & colour + texture. No `8k`, `masterpiece`, `epic`.
- Run `python scripts/source_to_storyboard.py -s storyboard.json --target <t> --lint` (exit 1 on errors).
- Full rules: `references/anti-ai-writing-guide.md`.

### Step 4 — Export / 輸出

| Target | Command | Guide |
|---|---|---|
| Google Vids / Gemini | `--target vids -o master_prompt.txt` | `references/adapters/google-vids.md` |
| Veo / Sora / Runway / Kling | `--target ai-video --tool veo -o shots.md` | `references/adapters/ai-video-generic.md` |
| Programmatic MP4 | `cd scripts && python -m storyboard_render storyboard.json` | `references/adapters/programmatic-render.md` |
| Slides + narration | `--target slides -o deck.pptx` (or `.md`) | `references/adapters/slides-narration.md` |

All `--target` commands are `python scripts/source_to_storyboard.py -s storyboard.json …`.

**Choosing / 怎麼選**: need exact text, brand colours, CJK subtitles, zero cost → **render**. Need live-action or
cinematic footage → **ai-video**. Team lives in Google Workspace → **vids**. Presenter will narrate live or record in
PowerPoint → **slides**. Mix freely — they share one storyboard.

---

## Deliverable checklist / 交付檢查

- [ ] `storyboard.json` passes `--lint` for the chosen target
- [ ] Every VO fits its scene (renderer extends scenes automatically; Vids/AI tools do not)
- [ ] One style anchor reused verbatim across scenes
- [ ] Render target: `--preview` PNGs reviewed before the full render; output passes the built-in decode check
- [ ] Final scene is a concrete CTA, not a slogan

---

## Files / 檔案

| Path | Purpose |
|---|---|
| `scripts/source_to_storyboard.py` | Draft from text, lint, export to vids / ai-video / render / slides |
| `scripts/storyboard_render/` | Renderer package (`core` primitives, `art` mascots & icons, `layouts`, `loader`, `render`) |
| `examples/storyboard.en.json`, `examples/storyboard.zh-TW.json` | Working examples (en: title/split/flow/stat/cta; zh-TW: title/bullets/hub/timeline/cta) |
| `references/storyboard-schema.md` | JSON schema + Markdown scene card |
| `references/narrative-and-style-patterns.md` | Style systems, 3-act arc, source modes, pacing |
| `references/anti-ai-writing-guide.md` | Ban lists, cadence, word budget, prompt grammar |
| `references/adapters/*.md` | Per-tool limits and tips |

Dependencies: Python 3.10+; renderer needs `pycairo numpy edge-tts` + `ffmpeg`; `.pptx` export needs `pandoc` or
`pypandoc_binary`.
