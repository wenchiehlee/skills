---
name: skill-ux-google-alert-manager
version: 1.2.0
description: >-
  UX styling, component patterns, and interaction design for GoogleAlertManager (GitHub Pages web dashboard).
  Use this skill when designing, building, or refining the alert feed triage, card layouts, filter chips,
  and signal-over-noise productivity interface for GoogleAlertManager.
---

# UX Skill: GoogleAlertManager (SaaS Signal Intelligence)

> **Version**: `1.2.0` | **Updated**: `2026-10-23` | **Release Note**: 吉祥物升級為破曉警報鳥 (Alert Bird 🐦, Lucide bird) 與活力警報橘 (`#ea580c`) 語意色調；新增繁中/英文瀏覽器語系偵測與偏好記憶規則

This skill provides the design system, component patterns, and interaction rules for **GoogleAlertManager**, turning high-volume feed clutter into an organized, rapid-triage intelligence dashboard.

## UX Principles & Identity

1. **Signal-over-Noise**: Emphasize actionable content, urgency ratings, and keyword matches over visual decorative elements.
2. **Rapid Triage Workflows**: Support 1-click archiving, snoozing, and starring, complete with keyboard shortcuts (`j`/`k` navigation, `e` archive, `s` star).
3. **Adaptive Density**: Offer comfortable card view vs compact table view for scanning 100+ alert entries effortlessly.
4. **Instant Visual Status**: Unread indicator dots, source badges (News, Web, Forum), and sentiment/urgency chips.
5. **Animal Mascot (破曉警報鳥 Alert Bird 🐦)**:
   - **Symbol**: `#icon-falcon-radar` (from [animal-icons.svg](../../tokens/icons/animal-icons.svg), Lucide 官方原生 `bird`).
   - **Color Tone**: **活力警報橘 (Alert Orange `#ea580c`)**，搭配 `#ffedd5` 底卡與 `#fed7aa` 邊框，徹底摒除偏紫冷色。
   - **Purpose**: 象徵第一時間破曉啼鳴、高敏感度穿透資訊雜訊的敏捷情報雷達。
   - **Application**: Placed on top header scout badge, rapid triage buttons, and high-urgency notifications.

---

## Component Architecture

### 1. Alert Card Component
Each alert card contains:
- **Header**: Source icon + domain badge + timestamp + unread pulse dot.
- **Body**: Highlighted title with keyword bolding + 2-line condensed snippet.
- **Action Toolbar**: Ghost button actions (Star, Mark Read, Snooze, Share, Open Link).

See [alert-card-component.html](./examples/alert-card-component.html) for the markup structure.

### 2. Quick Filter Chips Bar
Sticky top filter bar with quick counts:
```html
<div class="gam-filter-bar">
  <button class="gam-chip active">全部 (128)</button>
  <button class="gam-chip">未讀 (14)</button>
  <button class="gam-chip">高優先 (5)</button>
  <button class="gam-chip">已加星號 (23)</button>
</div>
```

### 3. Incorporating the Stylesheet
Link [alert-manager-theme.css](./resources/alert-manager-theme.css) into the main HTML head or bundle.

## Shared Language Behavior / 共用語言行為

Apply this policy whenever this skill is used to design or implement user-facing interfaces:

- Provide **English (`en`) and Traditional Chinese (`zh-TW`)** for interface labels, controls, navigation, and system messages.
- On first visit, use a previously saved valid user choice if available. Otherwise inspect the browser's primary locale (`navigator.languages[0]`, falling back to `navigator.language`): any locale beginning with `zh` selects `zh-TW`; every other locale selects `en`.
- Keep an accessible, visible language switch. When the user changes language, persist `zh-TW` or `en` in `localStorage` under `ux-language-preference`, restore that choice on later visits, and update the document's `lang` attribute. Never replace a saved user choice with browser detection.
- Do not machine-translate skill descriptions, user-authored text, names, tickers, units, or technical values just because the interface language changes. Translate interface copy where approved translations exist; preserve source content otherwise. Use locale-aware date/number formatting only when it does not alter domain meaning.
- For non-browser surfaces (such as Android TV notifications, generated images, and PDFs), use the host application's saved language preference. Do not assume browser APIs exist there; offer locale selection in the companion app or settings when that surface needs its own choice.
