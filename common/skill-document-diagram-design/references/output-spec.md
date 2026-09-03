# 輸出規格：Docsify / Material for MkDocs / PowerPoint

所有圖表一律先落地成一份**自含 HTML+SVG**（原生管線，見 `diagram-types.md`），再依目標平台轉出對應格式，避免三個平台各自維護一套產生邏輯。既有 PlantUML 圖表先依 `plantuml-support.md` 的流程匯入、改畫成原生 SVG，再套用本檔案的規則輸出——本文件描述的三平台規則不適用於「保留 PlantUML 原樣輸出」，因為本技能不提供這個選項。

## 共通流程

```text
需求 -> 選類型（diagram-types.md）-> （若來源是舊 PlantUML/Mermaid，先依 plantuml-support.md 匯入）
     -> 產出原生 HTML+SVG 來源檔
     -> 依目標平台轉出嵌入格式
```

## `.html` 來源檔 → `.svg` 匯出檔

原生管線手刻時用自含 `.html`（`<style>` 放在 `<head>`，用 `var(--token)` 對齊 `style-guide.md` 的色票，方便迭代/預覽）。要嵌進 Docsify/MkDocs 時，另外存一份 `.svg`：把 `<svg>` 內容抽出、`<style>` 移進 `<svg>` 內、`var(--token)` 全部換成字面色碼（standalone SVG 用 `<img>` 嵌入時不會套用 HTML 文件的 CSS 變數，必須自帶完整樣式）。兩個範例（`assets/example-org-chart.*`、`assets/example-mindmap-investment-stack.*`）都同時保留 `.html`（可編輯來源）與 `.svg`（可直接嵌入的成品），照這個慣例維護即可。

## Docsify

- 目標檔案：SVG（原生管線的 `.html` 抽出、去 CSS 變數後存成 `.svg`；PlantUML 管線用 `render_plantuml.py fetch --fmt svg`，僅限遷移期間比對用）。
- 建議存放路徑：呼叫端專案的 `docs/diagrams/<name>.svg`。
- 嵌入方式：
  ```markdown
  ![說明文字](diagrams/<name>.svg)
  ```
  或需要內聯控制樣式時，直接把 `<svg>...</svg>` 貼進 Markdown（Docsify 對內聯 HTML 支援良好）。
- 避免依賴外部 JS 套件（Docsify 站點常見離線/內網情境），因此**不要**用 Mermaid runtime 之類需要額外載入的方案，一律用靜態 SVG。

## Material for MkDocs

- 一律輸出**靜態 SVG**，存到 `docs/assets/diagrams/<name>.svg`，用 `<figure markdown="span">` 包起來取得標題列版式：
  ```markdown
  <figure markdown="span">
    ![說明文字](assets/diagrams/<name>.svg)
    <figcaption>Figure N 說明文字</figcaption>
  </figure>
  ```
- 若專案裡有舊的 PlantUML `proxy-src` 嵌入（例如 `mkdocs-investment` 的 `InvestmentStackVision.planuml`），依 `plantuml-support.md` 的遷移流程換成上面這種本地 SVG 寫法，不要保留對 `plantuml.com` 的外部依賴。
- Mermaid 只作為匯入來源（見 `diagram-types.md`），同樣不輸出 Mermaid 區塊。

## PowerPoint

PPTX 不支援內嵌動態渲染，所以一律先落地成點陣圖：

1. 原生管線（HTML+SVG）→ `scripts/svg_to_png.py`：用 headless Chromium（Playwright）截圖，預設 2x scale 確保投影機/大螢幕不糊。
2. 產出的 PNG 交給 `scripts/svg_to_pptx.py`：
   ```bash
   python scripts/svg_to_pptx.py manifest.json --out deck.pptx
   ```
   `manifest.json` 格式：
   ```json
   [
     {"title": "投資十步流程", "image": "flowchart.png", "notes": "對應 SKILL.md 十步判斷"},
     {"title": "Investment Stack Vision", "image": "InvestmentStackVision.png"}
   ]
   ```
   版型固定為 16:9，每筆一張投影片：上方標題、置中圖片（等比縮放、不裁切）、可選講者備忘稿。不做複雜版型變化——需要客製版型時，把產出的 PNG 手動貼進使用者既有的 PPTX 範本更實際。

## 選擇建議（速查）

| 目標 | 優先格式 | 理由 |
|---|---|---|
| Docsify | 靜態 SVG | 離線/內網友善，不依賴外部服務 |
| MkDocs Material | 靜態 SVG | 設計可控度最高；已用 PlantUML 的專案先依 `plantuml-support.md` 遷移 |
| PowerPoint | PNG（2x） | PPTX 只能吃點陣圖，2x 確保投影不糊 |
