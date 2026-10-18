---
name: skill-document-ppt-design
description: Design and generate editorial-quality PPT/PPTX slide decks as SVG or PPTX, following the design systems from software-ai-life/Awesome-PPT-Design-Skills. Supports multiple house styles (Futuristic Tech Editorial, Japanese Lifestyle Editorial, Washi Paper Soft Glow, Soft 3D Clay, Minimalist Luxury Branding, Modern Illustration Editorial, Japanese Hand-Drawn Editorial). Use for ppt-master workflows, slide deck design, SVG page generation, PPTX export, PDF-to-PPT transformation, Traditional Chinese presentations, and any scenario requiring a complete visual system for a presentation.
---

# 投影片設計技能（document-ppt-design）

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills（`common/skill-document-ppt-design`） |
| 維護者 | wenchiehlee |
| 方法論來源 | https://github.com/software-ai-life/Awesome-PPT-Design-Skills |

將任何來源（文件、PDF、會議紀錄、數據分析、投資報告）轉成具出版品質的投影片，依指定風格系統輸出 SVG 頁面與可編輯 PPTX。核心原則是**先讀懂內容，再套風格；一頁只保留一個清楚訊息**。

## 語言與風格

- 預設使用繁體中文（zh-TW）；內容語言依來源材料決定，可雙語輸出。
- 動手設計前，先問「這頁的核心訊息是什麼？」沒有清楚訊息就不展開設計。

## 📦 技能結構

```text
skill-document-ppt-design/
├── SKILL.md                          # 本檔案：風格選型、流程指南、使用限制
├── metadata.json
├── self_update.py
├── references/
│   ├── style-system.md               # 所有風格的色票、字型、版面、幾何規則
│   ├── slide-patterns.md             # 可重複使用的頁型（封面、論述、資料、比較…）
│   ├── ppt-master-integration.md     # 搭配 ppt-master 的 SVG spec lock 與產製流程
│   └── qa-checklist.md               # 交付前視覺 QA 清單
├── scripts/
│   └── svg_to_pptx.py                # 將 SVG 頁面批次組合為 .pptx（python-pptx）
└── assets/
    ├── template.html                  # 通用最小 scaffold（可作各風格起點）
    └── examples/
        └── 01_cover.svg               # 預設風格封面範例（Futuristic Tech Editorial）
```

## 🎨 風格系統（House Styles）

本技能支援以下七種視覺系統，依用途與受眾選擇：

| 風格名稱 | 適用場景 | 主色系 |
| :--- | :--- | :--- |
| **Futuristic Tech Editorial** | AI、平台、工程、技術策略、資料導向商務 | 純白 + 電光藍 + 石墨灰 |
| **Japanese Lifestyle Editorial** | 品牌故事、商務提案、產品敘事、具雜誌感 | 純白 + 焦橙 + 深炭灰 |
| **Washi Paper & Soft Glow** | 人文敘事、溫度型商務、品牌理念、策略故事 | 米白 + 柔光 + 低彩靛藍 |
| **Soft 3D Clay** | 友善產品說明、輕盈科技、活潑但專業策略 | 暖米色 + 鼠尾草綠 + 莫蘭迪粉 |
| **Minimalist Luxury Branding** | 高端品牌提案、公司簡介、創辦人簡報 | 暖米色 + 柔棕色 + 深灰文字 |
| **Modern Illustration Editorial** | 產品故事、策略解釋、工作流程、概念型 | 柔米色 + 霧藍 + 灰橘 |
| **Japanese Hand-Drawn Editorial** | 人文品牌、生活風格、創意流程、安靜細膩 | 暖白紙感 + 墨黑 + 低彩靛藍 |

詳細色票、字型規格與版面規則見 `references/style-system.md`。

## ⚙️ 前置環境

```bash
# SVG → PNG（供 PPTX 組合用）
pip install playwright
playwright install chromium

# PNG → PPTX
pip install python-pptx pillow
```

純輸出 SVG 不需要額外套件。

## 🚀 使用流程

### 1. 選定風格

從風格系統表選擇一個 house style，或依使用者指定風格名稱。若無指定，預設使用 **Futuristic Tech Editorial**。

- 同一份內容要比較不同風格時，先選定單一風格產完整 deck，再另開任務切換。
- 若有品牌規範（logo、色票、字體 guideline），優先使用品牌規範，以技能系統作 fallback。

### 2. 內容消化與頁面規劃

1. 讀取來源材料（文件、PDF、Markdown、CSV、投資報告……）。
2. 提煉核心敘事，決定頁數（3–10 頁為宜）。
3. 列出每頁的主要訊息，與使用者確認結構，再進入設計。

### 3. 套用 ppt-master 流程

依 `references/ppt-master-integration.md` 依序產出：

```text
1. 內容摘要與頁面規劃
2. Eight Confirmations（風格、頁數、受眾、語言、輸出格式）
3. design_spec.md
4. spec_lock.md
5. 逐頁 SVG（viewBox 0 0 1280 720）
6. 視覺 QA（對照 references/qa-checklist.md）
7. PPTX export（scripts/svg_to_pptx.py）
```

### 4. 逐頁 SVG 設計

- 用 `assets/template.html` 當起點，或使用 `references/style-system.md` 的 token 手刻。
- 從 `references/slide-patterns.md` 選定每頁的頁型（封面、論述、資料信號、系統圖、比較、時間軸、結尾）。
- 每頁保留一個清楚訊息；不塞超過 3–5 個模組。
- 遵守各風格的 Non-Negotiables（見 `references/style-system.md`）。

### 5. 視覺 QA

設計完成後，逐頁過 `references/qa-checklist.md`。常見問題：
- accent color 比例超過頁面 10%
- 字型或色碼不符指定風格
- SVG 含 filter / blur / shadow / 外部圖片連結
- 頁面訊息超過一個

### 6. PPTX 匯出（可選）

```bash
python scripts/svg_to_pptx.py --slides slides/ --output deck.pptx
```

`svg_to_pptx.py` 會先用 Playwright 將 SVG 轉為 PNG，再用 python-pptx 組成可編輯 `.pptx`。

## 🔗 相依技能

| 技能 | 用途 |
| :--- | :--- |
| `skill-pptx-to-md` | 把現有 PPTX 轉成 Markdown，作為來源材料 |
| `skill-document-diagram-design` | 需要嵌入圖表時，產生符合版面的原生 SVG 圖表 |
| `skill-company-decision-report` | 將投資決策報告轉成簡報頁面 |

## ⚠️ 限制

- 本技能是風格與流程規範，不是固定模板；最終品質取決於來源材料品質。
- 若使用者提供正式品牌規範，品牌規範優先，本技能系統為 fallback。
- SVG 內文字使用 `<text>` 元素，確保 PPTX 轉換後仍可編輯；不使用外部字型連結。
- Claymorphism / glassmorphism / 3D / 陰影等效果不列入 SVG 規格，僅在 Soft 3D Clay 風格的 CSS 層面使用，且轉 PPTX 時退回平面表示。

## 完成前檢查

- 指定風格已套用，色票、字型、版面規則符合 `references/style-system.md`。
- 每頁只保留一個清楚訊息；頁數合理（不為填滿頁數捏造內容）。
- SVG viewBox 為 `0 0 1280 720`；無 filter / blur / shadow / 外部連結。
- 已過 `references/qa-checklist.md`；品質問題已列出並告知使用者。
- PPTX 匯出前確認 Playwright + python-pptx 環境可用。
