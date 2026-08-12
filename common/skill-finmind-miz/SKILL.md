---
name: skill-finmind-miz
description: 從自架 Calibre-Web 電子書伺服器（books.miz.com.tw）取得書籍原始 epub 或閱讀器全文，並依 Miz.Fetch 專案規範匯出為 Markdown（books/[書名]/metadata.md + 00.md, 01.md, ...），保留標題/粗體/清單排版並抽出內嵌圖片。
---

# FinMind Miz Book Fetch Skill（Miz 電子書擷取技能）

此技能用於將 **books.miz.com.tw**（使用者自架、開放存取的 Calibre-Web 個人電子書伺服器）上的書籍，轉換為 Markdown 並存入 [Miz.Fetch](https://github.com/wenchiehlee-money/Miz.Fetch) 專案的 `books/` 資料夾。

## 授權前提（務必先確認）

- 僅可用於**使用者自己架設/擁有的** Calibre-Web 個人書庫（自架、非商業訂閱平台）。若使用者提供的網址是第三方商業電子書平台，**不要**用本技能繞過其閱讀器限制擷取全文，改為請使用者提供官方下載檔或手動貼上內容。
- 若不確定網站性質，先確認頁面是否為 Calibre-Web（頁面常見文字如 "Calibre-Web"、書架分類清單等），並向使用者確認這是否為其自架伺服器。

## 兩種擷取方法

| | 方法 A：登入下載原始 epub（**建議、預設**） | 方法 B：瀏覽器自動化擷取閱讀器全文（備援） |
|---|---|---|
| 需求 | 有效的登入 session cookie | `chrome-devtools` MCP 工具，不需登入 |
| 輸出品質 | 完整保留標題/粗體/斜體/清單排版，並抽出所有內嵌圖片 | 純文字，無排版、無圖片 |
| 速度 | 快（單次下載整本 epub） | 慢（逐章節等待瀏覽器渲染） |
| 適用時機 | session cookie 有效時的預設選擇 | cookie 過期、沒有登入權限、或只是要快速取得文字內容做 AI 摘要 |

## 方法 A：登入下載原始 epub（`scripts/fetch_epub_to_md.py`）

### 1. 取得 session cookie

- 用瀏覽器登入 `https://books.miz.com.tw/login`。
- 開 DevTools → Application/Storage → Cookies，複製 `session` cookie 的值。
- 設定環境變數（或用 `--session-cookie` 參數）：
  ```bash
  export MIZ_SESSION_COOKIE="<複製的 session cookie 值>"
  ```
  Miz.Fetch 專案的 `scripts/fetch_epub.py` 內已有一份先前取得、目前仍有效的 session cookie 可直接複用（無需重新登入），除非該 cookie 已過期。

### 2. 找出 book id

書籍網址格式為 `https://books.miz.com.tw/read/{id}/epub`（可能帶 `#epubcfi(...)` 錨點，可忽略），`{id}` 即為 book id。

### 3. 執行下載與轉換

```bash
python scripts/fetch_epub_to_md.py \
  --id 201 \
  --out-dir "books/{確切書名}" \
  --fetch-date "2026-08-12"
```

腳本會：

1. 用 session cookie 向 `https://books.miz.com.tw/show/{id}/epub/file.epub` 下載完整原始 epub（zip）。
2. 解析 `META-INF/container.xml` → OPF，取得 `dc:title` / `dc:creator` / `dc:publisher`，並依 spine（`<itemref idref="...">`）順序取得章節清單。
3. 抽出所有內嵌圖片到 `images/` 子資料夾。
4. 把每個章節的 XHTML 轉成 Markdown（`00.md`, `01.md`, ... 依 spine 順序，`img` 標籤轉為 `![alt](images/檔名)`）。
5. 自動產生 `metadata.md`（書名、作者、出版社、來源網址、擷取日期）。

若下載回傳非 200（或內容不是有效 zip），代表 session cookie 已過期，需回到步驟 1 重新登入取得新值。

## 方法 B：chrome-devtools 擷取閱讀器全文（備援，不需登入）

books.miz.com.tw 是純前端 JavaScript 渲染的 epub.js 閱讀器，一般 HTTP 擷取（WebFetch/curl）只能取得閱讀器介面殼層，無法取得書籍正文；下載端點在未登入時會回傳 403。此方法改用瀏覽器自動化，直接呼叫頁面內已載入的 `epub.js` Book 物件（`book.spine` + `book.load()`）逐一取出各章節的純文字內容。

### 1. 導覽到閱讀器頁面

```
navigate_page(url="https://books.miz.com.tw/read/{id}/epub")
```

### 2. 用 evaluate_script 擷取全書章節文字

閱讀器頁面的全域變數 `window.reader.book` 即為 epub.js 的 Book 實例：

```javascript
async () => {
  const book = window.reader.book;
  const toc = book.navigation.toc;
  const items = book.spine.items;
  const results = [];
  for (const item of items) {
    try {
      const doc = await book.load(item.href);
      const text = doc.body ? doc.body.innerText : '';
      results.push({href: item.href, index: item.index, text});
    } catch (e) {
      results.push({href: item.href, index: item.index, text: '', error: String(e)});
    }
  }
  return {toc, results};
}
```

用 `evaluate_script` 執行，並帶上 `filePath` 參數把結果存成 JSON 檔（章節數多時 inline 回傳會過大）：

```
evaluate_script(function=<上面的腳本>, filePath="<scratchpad>/book_{id}.json")
```

### 3. 用後處理腳本產生 Markdown

```bash
python scripts/build_book_markdown.py \
  --json "<scratchpad>/book_{id}.json" \
  --out-dir "books/{確切書名}" \
  --title "{確切書名}" \
  --author "{作者}" \
  --source-url "https://books.miz.com.tw/read/{id}/epub" \
  --publisher "{出版社，可選}" \
  --fetch-date "2026-08-12"
```

此腳本會將 `toc`（含巢狀 `subitems`）攤平為 `href → 章節標題` 對照表，依 spine 順序跳過過短（預設 <50 字，通常是封面圖片頁）的章節，依序輸出為 `01.md`, `02.md`, ...，並產生 `metadata.md`。

## 共通收尾步驟

檢查產生的檔案數量與內容是否合理（沒有大量空章節、標題正確、圖片連結存在），再依使用者指示 `git add` / `commit` / `push`（Miz.Fetch repo 為 private，推送前仍建議先跟使用者確認一次）。

## 參數說明

### `scripts/fetch_epub_to_md.py`（方法 A）

- `--id`：book id（必要）。
- `--out-dir`：輸出資料夾，通常是 `books/{書名}`（必要，會自動建立）。
- `--session-cookie`：登入 session cookie；預設讀取 `MIZ_SESSION_COOKIE` 環境變數。
- `--fetch-date`：擷取日期 YYYY-MM-DD，寫入 metadata.md（可選）。
- `--intro`：metadata.md 的簡介文字（可選）。

### `scripts/build_book_markdown.py`（方法 B 後處理）

- `--json`：方法 B 步驟 2 產出的 JSON 檔路徑（必要）。
- `--out-dir` / `--title` / `--author` / `--source-url`：同上（必要）。
- `--publisher` / `--fetch-date` / `--intro`：可選。
- `--min-len`：過濾章節的最小字數門檻，預設 `50`。

## 已知限制

- 方法 A 依賴有效的登入 session cookie，過期需重新登入取得。
- 方法 B 依賴頁面內 epub.js 的全域變數命名（`window.reader.book`），若閱讀器版本更新導致變數改名，需重新用 `evaluate_script` 探索（`() => Object.keys(window).filter(k => /book|epub|reader/i.test(k))`），且只能取得純文字，無排版與圖片。
- 兩種方法的章節檔名編號基準不同：方法 A 從 `00.md` 開始（與 spine index 對齊，符合 Miz.Fetch 現有書籍慣例），方法 B 從 `01.md` 開始（過濾掉極短章節後重新編號）。混用時同一本書建議只用其中一種方法，避免編號基準不一致。
