# 圖表類型庫（初始子集）

本技能先移植 [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) 中最常用於文件/簡報的類型，其餘 39 種類型中的其他類型**依需求再擴充**——遇到下表沒有的類型時，回頭讀取原始 repo 對應的 `references/type-*.md` 規格，比照本檔案的格式補一段，不要憑空發明畫法。

## 只有一條輸出管線：原生 HTML+SVG

所有**新產出**的圖表一律走原生管線——完全照 `style-guide.md` 的色彩/字型/密度規則手刻 SVG。本技能存在的目的之一就是取代 PlantUML／Mermaid 這類「文字 DSL 交給外部引擎畫圖、可控度低、長得像預設樣板」的做法，所以不提供 PlantUML 作為輸出選項。

PlantUML（`.puml`/`.planuml`）只在一種情境下出現：**使用者已經有舊的 PlantUML 圖表，要匯入並改畫成原生風格**。這是「匯入來源格式」，不是「輸出格式」，細節與遷移流程見 `plantuml-support.md`。Mermaid 區塊比照辦理——只匯入，不輸出。

## 初始類型子集

全部走原生 HTML+SVG 管線；「常見對應的舊 PlantUML 語法」一欄只是幫助辨識匯入來源，不代表輸出會用該語法。

| 類型 | 用途 | 備註 | 常見對應的舊 PlantUML 語法（僅匯入辨識用） |
|---|---|---|---|
| flowchart | 流程/決策邏輯 | 節點數控制在 12 個以內，超過就拆兩張圖 | `@startuml` activity |
| swimlane | 跨角色/跨階段流程 | 泳道數建議 ≤ 4 | `@startuml` + `|swimlane|` |
| quadrant | 二維定位比較（例如風險 vs. 報酬） | 只標出真正需要比較的項目，不要塞滿象限 | — |
| comparison-table | 多方法論/多選項屬性比較 | 表格式圖，欄數建議 ≤ 5 | — |
| timeline | 時間序列事件 | 事件數建議 ≤ 8 | `@startgantt` |
| tree / nested-hierarchy | 因果鏈、分類階層 | 深度建議 ≤ 4 層 | — |
| radar | 多維度輪廓比較 | 維度數建議 4–8 個 | — |
| sankey | 流量/組成分解 | 節點數建議 ≤ 10 | — |
| mindmap | 主題輻射式分類（例如產品/技術堆疊全貌） | 深度建議 ≤ 4 層、每層分支 ≤ 6 個；`InvestmentStackVision.planuml` 就是這個類型的匯入案例，見 `plantuml-support.md` | `@startmindmap` |
| sequence | 互動/呼叫順序 | 參與者建議 ≤ 6，超過先問能否拆場景 | `@startuml` sequence |
| state | 狀態機 | 狀態數建議 ≤ 8 | `@startuml` state |
| class / ER | 資料模型 | 實體數建議 ≤ 10 | `@startuml` class/entity |
| org-chart | 組織/層級關係 | 節點數建議 ≤ 15 | — |

## 擴充流程

1. 確認需求對應的類型不在上表。
2. 讀 diagram-design 原始 repo 的 `skills/diagram-design/references/type-<name>.md`（或等效規格頁）與對應範例 HTML，取其**視覺規格**（節點造型、間距、標籤排版），一律轉譯成原生 HTML+SVG 產出，不要把 PlantUML/Mermaid 語法本身當成輸出格式抄過來。
3. 在上表補一列，並視需要另建一節記錄該類型專屬的排版規則（node 最大數、必要欄位、常見誤用）。

## 通用檢查（畫完任一類型後都要過）

- 是否只有 1–2 個 accent 元素？
- 座標/間距是否為 4 的倍數（原生管線）？
- 節點數是否超出上表建議上限？超出就先問「能不能拆成兩張圖」而不是把字級縮小塞進去。
- 是否可以用一句話講清楚，若可以就不畫圖。
