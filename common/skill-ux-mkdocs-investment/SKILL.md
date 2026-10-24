---
name: skill-ux-mkdocs-investment
description: >-
  Fintech design system, KPI metric widgets, financial table styling, and Material for MkDocs customizations
  for the mkdocs-investment repository (GitHub Pages). Use this skill when designing, building, or refining
  stock dashboards, investment research notes, financial tables, and asset tracking UIs.
---

# UX Skill: mkdocs-investment (High-Precision Fintech Slate)

This skill provides an institutional fintech aesthetic and dense analytical components for **mkdocs-investment**, delivering crystal-clear market metrics, stock screener tables, and asset allocation reports.

## Design Pillars

1. **Fintech Obsidian & Navy Palette**: Deep Navy background (`#0a0e17`) paired with Slate cards (`#131b2e`) to give financial charts and numbers high visual contrast.
2. **Precision Tabular Typography**: Tabular numbers (`tabular-nums`) with monospace alignment so decimals and columns line up effortlessly.
3. **Market Color Standards**:
   - Taiwan Market mode: **Red (`#ef4444`)** for Up/Gain, **Green (`#22c55e`)** for Down/Loss.
   - International / US Market mode toggleable via CSS variables.
4. **Sticky Financial Data Tables**: Sticky column headers with subtle borders and compact row heights (`36px-40px`) for rapid scanning across 50+ tickers.
5. **Glanceable KPI Metric Tiles**: Big bold figures with delta percentages and trend badges.
6. **Animal Mascots (幾何折紙公牛與風控熊 Origami Bull & Defensive Bear 🐂🐻)**:
   - **Symbols**: `#icon-bull-fintech` (Alpha momentum) & `#icon-bear-defense` (Downside hedging) from [animal-icons.svg](../../tokens/icons/animal-icons.svg).
   - **Purpose**: Instantly signals multi-factor momentum vs risk buffer in metric cards and screener rows.
   - **Application**: Placed beside delta percentages, index trackers, and portfolio health tiles.

---

## Component Guide

### 1. KPI Metric Summary Grid
Use `.fin-kpi-grid` and `.fin-kpi-card` to display portfolio or ticker fundamentals:

```html
<div class="fin-kpi-grid">
  <div class="fin-kpi-card">
    <div class="fin-kpi-label">總資產淨值 (TWD)</div>
    <div class="fin-kpi-value">$2,485,000</div>
    <div class="fin-kpi-delta gain">▲ +2.4% 今日損益</div>
  </div>
  <div class="fin-kpi-card">
    <div class="fin-kpi-label">本益比 (P/E Ratio)</div>
    <div class="fin-kpi-value">16.8x</div>
    <div class="fin-kpi-delta neutral">歷史中位數位階</div>
  </div>
</div>
```

### 2. High-Density Financial Tables
Wrap Markdown tables or use standard tables; the stylesheet applies sticky headers, monospace numerals, and hover highlighting automatically.

### 3. Implementation
- Stylesheet: Place [mkdocs-investment.css](./resources/mkdocs-investment.css) into `docs/stylesheets/extra.css`.
- KPI Example: View [kpi-widget.html](./examples/kpi-widget.html).

## Shared Language Behavior / 共用語言行為

Apply this policy whenever this skill is used to design or implement user-facing interfaces:

- Provide **English (`en`) and Traditional Chinese (`zh-TW`)** for interface labels, controls, navigation, and system messages.
- On first visit, use a previously saved valid user choice if available. Otherwise inspect the browser's primary locale (`navigator.languages[0]`, falling back to `navigator.language`): any locale beginning with `zh` selects `zh-TW`; every other locale selects `en`.
- Keep an accessible, visible language switch. When the user changes language, persist `zh-TW` or `en` in `localStorage` under `ux-language-preference`, restore that choice on later visits, and update the document's `lang` attribute. Never replace a saved user choice with browser detection.
- Do not machine-translate skill descriptions, user-authored text, names, tickers, units, or technical values just because the interface language changes. Translate interface copy where approved translations exist; preserve source content otherwise. Use locale-aware date/number formatting only when it does not alter domain meaning.
- For non-browser surfaces (such as Android TV notifications, generated images, and PDFs), use the host application's saved language preference. Do not assume browser APIs exist there; offer locale selection in the companion app or settings when that surface needs its own choice.
