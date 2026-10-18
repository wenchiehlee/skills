---
name: skill-ux-synology-nas
description: "UX styling, Cyber Slate & Synology Blue palette, Armored Pangolin mascot, and MkDocs customizations for the wenchiehlee.quickconnect.to repository (wenchiehlee.synology.me on Synology NAS). Use this skill when designing, building, or refining private cloud dashboards, Docker container cards, Tailscale status, and DevOps documentation."
---

# skill-ux-synology-nas: Synology NAS & 私人雲端 DevOps 設計系統規範

本 Skill 規範 `wenchiehlee.quickconnect.to`（對外網域 `wenchiehlee.synology.me`）之整體視覺語彙、吉祥物品牌識別與 Material for MkDocs 覆寫架構。

## 1. 吉祥物識別：裝甲穿山甲 🛡️ (Armored Pangolin)
- **Symbol ID**: `#icon-pangolin-shield` (定義於 `UX-Deck/tokens/icons/animal-icons.svg`)
- **設計哲學**: 延續 ask-bridge 與 Lucide 的 1.6px 極簡幾何線條風格，將中世紀/賽博防禦盾牌外廓與層疊幾何裝甲鱗片（Scutes）完美融合。
- **象徵意義**: 私人雲端、硬體級防護屏障、數據資產自主性與極致穩健的 24/7 DevOps 服務。
- **Logo 呈現**: 透過 `docs/overrides/partials/logo.html` 嵌入向量 SVG，取代傳統點陣圖，在桌面頂欄與行動抽屜自帶霓虹微光與懸停微縮放互動。

## 2. 色彩基調與材質調性 (Cyber Slate & Synology Blue)
- **主品牌色 (Primary)**: `#0284c7` (Synology Cloud Blue)
- **深色底座 (Background Slate)**: `#0f172a` (Cyber Obsidian Slate)
- **霓虹微光 (Glow Accent)**: `#38bdf8` (Neon Cyan Shield Glow)
- **服務健康綠 (Operational Green)**: `#22c55e` (Container & Mesh Active)
- **卡片陰影與邊框**: `border: 1px solid #1e293b; background: rgba(30, 41, 59, 0.6); backdrop-filter: blur(8px);`

## 3. 字體系統 (Typography)
- **標準 UI 內文**: `Roboto`, `Noto Sans TC`, sans-serif
- **代碼與監控指標**: `Roboto Mono`, `JetBrains Mono` (Tabular Numbers)
- **人文標籤與註解**: `LXGW WenKai TC` (霞鶩文楷)

## 4. 跨專案無縫導航 (UX-Deck Sibling Nav)
- 頂部導航列右側配置 `.nas-header-home-pill` 磨砂膠囊按鈕：
  ```html
  <a href="https://wenchiehlee-money.github.io/UX-Deck/" class="nas-header-home-pill" title="回到 UX-Deck 主題首頁">
    <span class="nas-pill-icon">🏠</span>
    <span class="nas-pill-text">主題首頁</span>
  </a>
  ```
- 行動版響應式設計：小於 `60em` 時自動摺疊文字，僅保留優雅的 `🏠` 磨砂微光按鈕。
