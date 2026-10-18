---
name: skill-ux-mkdocs-life
version: 1.1.0
description: >-
  UX styling, design guidelines, and Material for MkDocs customizations for the mkdocs-life repository.
  Use this skill when enhancing the user experience, typography, layout, blog cards, or visual design
  of the mkdocs-life GitHub Pages website.
---

# UX Skill: mkdocs-life (Warm Editorial & Mindful Journal)

> **Version**: `1.1.0` | **Updated**: `2026-10-18` | **Release Note**: 字體系統升級為方案 A 溫潤隨筆文楷體（LXGW WenKai TC + Quicksand）與 Google Fonts v2 動態載入架構

This skill provides design patterns, CSS snippets, and layout rules for **mkdocs-life**, transforming standard MkDocs documentation into a graceful, warm, editorial-style personal journal and knowledge sanctuary.

## Visual Identity & Design Pillars

1. **Warm Paper Palette**: Soft cream/warm paper surfaces (`#faf8f5`) that reduce eye fatigue during long reading sessions.
2. **Editorial Typography (方案 A 溫潤隨筆文楷體)**:
   - **隨筆長文與標題**: `LXGW WenKai TC` (霞鶩文楷繁體) + 行距 `1.85 ~ 1.9`，營造手帳隨筆般親切溫暖的筆觸。
   - **標籤與英數**: `Quicksand` (圓潤休閒英數體) + `Noto Sans TC`。
   - **導航與按鈕**: `Noto Sans TC` (思源黑體) 保持清晰俐落。
3. **Journal & Timeline Elements**: Beautiful quote callouts, milestone timeline markers, and card grids with subtle hover lifts.
4. **Mindful Media Framing**: Rounded corners (`12px`) and gentle shadow framing for personal photos and journal screenshots.
5. **Animal Mascot (林鹿 Mindful Forest Deer 🦌)**:
   - **Symbol**: `#icon-deer-life` (defined in [animal-icons.svg](../../tokens/icons/animal-icons.svg)).
   - **Purpose**: Represents serene contemplation, graceful pacing, and mindful life journaling.
   - **Placement**: Embedded in log date badges, section dividers, and reflection callouts.

---

## Quick Start / Implementation

### 1. Include the Custom CSS & Icon Sprite
Ensure `docs/stylesheets/life-theme.css` is linked in `extra_css`.

### 2. Configure `mkdocs.yml`
In `mkdocs.yml`, set `font: false` to allow Google Fonts CSS2 modern dynamic loading via `docs/overrides/main.html`:

```yaml
theme:
  name: material
  custom_dir: docs/overrides
  favicon: assets/images/deer-favicon.png
  font: false # 由 overrides/main.html 與 life-theme.css 統一載入 Google Fonts v2
  palette:
    # Light Mode (Warm Editorial)
    - scheme: default
      primary: teal
      accent: deep orange
      toggle:
        icon: material/weather-night
        name: 切換至夜間模式
    # Dark Mode (Warm Slate Midnight)
    - scheme: slate
      primary: teal
      accent: deep orange
      toggle:
        icon: material/weather-sunny
        name: 切換至暖白模式

extra_css:
  - stylesheets/extra.css
  - stylesheets/life-theme.css
```

---

## Component Showcase

### A. Blog & Life Card Grid
Use Markdown HTML blocks or standard list formatting with the `.life-card-grid` class to display log entries as cards:

```html
<div class="life-card-grid">
  <div class="life-card">
    <div class="life-card-badge">2026-10-15</div>
    <h3>秋季山行筆記</h3>
    <p>走訪山林間的心得筆記與攝影記錄，在微涼秋意中沉澱思緒...</p>
    <a href="./posts/autumn-walk/" class="life-card-link">閱讀全文 &rarr;</a>
  </div>
</div>
```

### B. Mindful Callout / Reflection Box
```markdown
> [!NOTE] 生活反思
> 在快節奏的世界裡，保留一處安靜梳理心靈與目標的自留地。
```
The stylesheet styles this with warm terracotta accents and soft background tinting.

### C. Life Milestone Timeline
Add `.life-timeline` wrapper for milestone records:
```html
<ul class="life-timeline">
  <li>
    <strong>2026 Q3</strong>: 完成長跑目標與閱讀計畫
  </li>
  <li>
    <strong>2026 Q4</strong>: 全新生活日誌 UX Deck 改版上線
  </li>
</ul>
```
