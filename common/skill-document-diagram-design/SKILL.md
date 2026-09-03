---
name: skill-document-diagram-design
description: Generate editorial-quality diagrams (flowchart, sequence, quadrant, comparison table, timeline, tree, radar, sankey, mindmap, state, class/ER, org chart) as self-contained HTML+SVG, following the restrained design system from cathrynlavery/diagram-design, and export them for embedding in Docsify, Material for MkDocs, or PowerPoint. Also imports and redraws existing diagrams from PlantUML/Mermaid source or from a diagram image, so legacy PlantUML embeds (e.g. .planuml mindmaps) can be migrated to native SVG instead of depending on an external rendering server.
---

# 文件圖表設計技能（document-diagram-design）

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-document-diagram-design`） |
| 維護者 | wenchiehlee-money |
| 方法論來源 | https://github.com/cathrynlavery/diagram-design |

把「需要一張圖表」的需求，轉成可離線瀏覽的自含 HTML+SVG，再依目標平台（Docsify / Material for MkDocs / PowerPoint）匯出對應格式。核心原則是**克制**：每個節點都要有存在理由，accent color 只保留給讀者第一眼該看的 1–2 個元素，不做預設樣板的裝飾性圖表。

## 語言與風格

- 預設使用繁體中文（zh-TW）輸出說明文字；圖表內文字依使用者資料語言決定（技術文件通常保留英文術語）。
- 動手畫圖前，先問「讀者從這張圖學到的東西，會比一段寫清楚的文字多嗎？」不成立就不畫，直接建議用文字/表格。

## 📦 技能結構

```text
skill-document-diagram-design/
├── SKILL.md                        # 本檔案：選型與流程指南
├── metadata.json
├── self_update.py
├── references/
│   ├── style-guide.md              # 顏色/字型 token、克制美學原則
│   ├── diagram-types.md            # 圖表類型子集與選型表（可擴充）
│   ├── output-spec.md              # Docsify / MkDocs / PowerPoint 輸出規則
│   ├── plantuml-support.md         # PlantUML 匯入與淘汰路徑（含 InvestmentStackVision 案例）
│   └── import-redraw.md            # 文字 DSL / 圖片 / 既有 SVG 三種匯入來源的處理流程
├── scripts/
│   ├── import_plantuml_mindmap.py  # PlantUML mindmap → IR JSON（匯入用，不是輸出）
│   ├── render_plantuml.py          # 舊 PlantUML 圖表比對用渲染工具（遷移期間限定）
│   ├── svg_to_png.py               # 原生 HTML+SVG → PNG（Playwright，PPT 用）
│   └── svg_to_pptx.py              # 一組 PNG → .pptx（python-pptx）
└── assets/
    ├── template.html                          # 最小可用 scaffold（token 已對齊 style-guide.md）
    ├── example-org-chart.html                 # 範例：org-chart 類型，重繪自 diagram-design 的官方截圖案例
    ├── example-org-chart.svg                  # 上者的 Docsify/MkDocs 用獨立 SVG（class 樣式已內聯為字面色碼，不依賴外部 CSS）
    ├── example-mindmap-investment-stack.html  # 範例：mindmap 類型，遷移自 InvestmentStackVision.planuml（見 plantuml-support.md）
    ├── example-mindmap-investment-stack.svg   # 上者的獨立 SVG
    └── example-deck.pptx                      # 範例：上兩張圖依 output-spec.md 的 PowerPoint 流程組成的成品 .pptx
```

## ⚙️ 前置環境配置

依實際會用到的功能安裝：

```bash
# PowerPoint 匯出（HTML+SVG → PNG）
pip install playwright
playwright install chromium

# PowerPoint 組頁（PNG → .pptx）
pip install python-pptx pillow
```

Docsify／MkDocs 純輸出 SVG 不需要額外套件；PlantUML 匯入解析（`import_plantuml_mindmap.py`）只用標準函式庫。

## 🚀 使用流程

### 1. 判斷這是「新畫一張圖」還是「匯入既有圖表重畫」

- **新畫**：直接進第 2 步。
- **匯入既有 PlantUML/Mermaid 原始碼、圖片截圖、或既有 SVG/HTML**：先讀 `references/import-redraw.md`，走匯入流程，產出語意清單並與使用者確認後，才進入第 2 步當作「新畫」處理——匯入來源本身**不是**輸出格式，目的是取代它（尤其是依賴外部渲染伺服器的 PlantUML proxy 嵌入，見 `references/plantuml-support.md`）。

### 2. 選圖表類型

讀 `references/diagram-types.md`，依內容形狀（流程、比較、階層、時間序、分佈……）挑類型。找不到合適類型時，回 diagram-design 原始 repo 的對應規格頁補一列，不要硬套不合適的類型。

### 3. 依 `references/style-guide.md` 手刻原生 HTML+SVG

- 用 `assets/template.html` 當起點，或沿用專案既有的 `style-guide.md`（若呼叫端專案已有自訂色票/字型）。
- 座標取 4 的倍數、1px hairline 邊框無陰影、accent color 只用 1–2 處。
- 節點數超過 `diagram-types.md` 建議上限時，先問能不能拆成兩張圖，不要硬塞。
- 每張圖都要有 `role="img"`、`<title>`、`<desc>`（無障礙）。

### 4. 依目標平台匯出

讀 `references/output-spec.md`：

| 目標 | 指令/做法 |
|---|---|
| Docsify | 直接存 `.svg`，或把 `<svg>` 內聯進 Markdown |
| MkDocs Material | 存 `.svg` 到 `docs/assets/diagrams/`，用 `<figure markdown="span">` 包裝 |
| PowerPoint | `python scripts/svg_to_png.py <name>.html --out <name>.png` → 寫 `manifest.json` → `python scripts/svg_to_pptx.py manifest.json --out deck.pptx` |

## 🔁 PlantUML／Mermaid 遷移（重點案例）

使用者專案 `mkdocs-investment/docs/InvestmentStackVision.planuml`（PlantUML mindmap，透過 `plantuml.com/plantuml/proxy` 即時渲染嵌入 `docs/index.md`）是本技能要能處理的具體案例。完整流程見 `references/plantuml-support.md`，摘要：

```bash
# 1. 解析成 IR
python scripts/import_plantuml_mindmap.py InvestmentStackVision.planuml --out InvestmentStackVision.ir.json

# 2. 讀 IR，依 style-guide.md 手刻原生 SVG（Claude 執行，非腳本）

# 3. 依 output-spec.md 輸出 MkDocs 用 SVG，取代原本指向 plantuml.com 的 <figure> 區塊
```

`scripts/render_plantuml.py` 只在需要「看一眼舊圖現在長怎樣」以便對照時使用，遷移完成後即可不用。

## 🖼️ 圖片匯入（重繪）

使用者提供一張含圖表的圖片（截圖、掃描、匯出圖檔）時：

1. 用 Read 工具直接讀圖（Claude 為多模態模型，不需要另外寫 OCR/CV 腳本）。
2. 依 `references/import-redraw.md` 列出語意清單（節點、分組、連線、標籤），標出看不清楚/有歧義之處。
3. 決定細節（faithful/balanced/simplified）與受眾（engineer/mixed/executive）dial，預設 `balanced` + 依上下文判斷受眾。
4. 把語意清單回報使用者確認，避免語意落差。
5. 確認後依 `style-guide.md` 手刻原生 SVG，複雜或有明顯取捨時，在回覆裡簡述哪些節點被合併/簡化/捨棄。

## 🛡️ 穩健性設計與異常處理

- `import_plantuml_mindmap.py` 遇到無法解析的行會印警告並略過該行，不會中斷整體解析；深度異常的節點會掛回根節點並提示。
- `svg_to_png.py` 找不到指定 `--selector` 時，退回整頁截圖並提示，不直接失敗。
- `render_plantuml.py fetch` 連不上公開伺服器時，會提示改用 `PLANTUML_JAR` 本地渲染，不會靜默失敗。
- `svg_to_pptx.py` 遇到 `manifest.json` 中缺 `image` 欄位或圖片檔不存在的項目，略過該筆並印警告，不中斷整份簡報產生。
- 三個轉檔腳本在缺少對應相依套件（playwright / python-pptx / pillow）時，會印出明確的 `pip install` 指令再結束，不留下模糊的 stack trace。

## 安全邊界

- 不主動把圖表（尤其含內部資料的架構圖、財務圖）發布到公開服務；若使用者要求用外部 PlantUML/Mermaid 線上渲染服務，先確認資料是否可對外，敏感內容一律走本地渲染或本技能的原生管線。
- 圖片匯入時，若圖片內容明顯含個資或敏感資訊，先跟使用者確認是否要保留在重畫後的圖表裡，不要預設全部照抄。

## 🔄 版本管理與更新

- 本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-document-diagram-design`；各專案內的副本皆由登錄庫部署而來。
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
- 檢查並更新到登錄庫最新版本：
  ```bash
  python self_update.py
  ```
- 目前 `metadata.json` 的 `deployments` 只有 `registry` 一筆，尚未註冊 consumer 副本；之後要部署到其他專案時，補上對應的 `deployments` 項目再執行 `python self_update.py --deploy-all`。
