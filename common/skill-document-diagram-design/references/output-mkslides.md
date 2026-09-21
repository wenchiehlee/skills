# 輸出規格：mkslides（Reveal.js 投影片）

[mkslides](https://github.com/MartenBE/mkslides)（`pip install mkslides`）是獨立的靜態簡報產生器，命令列與設定檔風格刻意模仿 MkDocs（`mkslides build`／`mkslides serve`、`mkslides.yml`），但底層引擎是 [Reveal.js](https://revealjs.com/)，跟 MkDocs Material **不是同一套輸出**——實務上是同一批 Markdown 來源，`mkdocs build` 產生文件站、`mkslides build` 另外產生投影片站，兩者並存。

## 何時選這條路徑

- 使用者要簡報，但不想／不能裝 Node/pnpm/Vite（open-slide 需要）→ mkslides 只需要 Python，環境成本比 open-slide 低。
- 使用者已經在用 MkDocs 寫文件，圖表的內聯 SVG 互動規則想直接沿用，不想為簡報另外設計一套嵌入邏輯 → mkslides 的 Markdown 語法與 `references/output-spec.md` 的「MkDocs Material（互動）」那節共用同一套規則。
- 需要 Reveal.js 內建的簡報功能（逐步揭露、講者備忘稿、PDF 匯出、多主題）但不需要 open-slide 那種可程式化的元件狀態 → mkslides 用 Markdown 語法就能拿到這些，不用寫 React。

找不到現成 mkslides 專案時：

```bash
pip install mkslides
mkslides build slides/      # 或 mkslides serve slides/ 做即時預覽
```

## 圖表如何嵌入

跟 MkDocs Material 一樣：**純靜態**用獨立 `.svg` + Markdown 圖片語法；**需要互動**把 `<svg>...</svg>` 原封不動內聯進 Markdown。座標系統、`style-guide.md` 的 6 個 token、克制原則都不變。

Reveal.js 的畫布尺寸由 `revealjs.height`/`revealjs.width` 設定（預設 1050×700，建議改成 1080×1920 對齊 open-slide 慣例，方便同一份圖表兩邊共用），圖表的 `viewBox` 依這個比例對齊，不要假設瀏覽器視窗尺寸。

```yaml
# mkslides.yml
revealjs:
  height: 1080
  width: 1920
```

## ⚠️ 內聯 `<script>` 的執行時機——先驗證再依賴

mkslides／Reveal.js 的 Markdown 轉換走 `data-markdown` 機制：整份 Markdown 先被丟進一個 `<section data-markdown>`，由 Reveal 的 markdown 外掛（底層是 marked.js）在瀏覽器端轉成 `<section>` 投影片 DOM。這跟 MkDocs Material「建置期 python-markdown 轉換、`<script>` 直接原封不動輸出進最終頁面」的模式不同——**用字串插入 DOM（等同 innerHTML）產生的 `<script>` 標籤，瀏覽器預設不會自動執行**，這跟 Docsify 遇到的限制是同一類問題，只是機制不同（Docsify 是 AJAX 換頁時的 innerHTML，這裡是 marked.js 轉換後的 innerHTML）。

實務作法：

1. 純 CSS `:hover`／`:focus` 互動不受影響，照樣可用，優先選這條路。
2. 需要 JS 邏輯時，**先用一個最小範例（一個 hover 節點 + 一段 `console.log`）跑一次 `mkslides serve` 實測 script 會不會執行**，不要直接假設它會動——如果不動，改用 Reveal.js 的外掛機制（`plugins` 設定裡的 `extra_javascript`，寫成獨立 `.js` 檔案由 Reveal 在頁面載入時正常掛載，而不是內嵌在 Markdown 裡的 `<script>`）。
3. 需要跨投影片共用的互動邏輯，一律寫成獨立 `.js` 檔透過 `plugins.extra_javascript` 掛載，不要依賴 Markdown 內聯 script——這樣可以繞開上述不確定性，也比較好維護。

## 建議的互動模式

| 模式 | 做法 |
|---|---|
| 逐步進場（build steps） | 用 Reveal.js 原生的 `<!-- .element: class="fragment" -->` 語法標記節點，不用自己寫 JS，這是 mkslides 相對 open-slide 的最大優勢——同樣效果在 open-slide 要自己刻 state |
| Hover tooltip | 沿用 `<title>`/`<desc>` 內容，純 CSS 實作（見上方限制說明） |
| 點擊展開/收合子樹 | 若內聯 `<script>` 實測可行就直接寫；不行的話走 `plugins.extra_javascript` 掛獨立腳本 |
| 講者備忘稿 | Reveal.js 原生支援，`separator_notes` 設定的區塊自動變成 speaker notes，不需要額外處理 |

## 匯出與互動保留範圍

| 匯出方式 | 互動是否保留 |
|---|---|
| `mkslides serve` 本地預覽 | 完整保留 |
| `mkslides build` 靜態站 | 完整保留（純前端 JS，可部署到任何靜態主機，跟 MkDocs Material 用同一台伺服器也可以） |
| Reveal.js 內建的 PDF 匯出（`?print-pdf`） | 攤平成靜態頁，fragment 逐步揭露會失效，用途同 open-slide 的 PDF 匯出 |

## 與其他輸出路徑的關係

- 跟 open-slide 是互斥的簡報路徑選擇：需要 React 元件狀態、agent 逐步協作寫簡報、Node 環境沒問題 → open-slide；只要 Markdown+Reveal.js 的功能就夠、想省掉 Node 工具鏈 → mkslides。不要同時做兩份簡報，先問使用者環境限制與互動複雜度需求。
- 不要跟 PowerPoint 流程混用；PowerPoint 走純靜態走向企業既有簡報習慣，mkslides／open-slide 走網頁互動走向。
