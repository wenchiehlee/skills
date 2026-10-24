# PPT Master Integration

搭配 [`ppt-master`](https://github.com/hugohe3/ppt-master) 使用時，本技能作為視覺風格層。

---

## Deck Defaults

| 項目 | 值 |
| :--- | :--- |
| Aspect ratio | 16:9 |
| Canvas size | `1280 × 720` |
| SVG viewBox | `0 0 1280 720` |
| Default background | 依風格（見 `style-system.md`） |
| Default primary text | 依風格 |
| Default accent | 依風格 |

---

## SVG Spec Lock

每頁 SVG 必須遵守以下約束，確保 PPTX 轉換品質：

**必須做到**：
- `viewBox="0 0 1280 720"`
- 使用嵌入文字（`<text>` 元素），不使用點陣化文字
- 所有文字保持在 safe margin 範圍內（72 px from edge）
- 使用明確的 `fill` 與 `stroke`
- 使用基本 SVG primitives：`rect`、`line`、`path`、`circle`、`text`、`polyline`、`g`

**禁止**：
- `filter`、`feGaussianBlur`、`feDropShadow` 等 filter effects
- 外部圖片連結（`href` 指向 http/https）
- `foreignObject`
- CSS `box-shadow` 或 `text-shadow`
- 漸層（gradient）僅允許在 Soft 3D Clay / Modern Illustration 插畫物件內部，且需平面退化版本

---

## 產製流程（Eight Confirmations + 七步驟）

### 確認清單（Eight Confirmations）

在進入設計前，與使用者確認：

1. **風格**：選定哪一個 house style？
2. **頁數**：幾頁？（建議 3–10 頁）
3. **受眾**：誰看？（技術決策者、一般管理層、投資人、品牌客戶…）
4. **語言**：繁體中文 / 英文 / 雙語？
5. **輸出格式**：只要 SVG？還是需要 PPTX？
6. **來源材料**：文件、PDF、CSV、自由描述？
7. **品牌資產**：是否有 logo、品牌色票、指定字型？
8. **交付期望**：草稿確認後才輸出，還是直接輸出？

### 七步驟

```text
步驟 1：讀取並摘要來源材料
步驟 2：規劃頁面結構（每頁一個主訊息）
步驟 3：產出 design_spec.md（風格 token + 頁面清單 + 每頁頁型）
步驟 4：產出 spec_lock.md（鎖定設計決策，後續不再更動）
步驟 5：逐頁產出 SVG（遵守 SVG Spec Lock）
步驟 6：視覺 QA（逐頁過 qa-checklist.md）
步驟 7：PPTX export（scripts/svg_to_pptx.py）
```

---

## design_spec.md 標準格式

```markdown
# Design Spec

## 風格
<house style name>

## 色票
- Background: #XXXXXX
- Primary text: #XXXXXX
- Accent: #XXXXXX
- Secondary text: #XXXXXX
- Grid/divider: #XXXXXX

## 字型
- Heading: <font>, <size> px, weight <w>
- Body: <font>, <size> px, weight <w>

## 頁面清單
| 頁碼 | 頁型 | 主訊息 |
| :--- | :--- | :--- |
| 01 | Cover | <主標題> |
| 02 | Asymmetric Thesis | <論點> |
| ... | ... | ... |
```

---

## 文字密度規範

| 頁型 | 最大文字量 |
| :--- | :--- |
| Cover | 標題 + 1 行副標題 |
| 一般內容頁 | 1 個主訊息 + 3–5 個支撐模組 |
| Body copy block | 8–16 字/區塊 |
| 禁止 | 整段段落（除非引用來源） |

---

## PPTX 匯出說明

```bash
# 安裝依賴
pip install playwright python-pptx pillow
playwright install chromium

# 執行（slides/ 目錄下為逐頁 SVG，命名為 01.svg, 02.svg …）
python scripts/svg_to_pptx.py --slides slides/ --output deck.pptx
```

SVG → PNG 使用 Playwright + Chromium headless；PNG → PPTX 使用 python-pptx。產出的 `.pptx` 文字框為可編輯狀態（若原 SVG 使用 `<text>` 元素）。
