# Adapter: Google Vids / Gemini Omni

`python scripts/source_to_storyboard.py -s storyboard.json --target vids -o master_prompt.txt`

## Hard limits / 硬性限制

| Item | Limit | Practice |
|---|---|---|
| Aspect | `16:9` or `9:16` | 16:9 for explainers / decks; 9:16 for Shorts / Reels |
| Scene length | 3–10 s | 4–6 s for dense info; 7–9 s for establishing / emotional holds |
| Total length | ~60–180 s | 10–16 scenes for a 60–90 s piece |
| Voiceover | built-in TTS | Respect the word budget (zh 3.5–4 字/s, en ≈ 2.5 words/s) |

`--lint --target vids` fails (exit 1) on scenes outside 3–10 s and on AI-slop phrases.

## Master-prompt layout

```text
Create a <N>-second <style> video titled "<title>".

--- GOAL & AUDIENCE ---            (optional: goal, audience)
Voiceover Language: English | Traditional Chinese (zh-TW)
Aspect Ratio: 16:9

--- VISUAL AESTHETIC GUIDELINES ---  (style_notes: palette hex codes, mascot, motion language)

--- SCENE-BY-SCENE STORYBOARD (N SCENES) ---
Scene 1 (4s) - <title>
- Visual: <five-element prompt>. Camera: <move>.
- On-Screen Text: "<headline>"
- Voiceover: "<line>"
```

## Tips

- Paste into Vids **Help me create** → *Generate from prompt*. Vids re-times scenes; check each scene's VO fits.
- Put palette hex codes and the mascot description in `style_notes` — Vids reuses them across scenes.
- Keep on-screen text short: Vids renders it as a text layer, long text wraps badly in 9:16.
- The same text file also renders locally: `python -m storyboard_render master_prompt.txt` (layouts are auto-picked; use
  the JSON for full layout control).
- Direct-import walkthrough: see the consumer repo's `Google_Vids_Direct_Import_Guide.md` if present.
