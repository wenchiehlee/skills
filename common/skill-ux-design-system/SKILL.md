---
name: skill-ux-design-system
version: 1.2.0
description: >-
  Master UX Design System and unified visual language across sibling repositories
  (mkdocs-life, GoogleAlertManager, YoutubeAudio.Fetch, mkdocs-investment, HomeAssistant TV).
  Use this skill whenever crafting, refactoring, or evaluating user interfaces across these projects
  to maintain visual consistency while respecting each project's unique personality and UX purpose.
---

# UX-Deck Master Design System

> **Version**: `1.2.0` | **Updated**: `2026-10-23` | **Release Note**: 系統矩陣規格同步：更新 Android TV 10-foot HUD 為 60% 半透明 Cyber Dark Slate (`#660f172a`) 與右上角錨點 (`position: 0`)；新增繁中/英文瀏覽器語系偵測與偏好記憶規則

The UX-Deck Design System provides a cohesive visual architecture across our ecosystem of applications while preserving each project's domain-specific identity and functional needs.

## Ecosystem Overview & Differentiation Matrix

| Project | Platform / Target | Primary Aesthetic | Primary Mood | Core UX Goal |
| :--- | :--- | :--- | :--- | :--- |
| **mkdocs-life** | GitHub Pages (MkDocs) | Warm Editorial / Magazine | Reflective, Serene, Mindful | Distraction-free reading, journal storytelling |
| **GoogleAlertManager** | GitHub Pages (Web App) | SaaS Signal Intelligence | Sharp, Efficient, Productive | Rapid feed triage, signal-over-noise scanning |
| **YoutubeAudio.Fetch** | GitHub Pages (Web App) | Obsidian Soundwave Dark | Immersive, Modern, Tactile | Engaging playback, tactile queue management |
| **mkdocs-investment** | GitHub Pages (MkDocs) | High-Precision Fintech Slate | Institutional, Analytical, High-clarity | Dense financial metrics, KPI cards, table scanning |
| **HomeAssistant TV** | Android TV (PiPup / HUD) | 10-foot Frosted HUD (60% Translucent Dark Slate `#660f172a`) | Glanceable, Non-intrusive, Bold | Instant readability from 3–4m, Position 0 (TopRight) |

---

## 1. Unified Design Tokens

All sibling repositories inherit foundational tokens defined in [tokens.css](../../tokens/tokens.css):

### Spatial System (8pt Grid)
- **Base Grid**: Use multiples of `8px` (`--ux-space-xs: 8px`, `md: 16px`, `lg: 24px`, `xl: 32px`).
- **Half-steps**: Use `4px` (`--ux-space-2xs`) or `12px` (`--ux-space-sm`) for compact UI elements, icon-to-text spacing, or badge padding.

### Elevation & Depth
- **Level 1 (Card/List Item)**: `--ux-shadow-sm` (subtle separation).
- **Level 2 (Hover/Active/Dropdown)**: `--ux-shadow-md` (interactive elevation).
- **Level 3 (Modal / Floating Drawer)**: `--ux-shadow-lg` / `--ux-shadow-glass`.

### Micro-interactions & Motion
- All interactive controls (buttons, cards, links, tabs) must use smooth transitions:
  - Transition duration: `150ms` (hover/focus) to `250ms` (dialogs/menus).
  - Timing function: `cubic-bezier(0.2, 0, 0, 1)` (snappy ease-out).

---

## 2. Cross-Project Consistency Rules

When applying UX enhancements to any sibling repository:

1. **Accessibility Standards (WCAG 2.1 AA)**:
   - Contrast ratio must be at least **4.5:1** for regular body text and **3:1** for large text / UI borders.
   - Interactive elements must maintain explicit `:focus-visible` styling (minimum `2px` solid ring with `2px` offset).
2. **Typography Hierarchy**:
   - Establish a strict 3-tier heading structure with clear line heights (`1.2` for headings, `1.5-1.7` for body text).
   - Ensure Traditional Chinese fonts (`Noto Sans TC`, `PingFang TC`, `Microsoft JhengHei`) render crisply with optimal fallbacks.
3. **Empty & Loading States**:
   - Every list, table, or dashboard view must include designed empty states (explanatory illustration or icon + clear action button) and skeleton loading states.
4. **Adaptive Responsiveness**:
   - Mobile-first responsiveness from `360px` up to `4K` displays (with Android TV specialized for `1920x1080` / `3840x2160`).
5. **Animal Iconography & Mascot Refinements**:
   - Every sibling application features a distinct, mathematically aligned animal mascot on a `24x24` vector grid (`currentColor`, `1.75px` stroke width, `2.25px` on TV).
   - Read the complete [Animal Iconography Guide](./references/animal-iconography.md) and use the shared SVG sprite [animal-icons.svg](../../tokens/icons/animal-icons.svg).

---

## 3. Selecting the Right Skill

When working on a specific sibling repo, activate its dedicated skill:

- [skill-ux-mkdocs-life](../skill-ux-mkdocs-life/SKILL.md): Warm editorial styles, blog callouts, photo cards.
- [skill-ux-google-alert-manager](../skill-ux-google-alert-manager/SKILL.md): Alert feed cards, search chips, priority triage.
- [skill-ux-youtube-audio-fetch](../skill-ux-youtube-audio-fetch/SKILL.md): Dark obsidian media player, waveform bars, download progress.
- [skill-ux-mkdocs-investment](../skill-ux-mkdocs-investment/SKILL.md): Fintech dark/slate theme, KPI cards, sticky data tables.
- [skill-ux-homeassistant-tv](../skill-ux-homeassistant-tv/SKILL.md): 10-foot UI popups, D-pad focus outlines, frosted glass HUD.

## Shared Language Behavior / 共用語言行為

Apply this policy whenever this skill is used to design or implement user-facing interfaces:

- Provide **English (`en`) and Traditional Chinese (`zh-TW`)** for interface labels, controls, navigation, and system messages.
- On first visit, use a previously saved valid user choice if available. Otherwise inspect the browser's primary locale (`navigator.languages[0]`, falling back to `navigator.language`): any locale beginning with `zh` selects `zh-TW`; every other locale selects `en`.
- Keep an accessible, visible language switch. When the user changes language, persist `zh-TW` or `en` in `localStorage` under `ux-language-preference`, restore that choice on later visits, and update the document's `lang` attribute. Never replace a saved user choice with browser detection.
- Do not machine-translate skill descriptions, user-authored text, names, tickers, units, or technical values just because the interface language changes. Translate interface copy where approved translations exist; preserve source content otherwise. Use locale-aware date/number formatting only when it does not alter domain meaning.
- For non-browser surfaces (such as Android TV notifications, generated images, and PDFs), use the host application's saved language preference. Do not assume browser APIs exist there; offer locale selection in the companion app or settings when that surface needs its own choice.
