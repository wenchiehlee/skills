---
name: skill-ux-tw-coverage
description: >-
  Taiwan stock equity research design system, valuation radar, financial metric badges, and report UI
  for the My-TW-Coverage repository (GitHub Pages). Use this skill when designing, building, or refining
  individual equity deep-dive notes, target price trackers, PER/PBR bands, and research coverage dashboards.
---

# UX Skill: My-TW-Coverage (Taiwan Equities Research Radar)

This skill provides an institutional equity research aesthetic and fundamental valuation components for **My-TW-Coverage**, empowering clear presentation of individual Taiwan stock coverage reports, consensus estimates, valuation bands, and catalyst tracking.

---

## 🌲 Design Pillars

1. **Taiwan Pine Emerald & Research Amber Palette**:
   - Primary: **Taiwan Pine Emerald (`#059669`)** — represents enduring enterprise vitality and core fundamental quality.
   - Accent: **Research Amber (`#d97706`)** — highlights target prices, analyst notes, and valuation catalysts.
   - Surface: **Clean White Studio Basis (`#ffffff`)** with subtle Slate borders (`#e2e8f0`) and soft card shadows (`var(--ux-shadow-sm)`).
2. **Institutional Market Standard Colors (TWSE Standard)**:
   - **Gain / Target Outperform**: Red (`#dc2626`)
   - **Loss / Downside Risk**: Green (`#16a34a`)
   - **Neutral / Hold**: Slate Gray (`#64748b`)
3. **Tabular Monospace Numerals (`JetBrains Mono`)**:
   - Stock tickers (e.g., `2330.TW`), target prices (`NT$1,250`), forward PER (`18.2x`), and quarterly EPS (`$45.80`) are strictly aligned using `font-family: "JetBrains Mono", monospace` and `tabular-nums`.
4. **Action-Oriented Recommendation Badges**:
   - High-contrast rounded pill badges: `BUY ↗ 強力買進`, `OUTPERFORM ↗ 優於大盤`, `HOLD → 維持中立`, `REDUCE ↘ 減碼觀望`.
5. **Animal Mascot (拍拍翅萌萌鴞 Chubby Flapping Owlet 🦉)**:
   - **Symbol**: `#icon-owl-coverage` from `tokens/icons/animal-icons.svg`.
   - **Aesthetic**: 1.6px geometric line stroke with chubby round body, flapping baby wings, and cute inquisitive eyes.
   - **Metaphor**: The vigilant nocturnal researcher that cuts through dense financial statements to uncover true value and downside margin of safety.

---

## 🧩 Component Guide

### 1. Equity Valuation Header Card
Used at the top of individual stock coverage reports (e.g., TSMC 2330.TW):

```html
<div class="coverage-card">
  <div class="coverage-header">
    <div>
      <div class="coverage-badge-row">
        <span class="coverage-pill pill-buy">BUY ↗ 強力買進</span>
        <span class="coverage-sector">半導體龍頭 · 核心覆蓋</span>
      </div>
      <h2 class="coverage-ticker">
        2330.TW 台積電
        <svg class="ux-icon ux-icon-owl"><use href="#icon-owl-coverage"></use></svg>
      </h2>
    </div>
    <div class="coverage-price-box">
      <div class="price-label">現價 / 12M 目標價</div>
      <div class="price-val">
        $1,085 <span class="price-target">/ $1,250</span>
      </div>
    </div>
  </div>

  <div class="coverage-thesis">
    <strong>萌萌鴞調研核心觀點：</strong>受惠於 3nm 滿載與 CoWoS-L 擴產進度超前，Q3 毛利率攀升至 57.8%，下檔本益比安全邊際具備高防禦力。
  </div>

  <div class="coverage-kpi-grid">
    <div class="coverage-kpi-tile">
      <div class="kpi-label">預估 PER</div>
      <div class="kpi-num">18.2x</div>
    </div>
    <div class="coverage-kpi-tile">
      <div class="kpi-label">預估 ROE</div>
      <div class="kpi-num highlight-gain">29.8%</div>
    </div>
    <div class="coverage-kpi-tile">
      <div class="kpi-label">全年預估 EPS</div>
      <div class="kpi-num">$45.80</div>
    </div>
  </div>
</div>
```

### 2. Research Catalyst & Earnings Quality Checklist
Presents fundamental drivers and margin of safety indicators cleanly:
- 營收動能 (MoM / YoY Momentum)
- 自由現金流充沛度 (Free Cash Flow Margin)
- 籌碼與法人動向 (Institutional Ownership)
- 估值評價河流圖位置 (PER / PBR Band Position)

---

## 🎨 CSS Styling Reference

Include the following styles in your MkDocs or web dashboard stylesheet:

```css
.coverage-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  padding: 1.75rem;
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.05);
  font-family: "Inter", "Noto Sans TC", sans-serif;
}

.coverage-pill.pill-buy {
  background: #ecfdf5;
  color: #059669;
  border: 1px solid #a7f3d0;
  padding: 2px 10px;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 700;
  font-family: "JetBrains Mono", monospace;
}

.coverage-kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-top: 1.25rem;
}

.coverage-kpi-tile {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 1rem;
  text-align: center;
}

.coverage-kpi-tile .kpi-num {
  font-family: "JetBrains Mono", monospace;
  font-size: 1.25rem;
  font-weight: 800;
  color: #0f172a;
}
```
