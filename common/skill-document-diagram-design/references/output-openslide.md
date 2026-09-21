# 輸出規格：open-slide（互動投影片）

[open-slide](https://github.com/1weiho/open-slide)（https://open-slide.dev）是給 coding agent 用的簡報框架：每張投影片是固定 1920×1080 canvas 上的一個 React 元件（`slides/<id>/index.tsx`），不是像 PlantUML/Mermaid 那樣被渲染成圖片再嵌入。這條路徑存在的理由，是它能承載 Docsify/MkDocs 都做不到的**完整互動**（hover、點擊、逐步進場動畫、present mode），同時避開 PowerPoint pptx 只能吃點陣圖的限制（見 `output-spec.md`）。

## 何時選這條路徑

- 使用者的目標是「簡報／投影片」而不是「嵌進文件的一張圖」→ 用 open-slide，不要硬套 Docsify/MkDocs 的靜態 SVG 流程。
- 使用者明確要互動（逐步揭露節點、hover 顯示細節、點擊展開子樹）→ open-slide、mkslides（見 `references/output-mkslides.md`）、或「Docsify/MkDocs 內嵌原始 HTML」都能做，PowerPoint 做不到。open-slide 跟 mkslides 是互斥的簡報路徑：能裝 Node 且要 React 元件狀態選 open-slide，只要 Python 且 Reveal.js 內建功能夠用選 mkslides。
- 使用者要離線可播放、但又要互動 → open-slide `export to static HTML`（不是 PDF）符合這個需求。

找不到現成 open-slide 專案時，先跑：

```bash
npx @open-slide/cli init my-slide
cd my-slide
pnpm dev
```

## 圖表如何嵌入

本技能原生管線產出的是自含 `.html`（`<svg>` + `<style>` 用 `var(--token)`）。放進 open-slide 時**不要**再走「抽出 SVG、換成字面色碼」那條 Docsify/MkDocs 專用流程——open-slide 的頁面本來就是真正的 React/CSS 環境，直接把 `style-guide.md` 的 6 個 token 定義成 CSS 變數或 Tailwind 主題色即可，跟站台共用同一份色票，不用複製字面色碼。

做法：

1. 把手刻的 `<svg>...</svg>` 內容原封不動包成一個 React 元件（例如 `slides/<id>/diagrams/FlowchartDiagram.tsx`），節點座標系統維持 4 的倍數的原則不變。
2. `viewBox` 依畫面比例對齊 1920×1080 canvas，避免直接假設瀏覽器視窗尺寸。
3. 需要互動的節點，把原本純裝飾的 SVG 元素換成有 `onClick`/`onMouseEnter` 的 React 節點，狀態用 `useState` 管理（例如「目前展開的分支」「hover 中的節點 id」）。
4. accent color 的克制原則不變：互動高亮（hover/selected）可以暫時借用 `accent` token，但恢復預設狀態後仍只保留 1–2 處常駐強調色，不要讓互動變成「到處都會變色」。

## 建議的互動模式（依克制原則篩選過）

| 模式 | 適用圖表類型 | 做法 |
|---|---|---|
| Hover tooltip | 任何節點數多、細節寫不進去的圖（org chart、mindmap） | 用既有的 `<title>`/`<desc>` 內容當 tooltip 文字，hover 時用 CSS transition 淡入，不用額外套件 |
| 點擊展開/收合子樹 | mindmap、tree、org chart | 預設收合到 2 層深，點擊節點展開下一層，避免一次塞爆整張投影片（呼應 `diagram-types.md` 的節點數上限原則） |
| 逐步進場（build steps） | flowchart、sequence diagram | 用 open-slide 的動畫/present mode 機制，一步一步揭露流程節點，取代「一次全部畫出來再口頭講解」 |
| 篩選高亮 | comparison table、quadrant | 點擊圖例某一類別，只高亮該類別對應節點，其餘降至 `muted` |

超出這四種以外的複雜互動（拖曳排序、即時資料綁定）先跟使用者確認是否真的需要，避免簡報變成小型應用程式。

## 匯出與互動保留範圍

| 匯出方式 | 互動是否保留 | 用途 |
|---|---|---|
| `pnpm dev` / present mode 現場播放 | 完整保留 | 主要使用情境 |
| export to static HTML | 完整保留（純前端 JS，可離線／部署到任何靜態主機） | 分享給不方便裝環境的人，或部署上網 |
| export to PDF | **不保留**，攤平成靜態頁 | 只在對方明確要「紙本/列印」或不支援 HTML 時才用，且要跟使用者說清楚互動會消失 |

## 與其他輸出路徑的關係

- 不要把 open-slide 當成 Docsify/MkDocs 的替代品——文件內嵌圖表仍走 `output-spec.md` 的靜態 SVG 流程，open-slide 只用於「簡報」情境。
- 不要把 PowerPoint 流程（`svg_to_png.py`/`svg_to_pptx.py`）跟 open-slide 混用；兩者是互斥的目標平台選擇（有互動需求走 open-slide，需要交給不會裝 Node 環境的人走 PowerPoint 靜態版）。
