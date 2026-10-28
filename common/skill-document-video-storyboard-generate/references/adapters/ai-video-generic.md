# Adapter: Generic AI video (Veo / Sora / Runway / Kling)

`python scripts/source_to_storyboard.py -s storyboard.json --target ai-video --tool veo -o shots.md`

Text-to-video models generate **one clip per prompt** with no memory between prompts. The adapter therefore emits a
shot list: one fenced prompt per clip, each repeating the same **style anchor**.

## Clip caps (defaults — verify against current product docs, override with `--max-clip`)

| `--tool` | Default cap | Notes |
|---|---|---|
| `veo` | 8 s | Strong camera-language adherence |
| `sora` | 20 s | Longer takes; still split scenes > cap |
| `runway` | 10 s | Image-to-video works best with a keyframe |
| `kling` | 10 s | Good character motion |
| `generic` | 8 s | Safe default |

Scenes longer than the cap are split into `part 1/2 …` shots of equal length.

## Prompt grammar (one shot)

```text
<Camera move>. <Subject + concrete action in a concrete place>. <Light & colour>. <Texture / medium>.
<Style anchor>. Duration Ns, aspect 16:9. No on-screen text, no logos, no subtitles.
```

## Rules

1. **Consistency** — same `style_notes` anchor (palette hex, character description, lens) in every shot. For recurring
   characters, generate a reference still first and use image-to-video where the tool supports it.
2. **No text in-model** — models misspell text. Add on-screen text and subtitles in the editor (CapCut, Premiere,
   DaVinci, Clipchamp) using the `On-screen` and `VO` lines under each shot.
3. **One action per shot** — "robot hands over a report" is fine; "robot walks in, sits, types, then smiles" is not.
4. **Ban vague quality tags** (`8k`, `masterpiece`, `epic`) — see anti-ai-writing-guide.md.
5. **Voiceover** — generate separately (edge-tts, ElevenLabs, or `python -m storyboard_render --preview` timeline as a
   reference) and lay clips to the VO, not the other way round.
