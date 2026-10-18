# Animal Iconography & Micro-Icon Refinements

This document establishes the animal iconography language across all five sibling repositories, balancing emotional connection, functional clarity, and cross-platform fidelity.

```
                   +---------------------------------------+
                   |  UX-Deck Animal Iconography Language  |
                   |   24x24 Base Grid · currentColor      |
                   +---------------------------------------+
                                       |
    +------------------+---------------+---------------+------------------+
    |                  |               |               |                  |
    v                  v               v               v                  v
[Forest Deer 🦌]  [Falcon 🦅]     [Whale 🐋]      [Bull 🐂/Bear 🐻]  [Sentinel 🐕]
mkdocs-life       AlertManager    YoutubeAudio    mkdocs-invest      HomeAssistant TV
(Mindful Peace)   (Swift Radar)   (Sound Wave)    (Alpha & Risk)     (10-ft Glance)
```

---

## 1. Icon Specifications & Crafting Rules

Every icon must adhere to our unified geometric constraints:

| Attribute | Specification | Rationale |
| :--- | :--- | :--- |
| **Coordinate Grid** | `24px x 24px` (48px for Android TV) | Crisp pixel alignment on 1x, 2x Retina, and 4K displays |
| **Live Area** | `20px x 20px` with `2px` padding | Prevents visual clipping on rounded buttons or circular avatars |
| **Stroke Width** | `1.75px` (`2.25px` for TV 10-foot UI) | Uniform visual weight across simple and complex silhouettes |
| **Cap & Join** | `round` (`stroke-linecap="round" stroke-linejoin="round"`) | Warm, organic, modern aesthetic |
| **Coloring** | `currentColor` | Seamlessly adapts to light/dark themes and accent states |

---

## 2. Animal Mascot Profiles & Psychological Role

### 🦌 1. mkdocs-life — 林鹿 (Mindful Forest Deer)
- **Symbol ID**: `#icon-deer-life`
- **Archetype**: Serene Observer & Knowledge Wanderer.
- **Visual Design**: Elegant vertical antlers branching into delicate geometry, calm eyes, soft organic curves.
- **Application**:
  - Blog post headers and life reflections.
  - Category tags (e.g., Reading, Hiking, Philosophy).
  - Micro-Interaction: Soft vertical hover float (`translateY(-2px)`) with terracotta tint.

---

### 🦅 2. GoogleAlertManager — 銳眼遊隼 (Peregrine Radar Falcon)
- **Symbol ID**: `#icon-falcon-radar`
- **Archetype**: Swift High-Altitude Scout & Precision Radar.
- **Visual Design**: Aerodynamic swept-wing silhouette, sharp curved beak, and a concentric dotted radar ring around the eye.
- **Application**:
  - Search bar scout icon and high-priority alert badges.
  - "Signal Captured" toast notifications.
  - Micro-Interaction: Sharp tilt (`rotate(-6deg) scale(1.1)`) with signal cyan drop-shadow.

---

### 🐋 3. YoutubeAudio.Fetch — 聲波座頭鯨 (Soundwave Singing Whale)
- **Symbol ID**: `#icon-whale-sonic`
- **Archetype**: Deep-Sea Acoustic Resonator.
- **Visual Design**: Sleek whale profile emerging through soundwave ripples; blowhole emitting acoustic frequency curves.
- **Application**:
  - Audio player bar playhead and visualizer mascot.
  - High-bitrate audio badge indicator (FLAC / 320kbps).
  - Micro-Interaction: Harmonic wave floating animation (`translateY(-2px) rotate(3deg)`).

---

### 🐂🐻 4. mkdocs-investment — 幾何折紙公牛與風控熊 (Origami Bull & Defensive Bear)
- **Symbol IDs**: `#icon-bull-fintech` / `#icon-bear-defense`
- **Archetype**: Capital Alpha Driver & Risk Guardian.
- **Visual Design**:
  - **Bull**: Origami faceted lines, upward-swept horns with a trend arrow apex.
  - **Bear**: Calm, sturdy rounded profile symbolizing defensive capital hedging and margin of safety.
- **Application**:
  - Ticker card momentum tags (Bull = Taiwan Red/US Green; Bear = Taiwan Green/US Red).
  - Portfolio quarterly review summary badge.
  - Micro-Interaction: Confident 45-degree upward micro-tilt on hover.

---

### 🐕 5. HomeAssistant TV — 客廳守護夜鷹/靈犬 (Living Room Sentinel)
- **Symbol ID**: `#icon-sentinel-tv`
- **Archetype**: Faithful Living Room Protector.
- **Visual Design**: Alert pricked ears, high-contrast oversized eyes optimized for 3–4m viewing, radar broadcast rings above head.
- **Application**:
  - Front door doorbell / security camera overlay popup.
  - Living room Android TV toast notification header.
  - Micro-Interaction: Remote D-pad focus glow expansion (`scale(1.15)` with `box-shadow: 0 0 16px #38bdf8`).

---

## 3. Implementation Code Patterns

### Inline SVG Sprite Usage (Recommended)
```html
<!-- Reference from tokens/icons/animal-icons.svg -->
<svg class="ux-icon ux-icon-deer" aria-hidden="true">
  <use href="#icon-deer-life"></use>
</svg>
```

### Pure CSS Icon Mask (Zero-DOM Overhead)
```css
.badge-deer::before {
  content: "";
  display: inline-block;
  width: 18px;
  height: 18px;
  background-color: var(--ux-life-primary);
  mask: url('/tokens/icons/animal-icons.svg#icon-deer-life') no-repeat center / contain;
  -webkit-mask: url('/tokens/icons/animal-icons.svg#icon-deer-life') no-repeat center / contain;
}
```
