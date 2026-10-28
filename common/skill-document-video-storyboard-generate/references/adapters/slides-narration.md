# Adapter: Slides + narration

```bash
python scripts/source_to_storyboard.py -s storyboard.json --target slides -o slides.md     # Pandoc Markdown
python scripts/source_to_storyboard.py -s storyboard.json --target slides -o deck.pptx     # direct .pptx
```

`.pptx` output uses the `pandoc` CLI if present, otherwise `pypandoc` (`pip install pypandoc_binary`).

## Mapping

| Storyboard | Slide |
|---|---|
| `heading` → `on_screen` → `title` | Slide title (`##`) |
| `items[]` | Bullets: **label** — text |
| `center`, `on_screen` (when heading exists), `subheading` | Italic sub-line |
| `voiceover` | Speaker notes (`::: notes`) |
| `duration`, `visual` | Appended to notes as `(~Ns; visual: …)` — a cue for the presenter / designer |
| `title` (top level) | Title slide — skipped when scene 1 already uses the `title` layout |

## Turning it into a video

1. **PowerPoint** — open the deck, *Record → Record from beginning* reading the notes, then *File → Export → Create a
   Video*. Or apply `skill-document-ppt-design` first for layout polish.
2. **Google Slides / Vids** — import the .pptx into Google Slides, then in Vids *Create from Slides*; paste each note as
   the scene script.
3. **Fully automatic** — skip slides and use the programmatic-render adapter on the same storyboard.

## Rules

- ≤ 6 bullets per slide; bullets are nouns/short phrases — the story lives in the notes.
- Never read bullets aloud verbatim ("first, second, third"); the VO explains *why* they connect.
- One idea per slide; split a scene with > 6 items into two.
