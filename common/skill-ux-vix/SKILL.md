---
name: skill-ux-vix
version: 1.0.0
description: >-
  UX styling, design system tokens, and Plotly wrapper architecture for the VIX repository (wenchiehlee-money.github.io/VIX).
  Use this skill when designing, building, or refining the Taiwan VIX vs TAIEX dual-axis volatility radar, crash stress tests,
  Black Swan branding, and standalone Plotly HTML shell.
---

# UX Skill: VIX (Global Volatility Radar & Crash Sentinel)

> **Version**: `1.0.0` | **Updated**: `2026-10-20` | **Mascot**: 幾何黑天鵝 (Black Swan · Vecteezy 70781740)

This skill provides the design system, Plotly shell components, and brand tokens for **VIX (Global Volatility Radar)**, integrating long-term financial market sentiment with institutional institutional crisis stress testing.

---

## 🖤 Design Pillars & Identity

1. **Obsidian Dark & Panic Spectrum Palette**:
   - Primary Surface: **Obsidian Dark (`#0f172a`)** — represents deep ocean calm, extreme risk vigilance, and institutional seriousness.
   - Panic Red: **`#ef4444`** — triggers above the critical threshold of 30 (`恐慌臨界點 (30)`), indicating extreme market panic and tail risk hedging demand.
   - Alert Orange: **`#f97316`** — indicates elevated volatility (20~35) and market watch.
   - Complacency Green: **`#10b981`** — represents calm market conditions (< 20) and low implied volatility.
   - Tracker Blue: **`#0284c7`** / **`#38bdf8`** — represents TAIEX benchmark trajectory and liquidity depth.

2. **Animal Mascot (幾何黑天鵝 Geometric Black Swan 🦢)**:
   - **Symbol**: `#icon-swan-vix` from `tokens/icons/lucide/lucide-swan.svg`.
   - **Aesthetic**: Geometric minimalist vector curves depicting a proud, solitary black swan with sleek crown, curved neck, and layered wings.
   - **Metaphor**: Nassim Taleb's *The Black Swan* — represents low-probability, extreme-impact market events, defensive asymmetry, and tail risk sentinel.

3. **Plotly Dual-Axis Interactive Standard**:
   - Left Axis (Y1): **VIX 指數 (0~90)** — tracks US VIX (`#ef4444`) and Taiwan VIX (`#10b981`).
   - Right Axis (Y2): **TAIEX 指數 (0~50k+)** — tracks Taiwan Weighted Index with sky-blue area gradient fill.
   - Threshold Line: **恐慌臨界點 (30)** — red dashed horizontal line (`#ef4444`, `stroke-dasharray="6,4"`).
   - Event Shading & Flags: Historical crash stress periods (2011, 2015, 2018, 2020, 2022, 2024) highlighted with translucent backgrounds and red flags (🚩).

---

## 🧩 Standalone HTML Shell Architecture

In the `wenchiehlee-money/VIX` repository, wrap the Plotly figure with the standard UX-Deck shell:

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Taiwan VIX vs TAIEX · 全球波動率雷達 (VIX Radar)</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23ef4444'%3E%3Cpath d='M 12 3 C 8 3 4 8 4 13 C 4 18 8 21 12 21 C 16 21 20 18 20 13 Z'/%3E%3C/svg%3E">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700;800&family=Noto+Sans+TC:wght@400;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body style="background: #f8fafc; font-family: 'Inter', 'Noto Sans TC', sans-serif; margin: 0; padding: 24px;">

  <!-- Brand Navigation Header -->
  <header style="max-width: 1400px; margin: 0 auto 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; background: #0f172a; padding: 14px 24px; border-radius: 14px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.12);">
    <div style="display: flex; align-items: center; gap: 12px;">
      <!-- Black Swan SVG -->
      <span style="font-size: 1.5rem;">🦢</span>
      <div>
        <h1 style="margin: 0; font-size: 1.15rem; font-weight: 800; color: #ffffff;">Taiwan VIX vs TAIEX · 全球波動率雷達</h1>
        <div style="font-size: 0.76rem; color: #94a3b8; margin-top: 2px;">台美日波動率指標、CNN 恐懼與貪婪指數及黑天鵝崩盤回測</div>
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 12px;">
      <span style="font-size: 0.75rem; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 4px 10px; border-radius: 9999px; font-family: 'JetBrains Mono', monospace;">● 每日定時結算</span>
      <a href="https://wenchiehlee-ux.github.io/UX-Deck/" target="_blank" rel="noopener noreferrer" style="font-size: 0.8rem; background: #ffffff; color: #0284c7; text-decoration: none; padding: 6px 14px; border-radius: 9999px; font-weight: 700; box-shadow: 0 2px 6px rgba(0,0,0,0.08);">🎨 返回 UX-Deck 總看板 ↗</a>
    </div>
  </header>

  <!-- Plotly Canvas Wrapper Card -->
  <main style="max-width: 1400px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; padding: 20px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);">
    <!-- Plotly Graph Div inserted here -->
    {{ PLOTLY_DIV }}
  </main>

</body>
</html>
```
