---
name: skill-ux-homeassistant-tv
version: 1.3.0
description: >-
  10-foot UI design, glanceable frosted HUD overlays, and remote-control accessible popup notifications
  for HomeAssistant on Android TV. Use this skill when designing, building, or styling Home Assistant
  Lovelace dashboards, browser_mod dialogs, and Android TV notifications.
---

# UX Skill: HomeAssistant (Android TV 10-foot Popup UI & PiPup HUD)

> **Version**: `1.3.0` | **Updated**: `2026-10-23` | **Release Note**: 實體電視驗證升級：確立「透明 PNG 圓角毛玻璃 HUD (Solution B)」為電視極致美感標準；完整整合客廳守護靈犬吉祥物 (`#icon-sentinel-tv` 🐕)、日雜圓體與零白框 60% 透光規格。；新增繁中/英文瀏覽器語系偵測與偏好記憶規則

This skill provides design guidelines, CSS specifications, PiPup REST API payloads, and HomeAssistant automation templates for **HomeAssistant on Android TV**, delivering high-visibility, elegant, non-intrusive living room popups.

## 10-Foot UI Principles & Hardware Constraints

1. **Viewing Distance Ergonomics (3–4 Meters)**:
   - Header font size: `20pt` (`titleSize: 20`, approx 26px–32px).
   - Body font size: `16pt` (`messageSize: 16`, approx 18px–22px).
   - Typography Stack: `Zen Maru Gothic` (日雜圓體 700) + `Comfortaa` + `Noto Sans TC`.
   - High contrast ratio: Crisp white text (`#f1f5f9` / `#ffffff`) over 60% translucent dark slate (`#660f172a` / `rgba(15, 23, 42, 0.40)`).

2. **Screen Docking Position (`position: 0` = TopRight)**:
   - Notifications dock exclusively to the **Top-Right** of the screen (`position: 0`).
   - Android PiPup Enum Mapping:
     - `0`: `TopRight` (標準首選：右上角，完全避開中央視線與底部電影字幕)
     - `1`: `TopLeft` (左上角)
     - `2`: `BottomRight` (右下角)
     - `3`: `BottomLeft` (左下角)
     - `4`: `Center` (中央置中)

3. **Background & Transparency Standard (60% Transparency)**:
   - Android / PiPup `#AARRGGBB` Color Format: `#660f172a`
     - Alpha `66` = 40% Opacity (60% Transparency).
     - RGB `0f172a` = Cyber Dark Slate.
   - CSS Equivalent: `rgba(15, 23, 42, 0.40)` with `backdrop-filter: blur(20px)`.

4. **Animal Mascot (客廳守護靈犬 Living Room Sentinel 🐕)**:
   - **Symbol**: `#icon-sentinel-tv` (from `animal-icons.svg`).
   - **Brand Colors**: Warm Caramel Amber (`#d97706` / `#f59e0b`) & Sky Cyan (`#38bdf8`).
   - **Visual Cue**: Subtle amber drop-shadow (`filter: drop-shadow(0 0 10px rgba(217, 119, 6, 0.5))`).
   - **Purpose**: Symbolizes loyal household vigilance; engineered with bold outlines and pricked ears for instant recognition from 3–4 meters away.

---

## 兩大實體部署方案比較與標準

| 維度 | 方案 A：Native 直角模式 | 方案 B：動態/預渲染透明 PNG (Solution B 首選) | Web 模式 (`media.web`) ❌ |
| :--- | :--- | :--- | :--- |
| **邊角效果** | 90° 俐落直角 (Android ColorDrawable 限制) | **18px ~ 24px 平滑真圓角** (`border-radius: 18px`) | 雖然網頁有圓角，但底層墊白底 |
| **背景透明度** | 60% 透光 (`#660f172a`)，完美穿透電視畫面 | **60% 透光暗黑毛玻璃** + 圓角外 100% 透明 | **失敗！Android WebView 預設白畫布導致大白框** |
| **吉祥物圖示** | 支援外部圖片（需固定寬高比） | **完美內嵌向量守護犬 `#icon-sentinel-tv` 🐕 與光暈** | 載入有延遲，白底突兀破壞觀影 |
| **字體渲染** | 系統預設字型（Roboto） | **Zen Maru Gothic (日雜圓體) + 3D 彩色 Emoji** | 系統 WebView 字型 |
| **底層技術** | PiPup 原生 TextView + Glide | **PiPup Glide 渲染 32-bit RGBA PNG (`#00000000` 底)** | Android WebView |
| **建議場景** | 極速輕量文字通知、零依賴環境 | **極致美感標準（UX-Deck Card 7 像素級 1:1 實體呈現）** | 嚴禁在未修改 APK 時使用 |

---

## Verified PiPup Notification Payloads

### 方案 B：極致美感圓角 HUD Payload (Solution B)

```json
{
  "duration": 15,
  "position": 0,
  "backgroundColor": "#00000000",
  "title": "",
  "message": "",
  "media": {
    "image": {
      "uri": "http://192.168.31.101:8123/local/huds/doorbell.png",
      "width": 480
    }
  }
}
```

> **提示**：Home Assistant 可將預渲染之透明 PNG 置於 `/config/www/huds/` 目錄，即可透過 `http://<ha-ip>:8123/local/huds/<scenario>.png` 本地極速提供給 Android TV，無須額外 Python 服務。

### 方案 A：極簡原生直角 Scrim Payload (Mode A)

```json
{
  "duration": 15,
  "position": 0,
  "title": "玄關訪客叮咚 🔔",
  "titleColor": "#38bdf8",
  "titleSize": 20,
  "message": "大門有人按門鈴，門鎖維持安全上鎖中 🐾",
  "messageColor": "#f1f5f9",
  "messageSize": 16,
  "backgroundColor": "#660f172a",
  "media": {
    "image": {
      "uri": "https://raw.githubusercontent.com/ZhongZheng782/HomeAssistant/main/custom_components/sentinel_icon.png",
      "width": 100
    }
  }
}
```

---

## Component Specs & Code

### 1. TV Notification Toast / HUD
See [tv-popup.css](./resources/tv-popup.css) for full styling.

### 2. Home Assistant Lovelace / Automation Configuration
See [tv-notification-card.yaml](./examples/tv-notification-card.yaml) for sample automation payloads (using `rest_command.pipup_tv_notify` or `browser_mod.popup`).

## Shared Language Behavior / 共用語言行為

Apply this policy whenever this skill is used to design or implement user-facing interfaces:

- Provide **English (`en`) and Traditional Chinese (`zh-TW`)** for interface labels, controls, navigation, and system messages.
- On first visit, use a previously saved valid user choice if available. Otherwise inspect the browser's primary locale (`navigator.languages[0]`, falling back to `navigator.language`): any locale beginning with `zh` selects `zh-TW`; every other locale selects `en`.
- Keep an accessible, visible language switch. When the user changes language, persist `zh-TW` or `en` in `localStorage` under `ux-language-preference`, restore that choice on later visits, and update the document's `lang` attribute. Never replace a saved user choice with browser detection.
- Do not machine-translate skill descriptions, user-authored text, names, tickers, units, or technical values just because the interface language changes. Translate interface copy where approved translations exist; preserve source content otherwise. Use locale-aware date/number formatting only when it does not alter domain meaning.
- For non-browser surfaces (such as Android TV notifications, generated images, and PDFs), use the host application's saved language preference. Do not assume browser APIs exist there; offer locale selection in the companion app or settings when that surface needs its own choice.
