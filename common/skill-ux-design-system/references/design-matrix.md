# UX-Deck Design Differentiation & Consistency Matrix

This document details the aesthetic boundaries and consistency guidelines that connect our five sibling projects.

```
+--------------------------------------------------------------------------+
|                         UX-Deck Design Token Base                         |
|   8pt Spacing Grid | Smooth Bézier Curves | WCAG AA Contrast | Focus Rings |
+--------------------------------------------------------------------------+
           |                |                 |                 |
           v                v                 v                 v
   [ mkdocs-life ]   [ AlertManager ]   [ YoutubeAudio ]   [ Investment ]   [ HA Android TV ]
     Warm Teal &       Indigo SaaS       Obsidian Dark &     Fintech Slate &   10-ft Frosted
     Terracotta        Data Triage       Soundwave Violet    KPI Navy Deck     HUD Overlay
```

## Comparative Breakdown

### 1. Color Harmony & Palette

| Sibling | Primary Tone | Background / Surface | Accent / Indicator | Emotion |
| :--- | :--- | :--- | :--- | :--- |
| **mkdocs-life** | Deep Sage Teal (`#0d9488`) | Warm Paper Cream (`#faf8f5`) | Terracotta (`#e07a5f`) | Serene, reflective, natural |
| **GoogleAlertManager** | Electric Indigo (`#4f46e5`) | Clean Slate White (`#f8fafc`) | Signal Cyan (`#06b6d4`) | Crisp, organized, rapid |
| **YoutubeAudio.Fetch** | Vibrant Purple (`#8b5cf6`) | Pure Obsidian (`#0f0f13`) | Neon Cyan / Magenta | Tactile, immersive, media-focused |
| **mkdocs-investment** | Institutional Blue (`#2563eb`) | Dark Navy Slate (`#0a0e17`) | Emerald (`#10b981`) / Ruby (`#ef4444`) | Analytical, authoritative, precision |
| **HomeAssistant TV** | High-vis Sky Blue (`#38bdf8`) / Amber (`#f59e0b`) | 60% Translucent Dark Slate (`#660f172a` / `rgba(15,23,42,0.40)`) | Amber Warning (`#f59e0b`) | Glanceable, alert, living-room ambient (Position 0: TopRight) |

### 2. Interaction & Component Density

- **GoogleAlertManager & mkdocs-investment**: High density. Compact row heights (36px-44px), sticky headers, multi-column metrics, quick filter pills.
- **mkdocs-life**: Medium/Comfortable density. Generous paragraph line height (1.7), wide margins, elegant blockquotes, card margins (24px).
- **YoutubeAudio.Fetch**: Media interactive density. Large thumb-friendly scrubbers, animated volume sliders, expandable audio drawers.
- **HomeAssistant TV**: Low density / Ultra-large touch/focus targets. Minimum element height: 56px, active focus outlines: 3px-4px with glow, readable text at 3–4 meters.
