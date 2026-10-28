# Adapter: Programmatic render (pycairo + edge-tts + ffmpeg)

Deterministic, offline-capable MP4 with exact text, brand colours, CJK subtitles and no AI-video artefacts.

```bash
pip install pycairo numpy edge-tts          # ffmpeg must be on PATH
cd scripts
python -m storyboard_render ../examples/storyboard.en.json --preview          # PNG stills -> build_<name>/
python -m storyboard_render ../examples/storyboard.en.json                    # MP4 + SRT next to the input
python -m storyboard_render storyboard.json --out demo.mp4 --scenes 2 3       # partial render
python -m storyboard_render master_prompt.txt --no-tts --preview              # parse a Vids master prompt
python source_to_storyboard.py -s storyboard.json --target render -o resolved.json   # freeze auto layouts
```

## What it does

| Stage | Behaviour |
|---|---|
| Load | JSON storyboard, or `Scene N (Xs) - Title` text (English or `場景 N（X 秒）` headings, `畫面文字` / `旁白` fields) |
| TTS | edge-tts per scene, cached by hash(voice, rate, text) in `build_<name>/`; `--voice`, `--rate` override |
| Timing | scene = max(planned, 0.45 s lead + VO + 0.8 s tail); 0.5 s crossfade |
| Subtitles | word-boundary aligned; CJK chunked at punctuation (≤ 20 chars), Latin ≤ 64 chars; written to `.srt` too |
| Audio | synthesized pad + plucks, ducked under VO; per-scene `sfx` (`chime thud pop whoosh`) |
| Encode | 1920×1080 30 fps libx264 CRF 18 + AAC 192k, encoded in a temp dir, **fully decoded to verify**, then atomically moved — avoids corruption when the output folder is synced (SynologyDrive / OneDrive / Dropbox) |

## Layouts

`title statement bullets cards flow hub timeline split stat quote cta image` — see storyboard-schema.md.
Icons: `robot people doc deck chart gear bulb cloud globe calendar check warning question code lock clock rocket target`
(unknown names render as a numbered badge).

## Custom scenes

For a bespoke animation, write `mymod.py` with `def draw(ctx, t, dur, scene, env): ...` (pycairo context, `t` seconds
into the scene) and set `"custom": "mymod:draw"`. Import the helpers from `storyboard_render.core` (`bg`, `heading`,
`box`, `text`, `para`, `eo`, `prog`, `stroke_partial`, `flow_dots`…) and `storyboard_render.art` (`robot`, `person`,
`draw_icon`). Put `mymod.py` next to the storyboard JSON (that folder is added to `sys.path`).

## Fonts & CJK

The cairo toy API has no glyph fallback, so any string containing CJK switches to the `cjk` font
(Windows `Microsoft JhengHei`, macOS `PingFang TC`, Linux `Noto Sans CJK TC`). Override via `"fonts": {...}`.

## Limits

- 16:9 only (9:16 requests print a warning).
- Not photoreal — pair with the ai-video adapter and composite if live-action shots are needed.
