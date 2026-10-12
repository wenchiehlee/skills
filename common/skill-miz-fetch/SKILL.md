---
name: skill-miz-fetch
description: 從使用者有權存取的 EPUB 或 PDF 來源取得書籍內容，依 Miz.Fetch 慣例輸出分章 Markdown、metadata、圖片資產與按需求產生的書籍摘要/投資策略框架；涵蓋 Calibre-Web EPUB、文字型 PDF 與掃描 PDF OCR。
---

# Miz Fetch Skill（Miz 電子書擷取技能）

此技能用於把使用者有權存取的書籍來源整理成 Miz.Fetch 的書籍資料夾，輸出至 `books/[書名]/`。來源可能是自架 Calibre-Web EPUB、可下載的 EPUB，或使用者提供/已取得的 PDF。先判斷實際檔案格式，再選擇對應流程；不可因書籍在 Calibre-Web 有閱讀頁，就假設本機 PDF 已有文字層、圖片資產或 EPUB 章節結構。

## 授權前提（務必先確認）

- 僅可用於**使用者自己架設/擁有的** Calibre-Web 個人書庫（自架、非商業訂閱平台）。若使用者提供的網址是第三方商業電子書平台，**不要**用本技能繞過其閱讀器限制擷取全文，改為請使用者提供官方下載檔或手動貼上內容。
- 若不確定網站性質，先確認頁面是否為 Calibre-Web（頁面常見文字如 "Calibre-Web"、書架分類清單等），並向使用者確認這是否為其自架伺服器。

## 擷取方法

| | 方法 A：取得 EPUB 原檔（**EPUB 預設**） | 方法 B：瀏覽器自動化擷取閱讀器全文（EPUB 備援） | 方法 C：PDF 文字擷取或 OCR |
|---|---|---|
| 需求 | EPUB 檔與有效的下載權限 | `chrome-devtools` MCP 工具與可讀 EPUB 閱讀器 | PDF 檔；掃描 PDF 另需 `skill-mlx-api-client-ocr` |
| 輸出品質 | 依 spine 分章，保留 XHTML 標題/粗體/清單並抽出內嵌圖片 | 可取章節標題與文字；通常無排版、無圖片 | 文字型 PDF 可保留文字；掃描 PDF 需要 OCR，插圖需從原 PDF 另行輸出 |
| 適用時機 | 來源是 EPUB 時優先使用 | EPUB 下載受限但閱讀器可讀時 | 來源本身是 PDF，或沒有可用 EPUB 時 |

## 完整書籍資料夾的交付內容

使用者說「處理/整理一本書」時，預設完成原文攝取並依書籍性質準備下列檔案；若使用者只要求轉檔，則只做原文與 metadata，不擅自加入分析文件。

| 輸出 | 規則 |
|---|---|
| `metadata.md` | 書名、作者、出版社（可得時）、原始來源、日期、格式、PDF 頁數/OCR 狀態（如適用）與章節檔案清單。 |
| `00.md`, `01.md`, ... | 依 EPUB spine 或 PDF 目錄分章；前言/目錄可放 `00.md`，章節依序編號，附錄/註釋/致謝另分檔。每檔以 `# 章節標題` 開頭。不要把整本書塞在單一檔案，也不要任意按固定頁數切章。 |
| `images/*.jpg` | 保留封面與有實質內容的插圖/圖表，Markdown 內須有相對連結。不要建立空的 `images/`，也不要把 OCR 文字誤當圖片。來源為掃描 PDF 時依「PDF 圖片處理」選擇性轉出頁面 JPG。 |
| `書籍摘要.md` | 完整攝取且使用者要求「處理/整理」時，另產生可追溯到章節的書籍摘要；只要求原文轉檔時不產生。 |
| `投資策略框架.md` | 書籍與投資、財富、風險或決策有實質關聯時，或使用者明確要求時，依 `skill-investment-decision-coach` 的「書本框架提煉規則」產生。純文學/非投資書不強行套用投資框架。 |

`書籍摘要.md` 與 `投資策略框架.md` 是衍生整理，不是擷取原文。先完成並檢查原文，再進行摘要/提煉；標示章節來源，區分作者主張與整理者應用。掃描/OCR 不完整或有明顯錯字時，先修正來源品質或在衍生文件標明限制，不可把不確定 OCR 當作可靠原文。

### 新增或重做前的保護與來源核對

- 先盤點目標資料夾、來源檔、現有章節、圖片與衍生文件；不可把「新 fetch」理解成刪除既有內容。優先在暫存資料夾產生，再比對後移入。
- 不得用 `rm`、`rmtree` 或覆寫整個資料夾清理舊輸出。需要覆寫時逐檔確認；保留原始 PDF/EPUB、圖片和已完成的章節。`scripts/assemble_pdf_ocr_markdown.py` 預設拒絕覆寫既有 `00.md`/`metadata.md`；只有使用者明確要求重做且已確認目標檔案時才用 `--overwrite`。
- 書名、作者、譯者、出版社、ISBN、語言與版本/地區版次，優先從 PDF/EPUB 的版權頁、封面及目錄核對。網頁檔名、Scribd 標題、資料夾名稱、既有 metadata 都只能當線索；來源互相衝突時記錄「待核對」，不可自行選一個填成確定值。特別檢查繁體/簡體地區版差異，確保 metadata 描述的是手上這份 PDF，而不是另一個常見版本。
- 章節語言與用字依來源保留。除非使用者要求，不要把簡體內容默默轉成繁體、改寫 OCR 原文或翻譯；需要修正 OCR 時，保留原意並抽查原頁，無法判斷的字詞以註記標示。
- 如果既有章節已是 PDF OCR 結果，先做品質盤點後重用可接受內容，不能為了稱作「新 fetch」而重跑全部 OCR。檢查重複段落、遺頁、頁碼、亂序、缺字和明顯識別錯誤；必要時針對問題頁重做 OCR。

### 下載前先確認版次

當書名有不同地區版、譯本或新版時，先建立目標版次條件（出版社、譯者、ISBN、語言/字體、版次；至少使用可取得的兩項識別資料），再挑來源。對 Scribd 等第三方文件平台，平台標題和頁數只是線索；先查看文件的版權頁/目錄預覽，確認 ISBN、出版社和譯者是否吻合。下載後再檢查本機 PDF 的封面和版權頁；兩者不符就停止轉檔，把檔案標成「版次不符」，不可把它當成目標書籍完成攝取。

若第三方平台要求登入、訂閱或其他權限，而本次環境沒有可用的正常下載權限，只能請使用者透過其帳戶的官方下載功能提供檔案；不可利用閱讀器預覽、隱藏 endpoint、cookie 重放或其他方式繞過存取限制。公開預覽可用於書目核對，不代表可擷取或重建完整書籍。

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

## 方法 C：處理 PDF（文字型或掃描版）

先檢查 PDF 頁數、文字層、目錄/版權頁，以及現有輸出。抽查前、中、後頁判斷文字層是否完整；文字型 PDF 優先抽取內嵌文字，掃描頁才 OCR。若混合，採 OCR skill 的 hybrid 流程，保留可靠文字層。掃描書籍的長篇 OCR 依 `skills/skill-mlx-api-client-ocr/SKILL.md` 的 resilient runner 分頁執行，使用明確的頁碼、引擎與 DPI，並保留可續跑 cache。例如：

```bash
python skills/skill-mlx-api-client-ocr/scripts/ocr_resilient_runner.py \
  "books/書名/來源.pdf" "1,2,3,4,5" --engine baidu --dpi 200 \
  --cache .ocr-cache
```

對全書傳入實際 PDF 頁碼（不可照抄示例頁碼）。將頁面文字組裝成工作稿後，再按實際目錄/章名切成 `00.md`, `01.md`, ...；不要將整本 OCR 結果只存成一個 `00.md`。在 metadata 記錄頁數、來源版次、文字層/OCR 方法、引擎、DPI、擷取日期與章節清單。OCR 只負責轉錄文字，不會自動建立 `images/`、摘要或投資策略框架。

`scripts/assemble_pdf_ocr_markdown.py` 只把逐頁 cache 組成單一工作稿，並非章節切分器；它會產生 `00.md` 與基礎 metadata。完成章節切分後，必須更新 metadata 的目錄清單。舊版組裝器曾刪除既有編號 Markdown 和整個 `images/` 資料夾；新版已移除該清理行為。處理前後都要核對檔案清單，任何工具都不得藉由重建 `00.md` 清掉其他輸出。

### PDF 圖片處理：JPG 與 Markdown 連結

先看 PDF 內的圖像形態：掃描版常見每頁一張全頁點陣圖，並沒有可直接抽出的獨立插圖；文字型 PDF 則可能含封面、圖表或其他嵌入影像。Mac-mini OCR 可接受 PDF/JPG/PNG 並回傳辨識文字，但不會把圖片存進書籍的 `images/`。因此「OCR 已完成」不代表圖片已輸出。此 repository 的 OCR 技能路徑是 `skills/skill-mlx-api-client-ocr/SKILL.md`（不是 `skills/mac-mini-ocr/SKILL.md`）。

使用 `PyMuPDF` 把封面、目錄或實際包含圖表/插圖的 PDF 頁面渲染成 JPG；腳本預設只輸出指定頁面，避免把數百張整頁掃描圖全部複製進 Git：

```bash
python skills/skill-miz-fetch/scripts/render_pdf_pages_to_jpg.py \
  --pdf "books/書名/來源.pdf" \
  --out-dir "books/書名/images" \
  --pages 1,18,42 \
  --dpi 180
```

頁碼使用 PDF 的 1-based 頁碼。輸出檔名為 `page_001.jpg` 等；在對應章節 Markdown 放上 `![PDF 第 18 頁圖表](images/page_018.jpg)`。只輸出封面時使用 `--pages 1` 並在 `00.md` 連結。完整掃描版 PDF 的每頁都是影像，不代表每一頁都應複製進 `images/`；預設只留封面及有助理解的圖表/插圖頁，避免整本書產生重複巨量 JPG。只有使用者明確要求完整逐頁影像時，才指定所有頁面。若 PDF 中有可直接抽取且非全頁掃描的 JPG/PNG 資產，優先保留原圖並依原章節引用；不要將 JPEG 再壓縮一次。若沒有可辨認的有用插圖，只輸出封面即可，不建立空的 `images/`。

若頁面圖表未被 OCR 轉成可讀內容，JPG 只作為原始視覺來源，不能宣稱 OCR 已辨識其中所有標籤/數值。標記需人工檢視的頁碼，並把原頁圖像放在對應章節附近。

### 從完整原文建立摘要與投資框架

- `書籍摘要.md`：以繁體中文整理全書主旨、核心概念、章節重點、作者論證/案例與限制；附章節檔名或章名作為定位。避免把書籍外的推論寫成作者主張。
- `投資策略框架.md`：讀取 `skills/skill-investment-decision-coach/SKILL.md`，依其規則寫核心命題、主要原則、日/週/月/季實踐、一頁式檢查表、行動準則、章節來源、成立假設及失效條件；區分「作者主張」和「投資應用延伸」。認知/決策類書籍可提煉投資決策應用，但要清楚標成延伸，不可把書中一般心理學建議包裝成作者的投資策略。
- 原文有 OCR 品質問題時，不要只靠章節標題推測摘要；回查相應章節。分析結果放在衍生檔，不混入原文章節。

## 共通收尾步驟

檢查產生的檔案數量與內容是否合理：

1. 章節檔案數與 TOC/spine 相符，章名正確，沒有大量空檔或頁面遺漏/重複；掃描 PDF 確認 OCR 覆蓋全頁並抽查原 PDF 對照。
2. `images/` 內有實際 JPG/PNG 資產；每個 `![...](images/...)` 路徑都存在。PDF 路徑記錄輸出頁碼，不預設複製所有掃描頁。
3. 使用者要求完整處理時，依書籍性質確認 `書籍摘要.md` 和/或 `投資策略框架.md` 是否應產生；摘要與框架需有章節定位，不能只用標題臆測。
4. metadata 的來源、格式、頁數、OCR 引擎/DPI 與章節清單要和實際檔案相符。
5. 封面/版權頁與 metadata 的版本、出版社、語言及譯者資訊一致；有差異就更正或標示待核對。摘要和框架有代表性章節作依據，引用頁碼/例子時回查原頁，不要讓重複 OCR 或明顯亂碼進入衍生文件。

只有在使用者指示時才 `git add` / `commit` / `push`。

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

### `scripts/assemble_pdf_ocr_markdown.py`（方法 C 的工作稿組裝）

- `--pdf` / `--cache` / `--out-dir`：來源 PDF、逐頁 OCR cache 與書籍資料夾（必要）。
- `--title` / `--author` / `--source-url`：來源書目資料（必要）；出版社/簡介可用 `--publisher` / `--intro` 補充。
- `--engine` / `--dpi` / `--date`：需與 OCR cache 的檔名設定一致；預設引擎 `baidu`、DPI `200`。
- `--overwrite`：只允許替換既有 `00.md` 與 `metadata.md`；不會刪除其他章節或圖片。使用前先核對輸出目錄與現有檔案。

### `scripts/render_pdf_pages_to_jpg.py`（方法 C 的圖片輸出）

- `--pdf`：來源 PDF 路徑（必要）。
- `--out-dir`：JPG 輸出目錄，通常是 `books/[書名]/images`（必要）。
- `--pages`：以逗號分隔的 1-based 頁碼（必要；只輸出指定頁，避免意外建立大量整頁影像）。
- `--dpi`：輸出解析度，預設 `180`。
- `--overwrite`：明確允許覆寫同名 JPG；預設遇到已存在的目標會停止。

## 已知限制

- 方法 A 依賴有效的登入 session cookie，過期需重新登入取得。
- 方法 B 依賴頁面內 epub.js 的全域變數命名（`window.reader.book`），若閱讀器版本更新導致變數改名，需重新用 `evaluate_script` 探索（`() => Object.keys(window).filter(k => /book|epub|reader/i.test(k))`），且只能取得純文字，無排版與圖片。
- OCR 技能只回傳文字 Markdown/cache，不建立 JPG，也不會產生摘要或投資策略框架；PDF 視覺資產需另外從來源 PDF 匯出。
- `投資策略框架.md` 由 `skill-investment-decision-coach` 的提煉流程產生，不是 EPUB/PDF 轉檔器的副作用。
- EPUB 方法 A 從 `00.md` 開始（與 spine index 對齊，符合 Miz.Fetch 現有書籍慣例）；方法 B 從 `01.md` 開始（過濾極短章節後重新編號）。PDF 章節依實際 TOC/標題編號，與 OCR 工作稿 `00.md` 無固定對應。混用前先統一命名策略，避免同一本書編號不一致。
