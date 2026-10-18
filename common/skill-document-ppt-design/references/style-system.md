# Style System

本技能支援七種視覺系統。所有風格共享相同的頁面規格與排版原則，但色票、幾何語言與美學氣質各異。

---

## 共用頁面規格

- **Aspect ratio**: 16:9
- **SVG viewBox**: `0 0 1280 720`
- **Safe margin**: 72 px minimum on all sides
- **Preferred content width**: 1040–1120 px
- **Grid**: 12 columns, 24 px gutters

---

## 1. Futuristic Tech Editorial

**適用**：AI、平台、工程、技術策略、資料導向商務簡報

### Palette
| Token | Value |
| :--- | :--- |
| Background | `#FFFFFF` |
| Primary text | `#2B2B2B` |
| Accent (electric blue) | `#2F6BFF` |
| Secondary text | `#6B6B6B` |
| Grid / dividers | `#E6EAF2` |
| Pale module fill | `#F7F9FC` |

### Typography
- Cover title: 56–76 px, weight 700–800
- Slide title: 36–48 px, weight 700–800
- Section label: 11–13 px, uppercase, weight 600–700
- Body: 18–24 px, weight 400–500
- Caption: 12–15 px
- Fonts: `Inter`, `Arial`, `Microsoft JhengHei`, sans-serif

### Non-Negotiables
- Canvas dominantly `#FFFFFF`
- Electric blue sparingly as signal, not decoration
- **Flat only**: no shadows, no glow, no glassmorphism, no gradients, no 3D
- Thin lines (1–2 px), grid fragments, numeric labels
- Asymmetric layout with deliberate grid alignment

---

## 2. Japanese Lifestyle Editorial

**適用**：品牌故事、商務提案、產品敘事、具雜誌感的專業簡報

### Palette
| Token | Value |
| :--- | :--- |
| Background | `#FFFFFF` |
| Primary text | `#1A1A1A` |
| Accent (焦橙) | `#C8581A` |
| Secondary text | `#6A6A6A` |
| Rule / divider | `#D6D0C8` |
| Highlight block | `#FFF8F0` |

### Typography
- Cover title: 64–80 px, weight 700
- Slide title: 40–52 px, weight 700
- Section label: 10–12 px, uppercase tracking 0.15 em
- Body: 18–22 px, weight 400
- Fonts: `Noto Serif JP` (fallback `Georgia`), `Microsoft JhengHei`

### Non-Negotiables
- Pure white background as dominant canvas
- Burnt orange accent strictly for emphasis and structural marks
- Non-symmetric image crops at edge or pressed into a corner
- High-contrast type, restrained color usage

---

## 3. Washi Paper & Soft Glow

**適用**：人文敘事、溫度型商務簡報、品牌理念、策略故事

### Palette
| Token | Value |
| :--- | :--- |
| Background (和紙米白) | `#F5F0E8` |
| Primary text | `#2C2C2C` |
| Accent (低彩靛藍) | `#5B7FA6` |
| Soft rule | `#D8D0C4` |
| Glow highlight | `#FDFAF4` |

### Typography
- Cover title: 52–68 px, weight 300–400 (light, airy)
- Slide title: 34–44 px, weight 400
- Body: 18–22 px, weight 300–400, line-height 1.6
- Fonts: `Noto Serif JP`, `Yu Mincho`, `Georgia`, `Microsoft JhengHei`

### Non-Negotiables
- Washi-tone background (never pure white)
- Generous white space; quiet, warm atmosphere
- Low-saturation indigo as the only accent
- No hard geometric lines; prefer soft hairlines

---

## 4. Soft 3D Clay

**適用**：輕盈科技簡報、友善產品說明、活潑但專業的策略簡報

### Palette
| Token | Value |
| :--- | :--- |
| Background (暖米色) | `#FDF5E6` |
| Sage green | `#B2AC88` |
| Morandi pink | `#DBADAD` |
| Dark text | `#3A3230` |
| Soft shadow fill | `#E8E0D4` |

### Typography
- Cover title: 56–72 px, weight 700–800, rounded feel
- Slide title: 36–48 px, weight 700
- Body: 18–22 px, weight 400
- Fonts: `Nunito`, `Rounded Mplus`, `Arial Rounded MT Bold`, `Microsoft JhengHei`

### Non-Negotiables
- Warm base canvas; soft, air-filled composition
- Rounded corners (8–16 px) on all shape elements
- Muted, desaturated palette only—no vivid primaries
- Elements may suggest depth with very soft neutral drop shadow (max 4 px, no color)

---

## 5. Minimalist Luxury Branding

**適用**：高端品牌提案、公司簡介、創辦人簡報、精品感商務敘事

### Palette
| Token | Value |
| :--- | :--- |
| Background (暖米色) | `#F5EFE6` |
| Accent (柔棕) | `#A68A64` |
| Primary text (深灰) | `#3A3A3A` |
| Divider | `#D4C9B8` |
| Light panel | `#EDE7DC` |

### Typography
- Cover title: 60–76 px, weight 300–400, serif
- Slide title: 38–50 px, weight 400, serif
- Section label: 10–12 px, uppercase, sans-serif
- Body: 18–22 px, weight 400, sans-serif
- Fonts: `Playfair Display`, `EB Garamond` / `Microsoft JhengHei`

### Non-Negotiables
- Serif headline + sans-serif body pairing (mandatory)
- Large margins, low density, luxury pacing
- Warm beige canvas only; no pure white
- No photography unless client-supplied; prefer geometric composition

---

## 6. Modern Illustration Editorial

**適用**：產品故事、策略解釋、工作流程、概念型插畫簡報

### Palette
| Token | Value |
| :--- | :--- |
| Background (柔米色) | `#F7F3EE` |
| Mist blue | `#A7C7E7` |
| Warm orange | `#E8A87C` |
| Charcoal text | `#2F2F2F` |
| Light separator | `#DDD8D0` |

### Typography
- Cover title: 56–72 px, weight 700
- Slide title: 36–48 px, weight 700
- Body: 18–22 px, weight 400
- Fonts: `DM Sans`, `Source Sans Pro`, `Microsoft JhengHei`

### Non-Negotiables
- Soft vector illustration as supporting element (not background pattern)
- Gentle gradient allowed only inside illustration objects
- Controlled restrained shadow (illustration only, max 6 px, 20% opacity)
- Layout integrates illustration with type; illustration never crowds the text

---

## 7. Japanese Hand-Drawn Editorial

**適用**：人文品牌、生活風格、創意流程、安靜細膩的概念型簡報

### Palette
| Token | Value |
| :--- | :--- |
| Background (暖白紙感) | `#F8F6F2` |
| Ink black | `#2B2B2B` |
| Soft gray | `#BDBDBD` |
| Low-chroma indigo | `#6C7A89` |
| Pale wash | `#EAE8E2` |

### Typography
- Cover title: 52–68 px, weight 400, brushstroke feel
- Slide title: 34–44 px, weight 400
- Body: 18–22 px, weight 300–400, line-height 1.65
- Fonts: `Zen Old Mincho`, `Noto Serif JP`, `Microsoft JhengHei`

### Non-Negotiables
- Hand-drawn line quality; intentional imperfection in strokes
- Thin pencil/ink outlines; watercolor-like fills at very low opacity
- Never mechanical or grid-perfect; slight variation in alignment is acceptable
- Calm, unhurried pacing; no decorative borders

---

## Universal Layout Rules（所有風格共用）

- Use **asymmetry**: one dominant block, one supporting cluster.
- Leave one side of the slide visibly quieter.
- Align text and modules to a clear grid.
- Prefer open modules over heavy cards.
- Avoid dense bullet lists; convert to labeled blocks, steps, timelines, or comparison modules.
- **Geometry**: line weight 1–2 px; corners 0–16 px depending on style.
- No SVG `filter`, `blur`, `feDropShadow`, or external image `href` in the final SVG spec.
