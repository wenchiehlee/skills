# 輸出規格：Docsify / Material for MkDocs / PowerPoint / open-slide / mkslides

所有圖表一律先落地成一份**自含 HTML+SVG**（原生管線，見 `diagram-types.md`），再依目標平台轉出對應格式，避免各平台各自維護一套產生邏輯。既有 PlantUML 圖表先依 `plantuml-support.md` 的流程匯入、改畫成原生 SVG，再套用本檔案的規則輸出——本文件描述的平台規則不適用於「保留 PlantUML 原樣輸出」，因為本技能不提供這個選項。

**先判斷目標是「嵌進文件的一張圖」還是「簡報／投影片」**：前者才適用本檔案 Docsify/MkDocs/PowerPoint 三節；後者（尤其需要互動）改讀 `references/output-openslide.md`（React/Node 環境）或 `references/output-mkslides.md`（純 Python、Reveal.js），不要用 PowerPoint 流程硬做互動——pptx 格式本身沒有承載 JS 互動的能力。open-slide 與 mkslides 兩者互斥，依使用者的環境限制（能不能裝 Node）與互動複雜度需求二選一，不要同時做兩份簡報。

## 共通流程

```text
需求 -> 選類型（diagram-types.md）-> （若來源是舊 PlantUML/Mermaid，先依 plantuml-support.md 匯入）
     -> 產出原生 HTML+SVG 來源檔
     -> 依目標平台轉出嵌入格式
```

## `.html` 來源檔 → `.svg` 匯出檔

原生管線手刻時用自含 `.html`（`<style>` 放在 `<head>`，用 `var(--token)` 對齊 `style-guide.md` 的色票，方便迭代/預覽）。要嵌進 Docsify/MkDocs 時，依下面「互動性與嵌入方式」判斷走哪條分支：純靜態走「抽出獨立 `.svg`」，需要互動走「內聯 `<svg>`」——兩者不能都做到，選擇時先確認需求。

## 互動性與嵌入方式的關係（先讀這節再選嵌入方式）

SVG 規格本身支援 `:hover`/`:focus` 等 CSS 偽類、內嵌 `<script>` 的 JS 事件、以及 SMIL 動畫（`<animate>`），但**能不能生效，取決於嵌入方式，不是 SVG 本身**：

| 嵌入方式 | CSS `:hover` | JS `<script>` | 說明 |
|---|---|---|---|
| 內聯 `<svg>...</svg>` 直接貼進 Markdown | ✅ | ✅ | 瀏覽器把它當一般 DOM 節點，完整互動 |
| Markdown 圖片語法 `![alt](x.svg)`（→ 編譯成 `<img>`） | ❌ | ❌ | 瀏覽器把 SVG 當「安全靜態圖片」處理：不執行 script、不觸發互動事件，連 CSS hover 都不作用 |

**結論**：只要圖表需要任何互動（hover tooltip、點擊展開/收合），一律用內聯 `<svg>`，不能用 `![alt](x.svg)` 這種圖片語法——這點對 Docsify 和 MkDocs 都成立，是格式本身的限制，跟哪個框架無關。純靜態圖表（不需要互動）才用獨立 `.svg` 檔 + 圖片語法，好處是瀏覽器可以快取、Markdown 原始碼比較乾淨。

## Docsify

**純靜態**：目標檔案是獨立 SVG（原生管線的 `.html` 抽出、`var(--token)` 換成字面色碼後存成 `.svg`；PlantUML 管線用 `render_plantuml.py fetch --fmt svg`，僅限遷移期間比對用），存到呼叫端專案的 `docs/diagrams/<name>.svg`，用 `![說明文字](diagrams/<name>.svg)` 嵌入。

**需要互動**：把 `<svg>...</svg>` 原封不動貼進 Markdown（不是存成獨立檔案再用圖片語法引用），並注意 Docsify 是**執行期**用瀏覽器 JS 動態渲染 `.md`，內嵌 `<script>` 有框架層級的限制：

- `<script>` 預設不執行，要嘛在站台 `index.html` 設定 `executeScript: true`，要嘛頁面用了 Vue（Docsify 偵測到會自動開啟）。
- **一個頁面只會解析第一個 `<script>` 標籤**——同一頁若有多張互動圖表，各自的 JS 邏輯要合併寫進同一段 `<script>`，不能每張圖各帶一段。
- 只需要 hover 效果（不需要 JS 邏輯）時，純 CSS `:hover` 不受這個限制，是 Docsify 上最省事的互動做法。

避免依賴外部 JS 套件（Docsify 站點常見離線/內網情境），因此**不要**用 Mermaid runtime 之類需要額外載入的方案。

## Material for MkDocs

**純靜態**：輸出獨立 SVG，存到 `docs/assets/diagrams/<name>.svg`，用 `<figure markdown="span">` 包起來取得標題列版式：
  ```markdown
  <figure markdown="span">
    ![說明文字](assets/diagrams/<name>.svg)
    <figcaption>Figure N 說明文字</figcaption>
  </figure>
  ```

**需要互動**：把 `<svg>...</svg>` 原封不動貼進 Markdown。MkDocs 是**建置期**用 python-markdown 把 `.md` 轉成靜態 `.html` 檔，內嵌的 `<script>` 會被當成 raw HTML block 原封不動輸出進最終頁面，瀏覽器當一般靜態網頁執行——**沒有 Docsify 那種「單頁單 script」的限制**，一頁放多個各自帶 JS 的互動圖表都沒問題，是三個文件平台裡互動內嵌最省心的一個。

- 若專案裡有舊的 PlantUML `proxy-src` 嵌入（例如 `mkdocs-investment` 的 `InvestmentStackVision.planuml`），依 `plantuml-support.md` 的遷移流程換成本地 SVG 寫法（靜態或互動視需求擇一），不要保留對 `plantuml.com` 的外部依賴。
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

### pptx 原生互動：熱區跳轉與導覽按鈕

pptx 格式本身能承載的互動只有「超連結跳轉」與「預先定義好的播放動畫」兩種；後者的動畫時序（`<p:timing>`）沒有官方 API，本技能不提供。前者已經在 `svg_to_pptx.py` 支援，透過 `manifest.json` 的兩個選填欄位：

- `hotspots`：疊在圖片上的隱形可點擊矩形，`x/y/w/h` 是相對「圖片實際繪製範圍」（非整張投影片）的 0–1 比例，`target` 可填另一筆項目的 `id` 或 1-based 投影片編號。用於「點圖表裡的某個節點，跳到對應的詳細投影片」。
- `nav`：布林值，開啟後在該投影片右下角加上內建 action button（回首張／上一張／下一張），方便非線性簡報手動導覽。

   ```json
   [
     {
       "id": "flowchart",
       "title": "投資十步流程",
       "image": "flowchart.png",
       "hotspots": [
         {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.08, "target": "step3-detail", "label": "第三步細節"}
       ],
       "nav": true
     },
     {"id": "step3-detail", "title": "第三步細節", "image": "step3.png", "nav": true}
   ]
   ```

只有節點數不多、需要「點進細節頁」這種淺層非線性瀏覽時才用 hotspots；節點很多或需要 hover/依狀態變化的深度互動，不要硬塞進 pptx，改走下面的 open-slide 路徑。

## open-slide（互動投影片，React/Node）

需要互動（hover、點擊展開、逐步進場動畫）或目標本來就是簡報而非文件內嵌圖時，走這條路徑，不套用上面三節的靜態匯出規則。完整流程、互動模式清單、匯出時互動保留範圍，見 `references/output-openslide.md`。

## mkslides（互動投影片，Reveal.js/Python）

跟 open-slide 同屬「簡報」情境，差別是不需要 Node/pnpm/Vite，只要 Python；圖表嵌入規則跟本檔案「MkDocs Material（互動）」那節幾乎共用，額外拿到 Reveal.js 內建的 fragment 逐步揭露、講者備忘稿、PDF 匯出。完整流程、內聯 `<script>` 的已知限制與驗證步驟，見 `references/output-mkslides.md`。

## 選擇建議（速查）

| 目標 | 優先格式 | 理由 |
|---|---|---|
| Docsify | 靜態：獨立 SVG／互動：內聯 `<svg>` | 離線/內網友善；互動需內聯，且同頁多圖表要共用同一段 `<script>`（單頁單 script 限制） |
| MkDocs Material | 靜態：獨立 SVG／互動：內聯 `<svg>` | 設計可控度最高；建置期渲染，互動內聯沒有單頁單 script 限制，已用 PlantUML 的專案先依 `plantuml-support.md` 遷移 |
| PowerPoint | PNG（2x） | PPTX 只能吃點陣圖，2x 確保投影不糊；互動上限是熱區跳轉／導覽按鈕，做不到 hover 或動畫觸發 |
| open-slide | React 元件（原生 HTML+SVG 直接嵌入） | 互動天花板最高，present mode 內建；需要 Node 環境，export to PDF 會攤平失去互動 |
| mkslides | Markdown + 內聯 SVG（Reveal.js） | 環境成本最低（純 Python）；內聯 `<script>` 是否自動執行需先實測，fragment 語法免寫 JS 就能做逐步揭露 |
