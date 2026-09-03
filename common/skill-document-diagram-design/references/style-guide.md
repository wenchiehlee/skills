# 樣式指南（Style Guide）

此檔案是所有圖表的顏色／字型單一來源。產生任何圖表前，先確認是否有專案自訂的 `style-guide.md`（放在呼叫端專案，例如 `docs/diagram-style.md`）；沒有的話用本檔案的預設值。

## 設計原則（取自 diagram-design 方法論）

- **克制優先**：每個節點都要有存在的理由；accent color 只保留給讀者第一眼該注意的 1–2 個元素。
- **單一 accent color**：其餘元素一律用中性色（ink / muted / paper），不要多色系統。
- **1px hairline 邊框、不用陰影**，最大圓角 10px。
- **座標一律取 4 的倍數**，避免視覺上出現「AI 生成感」的隨意留白。
- **視覺密度目標 4/10**：資訊量夠用即可，不要為了「看起來豐富」硬塞裝飾。
- 判斷是否該畫圖：先問「讀者從這張圖學到的東西，會比一段寫清楚的文字多嗎？」不成立就不畫。

## 預設色彩 Token（可被覆寫）

| Token | 用途 | 預設值（light） | 預設值（dark） |
|---|---|---|---|
| `paper` | 背景 | `#FAFAF8` | `#111113` |
| `ink` | 主要文字/線條 | `#1A1A1A` | `#EDEDED` |
| `muted` | 次要文字/淡化元素 | `#8A8A85` | `#8A8A90` |
| `accent` | 焦點強調（僅 1–2 處） | `#5B4CFF` | `#8B7CFF` |
| `link` | 可點擊/關聯線 | `#2F6FED` | `#6FA1FF` |
| `border` | hairline 邊框 | `rgba(0,0,0,0.12)` | `rgba(255,255,255,0.16)` |

品牌置換：若專案有自己的網站/簡報色票，把上表 6 個 token 換成對應色碼即可，不需要逐張圖表改參數。

## 字型

- 標題／callout：Instrument Serif（或該專案既有的襯線標題字）
- 標籤／內文：Geist Sans（或系統 UI sans-serif，確保離線/簡報環境可用）
- 技術內容／代號：Geist Mono（或系統等寬字）

嵌入 Docsify／MkDocs 時預設走 Google Fonts CDN；若目標環境無法連外（純內網文件、離線 PPT），改用系統字型 fallback：`-apple-system, "Segoe UI", "Noto Sans TC", sans-serif`。

## 不要做的事

- 不要用漸層、陰影、圓角 > 10px、超過一種 accent color。
- 不要把每個節點都塗滿顏色——顏色是用來引導視線，不是裝飾。
- 不要為了填滿畫布而加無意義的裝飾線條/圖示。
