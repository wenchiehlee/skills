# Storyboard Schema / 中性分鏡格式

The storyboard is the single source of truth. Every adapter (`--target vids | ai-video | render | slides`) is a
pure function of this JSON, so write it once and regenerate deliverables when the story changes.
分鏡 JSON 是唯一真相來源；所有交付物都由它轉出。

## 1. Top level

| Key | Type | Required | Meaning |
|---|---|---|---|
| `title` | str | ✓ | Video title (also the slides deck title) |
| `language` | str | | `en-US` / `zh-TW` … auto-detected from voiceover if omitted |
| `voice` | str | | edge-tts voice for the renderer (default: `en-US-AndrewNeural` / `zh-TW-HsiaoChenNeural`) |
| `rate` | str | | TTS speed, e.g. `"+5%"` |
| `aspect_ratio` | str | | `16:9` (default) / `9:16` / `1:1` — the bundled renderer only outputs 16:9 |
| `style` | str | | `vector-explainer` / `cinematic` (see narrative-and-style-patterns.md) |
| `style_notes` | str | | Free-text style anchor; repeated verbatim in every AI-video prompt |
| `goal`, `audience` | str | | Used by the Vids adapter header |
| `palette` | obj | | Renderer colour overrides: `background`, `accent`, `primary`, `success`, `warn`, `title`, `cta_bg`, `series[]` … |
| `fonts` | obj | | Renderer font overrides: `latin`, `cjk`, `mono` |
| `music`, `subtitles` | bool | | Renderer toggles (default true) |
| `scenes` | list | ✓ | Ordered scenes (below) |

## 2. Scene

| Key | Type | Used by | Meaning |
|---|---|---|---|
| `id` | int | all | Scene number |
| `title` | str | all | Internal scene name (Vids heading line) |
| `duration` | num | all | Planned seconds. Renderer extends it to fit the voiceover |
| `act` | str | — | `setup` / `development` / `payoff` (narrative bookkeeping) |
| `voiceover` | str | all | Spoken line — obey the word budget in anti-ai-writing-guide.md |
| `on_screen` | str | all | Headline text (≤ 9 words / ≤ 16 CJK chars) |
| `heading` | str | render, slides | Title bar above the visual; slides use it as the slide title |
| `subheading` | str | render, slides | Secondary line (title / cta layouts) |
| `visual` | str | vids, ai-video | Five-element visual prompt: camera, framing, subject+action, light, texture |
| `camera` | str | vids, ai-video | e.g. `slow push-in`, `lateral truck` |
| `layout` | str | render | `title` `statement` `bullets` `cards` `flow` `hub` `timeline` `split` `stat` `quote` `cta` `image` (auto if omitted) |
| `items` | list | render, slides | `[{label, text, icon, color}]` or plain strings |
| `icon` | str | render | `robot people doc deck chart gear bulb cloud globe calendar check warning question code lock clock rocket target` |
| `character` | str | render | `robot` (default) / `people` / `none` |
| `center` | str | render (hub) | Hub centre label |
| `image` | str | render (image) | PNG path relative to the storyboard |
| `custom` | str | render | `"module:function"` plug-in drawn as `fn(ctx, t, dur, scene, env)` |
| `sfx`, `sfx_at` | str, num | render | `chime` `thud` `pop` `whoosh`, offset seconds |

Layout auto-pick: first scene → `title`, last → `cta`, ≥ 5 items → `bullets`, 2–4 items → `cards`, else `statement`.

## 3. Markdown scene card (human review format)

```markdown
### Scene [id]: [title]
- **Duration / 時長**: 5s | **Aspect / 畫幅**: 16:9 | **Layout**: cards
- **Camera / 鏡頭**: Medium close-up, slow pan left
- **Visual prompt / 視覺提示詞**:
  > [camera + framing + subject & action + light & colour + texture]
- **On-screen / 字卡**: [≤ 9 words]
- **Voiceover / 旁白**:
  > "[fits the word budget]"
- **Director note / 導演筆記**: [props, transition, sfx]
```

## 4. Minimal example

```json
{
  "title": "Release Day, Rewritten",
  "style": "vector-explainer",
  "scenes": [
    {"id": 1, "duration": 4, "layout": "title", "heading": "Release Day, Rewritten",
     "voiceover": "Release day used to take all afternoon."},
    {"id": 2, "duration": 7, "layout": "flow", "heading": "Three steps",
     "items": [{"label": "Collect", "icon": "doc"}, {"label": "Verify", "icon": "gear"}, {"label": "Report", "icon": "check"}],
     "voiceover": "It collects the tickets, verifies every build, and writes one page we can approve.",
     "visual": "Three cards slide in left to right, linked by drawn arrows. Flat vector, cream paper, soft shadows."}
  ]
}
```

Full examples: `examples/storyboard.en.json`, `examples/storyboard.zh-TW.json`.
