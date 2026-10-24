---
name: skill-ux-youtube-audio-fetch
description: >-
  UX styling, layout components, and multimodal sync controls for YoutubeAudio.Fetch (GitHub Pages web player & extractor).
  Use this skill when developing or improving the audio player interface, channel tabs, episode drawers,
  real-time transcript (lyrics-live) sync, and atmospheric media aesthetics for YoutubeAudio.Fetch.
---

# UX Skill: YoutubeAudio.Fetch (Studio Soundwave · 幻紫、串流青與純白)

This skill provides UI components, visual styling, and multimodal media controls for **YoutubeAudio.Fetch**, delivering a clean, high-fidelity YouTube audio extraction, podcast streaming, and live synchronized transcript listening experience.

## UX Identity & Design System

1. **Studio White & Clean Slate Basis**: Clean, luminous white background (`#ffffff` / `#f8fafc`) with subtle borders (`#e2e8f0`) and obsidian text (`#0f172a`), ensuring maximum clarity and reading comfort for long-form podcasts and financial morning calls.
2. **Sonic Violet Primary (`#8b5cf6` / `#7c3aed`)**: Electric violet for active tab gradients (`linear-gradient(135deg, #8b5cf6, #06b6d4)`), audio player buttons, and active episode indicators.
3. **Soundwave Cyan / Green Accent (`#06b6d4`)**: Vibrant cyan/teal for timestamps (`.ts`, `.date`), scrubber thumbs, category titles (`DAILY`, `PLAYLIST`), and dynamic transcript sync callout borders (`.lyrics-live`).
4. **Animal Mascot (聲波座頭鯨 Soundwave Singing Whale 🐋)**:
   - **Symbol**: `#icon-whale-sonic` (from [animal-icons.svg](../../tokens/icons/animal-icons.svg)).
   - **Mascot Glow Badge**: `linear-gradient(135deg, #8b5cf6 0%, #06b6d4 100%)` representing oceanic acoustic resonance, spectrum harmonics, and lossless audio fidelity.
   - **Application**: Placed on top brand bar (`.yaf-brand-bar`), favicon set, and media player identity headers.

---

## Key Components & Architecture

### 1. Sticky Floating Brand Bar (`.yaf-brand-bar`)
Stays pinned at the top with:
- Mascot glow badge (`#icon-whale-sonic` with `#8b5cf6 ~ #06b6d4` gradient)
- Site title & subtitle (`Atmospheric Media · 聲波座頭鯨`)
- Quick navigation pills: `🏠 主題首頁` (link to UX-Deck) and `📦 GitHub 儲存庫` (link to source repository).

### 2. Grouped Channel Pill Tabs (`.tabs` & `.tab-group`)
Classified into channel groups (`DAILY`, `PLAYLIST`) with pill-shaped buttons:
- Active state: `linear-gradient(135deg, #8b5cf6, #06b6d4)` with white typography and subtle violet glow.
- Inactive state: Pure white with cyan hover borders (`#06b6d4`).

### 3. Responsive Two-Column Streaming Layout
- **Left Column (Episode Drawer `.episode-list`)**:
  - Displays episode date, duration, phase status badges (`Phase 3` Gold, `Phase 2` Blue, `Phase 1` Sonic Violet), and title.
  - Active item features an accent left indicator border (`#8b5cf6`) and soft violet/cyan gradient tint.
- **Right Column (Player & Multimodal Sync `.main`)**:
  - **Themed Playback Control Panel (`.yaf-playback-panel`)**: Violet-to-cyan circular play/pause button (`linear-gradient(135deg, #8b5cf6, #06b6d4)`), smooth scrubber track with cyan playhead (`#06b6d4`), 15s skip controls, monospace timestamp (`JetBrains Mono`), animated spectrum wavebars, volume slider, and audio download button.
  - **Dynamic Live Transcript (`.lyrics-live`)**: Real-time scrolling transcript subtitle card with cyan left accent border (`#06b6d4`) and warm glow background.
  - **Video Keyframe Alignment (`.keyframe`)**: High-contrast video snapshot cards synchronized with audio playback timestamp.
  - **Topic Chapters & Cue List (`.cue-list`)**: Clickable timestamps with topic inferences for quick jumping.

---

## Real Deployed Reference
- **Live Site**: [https://zhongzheng782.github.io/YoutubeAudio.Fetch/](https://zhongzheng782.github.io/YoutubeAudio.Fetch/)
- **Repository**: [https://github.com/ZhongZheng782/YoutubeAudio.Fetch](https://github.com/ZhongZheng782/YoutubeAudio.Fetch)

## Shared Language Behavior / 共用語言行為

Apply this policy whenever this skill is used to design or implement user-facing interfaces:

- Provide **English (`en`) and Traditional Chinese (`zh-TW`)** for interface labels, controls, navigation, and system messages.
- On first visit, use a previously saved valid user choice if available. Otherwise inspect the browser's primary locale (`navigator.languages[0]`, falling back to `navigator.language`): any locale beginning with `zh` selects `zh-TW`; every other locale selects `en`.
- Keep an accessible, visible language switch. When the user changes language, persist `zh-TW` or `en` in `localStorage` under `ux-language-preference`, restore that choice on later visits, and update the document's `lang` attribute. Never replace a saved user choice with browser detection.
- Do not machine-translate skill descriptions, user-authored text, names, tickers, units, or technical values just because the interface language changes. Translate interface copy where approved translations exist; preserve source content otherwise. Use locale-aware date/number formatting only when it does not alter domain meaning.
- For non-browser surfaces (such as Android TV notifications, generated images, and PDFs), use the host application's saved language preference. Do not assume browser APIs exist there; offer locale selection in the companion app or settings when that surface needs its own choice.
