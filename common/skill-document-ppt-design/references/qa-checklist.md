# QA Checklist

交付前逐頁執行。發現問題先修正，再輸出 PPTX。

---

## 風格符合度

- [ ] 套用的是使用者指定的 house style，而不是混用多種風格
- [ ] 主背景色符合 `style-system.md` 的指定值（誤差 ≤ ±5 hex）
- [ ] Accent 色使用比例低於頁面面積 10%
- [ ] 幾何風格一致（Futuristic Tech：無陰影；Washi Paper：無銳利幾何線；Soft 3D Clay：有圓角…）
- [ ] 字型符合指定 font stack

---

## 版面與構圖

- [ ] 使用 16:9 構圖
- [ ] 所有文字在 safe margin 範圍內（距邊緣 ≥ 72 px）
- [ ] 版面有明顯的視覺重心與非對稱性
- [ ] 留白有意圖，不是填不滿
- [ ] 細線 / 模組不雜亂（不超過 7 個視覺元素）

---

## 字型排版

- [ ] 標題層級明顯（cover title > slide title > body > caption）
- [ ] 正文文字在投影尺寸下可讀（body ≥ 18 px）
- [ ] 文字不超出其容器或 safe margin
- [ ] 無裝飾性字型
- [ ] 無負字距（negative letter-spacing）

---

## 內容品質

- [ ] 每頁只有一個清楚訊息
- [ ] 標籤簡潔（不超過 5 字）
- [ ] 資料視覺有直接標籤，不依賴圖例
- [ ] 無佔位用假文字（Lorem ipsum、TBD、XXXX…）
- [ ] 引用來源已標記（若有外部數據）

---

## SVG 技術規格

- [ ] `viewBox="0 0 1280 720"`
- [ ] 所有可讀文字使用 `<text>` 元素（非圖片化）
- [ ] 無 `filter`、`feGaussianBlur`、`feDropShadow`
- [ ] 無外部圖片 `href`（http/https 連結）
- [ ] 無 `foreignObject`
- [ ] fill 與 stroke 均為明確色碼，無 `currentColor` / `inherit` 例外
- [ ] 檔案可在 Chromium headless 正確渲染（Playwright 截圖驗證）

---

## PPTX 產出（如適用）

- [ ] Playwright + Chromium 環境可用
- [ ] python-pptx ≥ 1.0 已安裝
- [ ] 所有頁面 PNG 已生成且無空白頁
- [ ] `.pptx` 可在 PowerPoint / Keynote 正常開啟
- [ ] 文字框可在 PowerPoint 中選取與編輯（若使用 `<text>` 元素）

---

## 常見問題速查

| 問題 | 可能原因 | 修法 |
| :--- | :--- | :--- |
| Accent 色過多 | accent 用於裝飾而非信號 | 保留 1–2 個 accent 元素，其餘改石墨色 |
| 字型不符 | 未套用 font stack fallback | 加上指定字型的完整 fallback 串列 |
| PPTX 轉換後模糊 | SVG 含 filter | 移除所有 filter effects |
| 頁面訊息超過一個 | 內容未拆分 | 將頁面一分為二或移至附錄 |
| 文字超出安全邊距 | 長文字未換行 | 縮短文字或縮小字級 |
