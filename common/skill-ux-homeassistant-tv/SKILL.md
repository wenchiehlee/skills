---
name: skill-ux-homeassistant-tv
version: 1.1.0
description: >-
  10-foot UI design, glanceable frosted HUD overlays, and remote-control accessible popup notifications
  for HomeAssistant on Android TV. Use this skill when designing, building, or styling Home Assistant
  Lovelace dashboards, browser_mod dialogs, and Android TV notifications.
---

# UX Skill: HomeAssistant (Android TV 10-foot Popup UI & PiPup HUD)

> **Version**: `1.1.0` | **Updated**: `2026-10-18` | **Release Note**: 實體電視驗證升級：統一採用 60% 半透明 Cyber Dark Slate (`#660f172a`) 與右上角錨定 (`position: 0`)

This skill provides design guidelines, CSS specifications, PiPup REST API payloads, and HomeAssistant automation templates for **HomeAssistant on Android TV**, delivering high-visibility, elegant, non-intrusive living room popups.

## 10-Foot UI Principles & Hardware Constraints

1. **Viewing Distance Ergonomics (3–4 Meters)**:
   - Header font size: `20pt` (`titleSize: 20`, approx 26px–32px).
   - Body font size: `16pt` (`messageSize: 16`, approx 18px–22px).
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

4. **Corner Radius Handling (Native vs Web Mode)**:
   - **Native PiPup Notifications**:
     - PiPup draws backgrounds using Android native `view.setBackgroundColor()`, which binds to `ColorDrawable` (inherently 90° rectangular corners).
   - **True Rounded Corners (`border-radius: 20px - 24px`) via Web Mode**:
     - To achieve rounded corners on Android TV popups, deliver payload with transparent background (`backgroundColor: "#00000000"`) and web container:
       ```json
       "media": {
         "web": {
           "uri": "http://<ha-or-nas-host>:<port>/live_toast.html",
           "width": 460,
           "height": 130
         }
       }
       ```
     - The loaded HTML/CSS container handles rounded corners, soft borders, and CSS blur.

5. **D-pad Focus Navigation**:
   - Every interactive control must have an unmissable focus state: `3px solid #38bdf8` outline with a cyan glow (`box-shadow: 0 0 16px rgba(56, 189, 248, 0.6)`).

6. **Animal Mascot (客廳守護靈犬 Living Room Sentinel 🐕)**:
   - **Symbol**: `#icon-sentinel-tv` (from `animal-icons.svg`).
   - **Brand Colors**: Amber Warm (`#f59e0b`) & Sky Cyan (`#38bdf8`).
   - **Purpose**: Symbolizes loyal household vigilance; engineered with bold outlines and pricked ears for instant recognition from 3–4 meters away.

---

## Verified PiPup Notification Specification

### Standard REST Payload (`POST http://<android-tv-ip>:7979/notify`)

```json
{
  "duration": 10,
  "position": 0,
  "title": "洗衣提醒",
  "titleColor": "#38bdf8",
  "titleSize": 20,
  "message": "智慧洗衣機已運轉完成，請及時晾曬衣物。",
  "messageColor": "#f1f5f9",
  "messageSize": 16,
  "backgroundColor": "#660f172a",
  "media": {
    "image": {
      "uri": "https://raw.githubusercontent.com/ZhongZheng782/HomeAssistant/main/custom_components/sentinel_icon.png",
      "width": 140
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
