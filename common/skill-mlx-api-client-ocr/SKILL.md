---
name: skill-mlx-api-client-ocr
description: 使用自建在 Mac-mini 上的 OCR API 服務，將 PDF 或圖片報告轉錄為 Markdown 格式，適用於健康報告或各類文件的數位化分析。
---

# Mac-mini OCR API 整合技能 (skill-mlx-api-client-ocr)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.7.2（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee/FamilyHealthyCheck |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-mlx-api-client-ocr`） |
| 維護者 | wenchiehlee |

此技能封裝了與 Tailscale 虛擬局域網路內自建的 Mac-mini OCR API 的連線與排版抓取。它能自動將您上傳的 PDF 檔案或圖片（JPG/PNG 等）傳送至 Mac-mini 伺服器，利用 OCR 引擎進行文字轉錄，並以結構清晰的 Markdown 格式回傳，方便後續的數據提取與分析。

對 PDF，預設採用 hybrid 流程：先保留 PDF 內建文字層，只有無文字層或文字層不足的頁面才送 Mac-mini OCR。這可避免把乾淨的官方文字層覆蓋成較差的 OCR 結果，也能大幅降低整份簡報 OCR 的時間。

## 📦 技能結構說明
當您將此技能複製到其他專案時，整個技能資料夾結構如下：
```text
skill-mlx-api-client-ocr/
├── SKILL.md               # 技能描述與對接指引 (本檔案)
├── metadata.json          # 機器可讀 metadata（名稱、版本、來源），供版本檢查使用
├── self_update.py         # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    ├── ocr_client.py      # 連線與 API 傳送客戶端腳本 (支援引擎選擇與回傳計時資訊)
    ├── benchmark_ocr_engines.py # 同頁面串行比較 Baidu / Paddle 的速度
    ├── pdf_fallback.py    # Mac-mini 離線時的本地非 OCR PDF→Markdown 退援轉換
    ├── refine_todo_ocr.py # 補轉錄 Markdown 中標記 TODO:OCR 的頁面
    ├── test_refine_todo_ocr.py # 空 OCR 回退到 PDF 內嵌文字的迴歸測試
    ├── convert_ir_pdfs.py # 批次處理法說會簡報 PDF 轉錄工具
    └── heic_convert.py    # HEIC 圖片（手機拍攝文件）轉 PNG 後送 OCR 轉錄
```

## ⚙️ 前置環境配置
在目標專案中啟用此技能前，請確保完成以下配置：

### 1. 安裝 Python 套件依賴
在專案中執行以下命令安裝必備套件：
```bash
pip install requests python-dotenv pypdf PyMuPDF
```

若需轉錄 HEIC 圖片（如 iPhone 拍攝的政府文件、稅務資料照片），額外安裝：
```bash
pip install pillow-heif
```

（`pypdf` 供離線退援模式使用；若只用線上 OCR 可省略。）

### 2. 配置環境變數
在目標專案的根目錄下建立 `.env` 檔案（並務必在 `.gitignore` 中排除 `.env`），只寫入 Mac-mini OCR API 金鑰與其他可選設定；OCR endpoint 已固定為 `http://mac-mini.tail28f10.ts.net:5001/ocr`：
```env
# Mac-mini OCR API 設定
OCR_API_KEY=<your-api-key>
# 選用：baidu（預設）或 paddle
OCR_ENGINE=baidu
```

### 3. OCR server live check

Before every OCR upload, the client performs an unauthenticated `GET http://mac-mini.tail28f10.ts.net:5001/health` check. The request proceeds only when HTTP status is `200` and the JSON response contains `status: "ok"`; connection errors, timeouts, non-200 responses, and non-OK statuses fail before the document is uploaded.

The live-check timeout is 5 seconds. Use `check_ocr_server_live()` directly when a workflow needs to verify server availability without uploading a document.

## 📊 AI Model Usage 統計

OCR 的模型使用量由 `skill-mlx-api-server` 的 `/ocr` endpoint 送出 Amplitude `llm_call`，依請求記錄引擎和模型（Baidu Unlimited-OCR 或 PaddleOCR-VL-1.6）。請求使用 `X-App-Name` 區分專案。

## 🚀 使用方式與範例

### 💡 方式 A：在 Python 程式碼中作為模組導入
您可以直接導入 `transcribe_document_to_markdown` 函數，在您的自動化腳本中直接呼叫：
```python
from scripts.ocr_client import transcribe_document_to_markdown

try:
    markdown_text = transcribe_document_to_markdown("path/to/report.pdf", dpi=200, engine="paddle")
    print("轉錄成功！內容摘要：")
    print(markdown_text[:500])
except Exception as e:
    print(f"轉錄失敗：{e}")
```

### 🖥️ 方式 B：在終端機中作為命令列工具執行
您也可以直接以指令方式執行腳本，將轉錄後的 Markdown 存成檔案：
```bash
# 語法：python ocr_client.py <檔案路徑> [DPI，預設200]
python scripts/ocr_client.py path/to/report.pdf > output.md
# 或指定 Paddle：python scripts/ocr_client.py path/to/report.pdf 200 paddle
```

引擎也可用 `OCR_ENGINE=baidu` 或 `OCR_ENGINE=paddle` 設定；未指定時沿用 Baidu，維持舊呼叫相容。TODO 補頁可用 `refine_todo_ocr.py ... --engine paddle` 指定引擎，完成標記會記錄 `engine="mac-mini-paddle"` 或 `engine="mac-mini-baidu"`。

### 📏 方式 C：以相同頁面比較兩引擎速度

先將代表性頁面準備成一頁一檔的 PDF 或原始影像，兩個引擎會依序各跑完整批次，避免逐頁切換造成 Paddle 模型冷啟動。第一筆列為 first-request（包含模型啟動/載入），其餘列為 warm。輸出 Markdown 各自存檔，`timings.jsonl` 保留每頁引擎、成功狀態、client 總時間，以及 server 的 queue、模型就緒、render、pipeline setup、inference 與 process 時間：

```bash
python scripts/benchmark_ocr_engines.py pages/*.png --dpi 200 --out results/ocr-benchmark --first-engine baidu
# 下一輪改成 --first-engine paddle；兩次結果分開保存
```

比較時分開呈現冷啟動與暖機頁面的中位數、p95；主要速度指標用模型 `inference_s`，端到端採 `client_elapsed_s`，並單獨檢視 `queue_wait_s`，避免把等待其他請求的時間算成引擎速度。相同 DPI、同一批頁面、固定批次順序後，再交換兩引擎的批次先後重跑一次可降低溫度/背景負載偏差。逾時頁面記錄為失敗並保留，不自動換引擎重試。辨識精度和表格結構需另外對照原始頁面評估，不能用速度推斷品質。

### 📈 方式 D：批次處理法說會簡報 (IR PDFs)
如果您需要批次處理多個投資關係相關的 PDF，可以使用 `convert_ir_pdfs.py`。此腳本會先做文字層抽取，再只對必要頁面補 OCR；Mac-mini 離線時會保留 `TODO:OCR` 標記，不會用低品質 OCR 覆蓋乾淨文字層：
```bash
# 掃描全部股票資料夾進行轉換：
python scripts/convert_ir_pdfs.py

# 只處理特定指定股票代碼的資料夾：
python scripts/convert_ir_pdfs.py 2301 DELL
```

### 🔌 方式 E：Mac-mini 離線時的退援模式與 TODO:OCR 工作流程
當 Mac-mini 不在線時，可先用本地文字層抽取產生暫用 Markdown，之後再補做 OCR：

```bash
# 步驟 1：文字層抽取（僅抽取 PDF 內嵌文字層，不做 OCR）
python scripts/pdf_fallback.py path/to/report.pdf > output.md

# 步驟 2：檢視哪些頁面需要補 OCR（離線可用）
python scripts/refine_todo_ocr.py output.md --list

# 步驟 3：Mac-mini 恢復後，只補轉錄標記的頁面（就地更新 output.md）
python scripts/refine_todo_ocr.py output.md --pdf path/to/report.pdf
# 或只補指定頁：--pages 3,7
```

**TODO:OCR 標記格式**（機器可讀，`refine_todo_ocr.py` 以此定位頁面）：

```html
<!-- TODO:OCR source="report.pdf" page=3 reason=scanned-page -->
```

*   `reason=scanned-page`：該頁幾乎沒有文字層（掃描影像頁），整頁需要 OCR。
*   `reason=embedded-images`：該頁有文字層但含內嵌圖片，且使用者明確要求 `--mark-embedded-images` 時才標記。
*   補轉錄完成後，標記會被替換為 `<!-- OCR:done source="..." page=N date="..." -->`，OCR 結果直接取代該頁內容。
*   若 API 回傳成功但 Markdown 為空，client 會回退至來源 PDF 的內嵌文字層；`OCR:done` 會以 `content_source="pdf-text-layer-fallback"` 註明實際內容來源。修復已經寫入的空結果時，執行 `python scripts/refine_todo_ocr.py report.md --pdf report.pdf --repair-empty`，可只修復空結果而不重跑 OCR。
*   Mac-mini 回傳 HTTP 504，或 client 的 OCR response read timeout 時，`refine_todo_ocr.py` 會在該頁 TODO 下方寫入／累加 `<!-- OCR:timeout page=N count=K last="..." kind="http-504|client-read-timeout" -->`，並在本機 fallback 前立即存檔。若重試後仍失敗，TODO 和 timeout 記錄都會保留；若本機 fallback 完成，`OCR:done` 標記會帶上 `mac_mini_timeouts`、最後 timeout 時間與類型，保留該頁累計次數。
*   Mac-mini OCR API 若回傳 detector/debug 標記或 `save results` 區塊，client 會在寫檔前清理，只保留可讀 Markdown。
*   注意：對純掃描 PDF（如掃描的健檢報告）只能先產生整頁 TODO:OCR 標記的骨架；表格與版面資訊仍需等 OCR 補轉錄後才可用。

Timeout 記錄範例：

```html
<!-- TODO:OCR source="report.pdf" page=31 reason=scanned-page -->
<!-- OCR:timeout page=31 count=2 last="2026-09-30T12:33:29+08:00" kind="http-504" -->
```

`count` 只在 server 明確回傳 `504` 或 OCR response read timeout 時增加；連線失敗和其他 HTTP 錯誤不計入。`kind` 區分 server timeout 與 client read timeout，避免把尚未確認的 server 狀態誤記為 900 秒 server timeout。

### 📸 方式 F：HEIC 圖片轉錄

手機（尤其 iPhone）拍攝留存的政府文件、單據常以 HEIC 格式儲存，OCR API 只吃 PDF/JPG/PNG，需先轉檔。`heic_convert.py` 會把 HEIC 轉成暫存 PNG 後再送 OCR：

```bash
# 單一檔案，輸出至 stdout
python scripts/heic_convert.py path/to/photo.heic > output.md
```

批次處理整個資料夾時，可自行寫一段迴圈呼叫模組函式：
```python
from pathlib import Path
from scripts.heic_convert import transcribe_heic_to_markdown

for heic_path in sorted(Path("Images").glob("*.HEIC")):
    md_path = heic_path.with_suffix(".md")
    md_path.write_text(transcribe_heic_to_markdown(heic_path), encoding="utf-8")
```

若原始影像與其他轉寫內容有差異，一律以 HEIC 原始影像的 OCR 結果為準。

## 🛡️ 穩健性設計與異常處理 (Robust Design)
*   **超時控制**：由於 PDF 的轉錄需要較長時間，請求的讀取超時（timeout）設為 `900` 秒，防止大型檔案傳輸中斷。
*   **例外捕捉**：自動補捉伺服器忙碌（503 錯誤）、網路中斷及認證失敗等異常，並拋出詳細的診斷訊息。
*   **編碼相容性**：針對 Windows 主機提供 UTF-8 stdout 自動重新配置，防止因檔名或內容中的中文字元導致 Unicode 噴錯。

## 🧭 Known TODO

*   **JPG/PNG table OCR response handling**：2026-09-01 在 `TW-institutional-research` 驗證 YouTube keyframe JPG 表格時，client request 可連到 Mac-mini `/ocr` endpoint，但數分鐘內沒有回傳可用 Markdown，最後只能中斷並改用本地 Tesseract fallback。需要補強：
    *   對單張圖片加入較短且可設定的 read timeout / progress heartbeat，避免 CLI 長時間無輸出。
    *   在 timeout 或空 response 時輸出可稽核的錯誤 metadata（檔名、endpoint、elapsed time、HTTP 狀態若可得），不要讓呼叫端誤判為成功。
    *   增加圖片表格專用 smoke test：JPG/PNG → Markdown table，確認 server 回傳內容不只是 raw OCR text，且不含 detector/debug/save-results 噪音。
    *   明確記錄 fallback policy：若 MLX OCR 未成功，產出的表格必須標示為 fallback OCR / low confidence，不能宣稱為 Mac-mini OCR 成功結果。

## 🔄 版本管理與更新
*   本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-mlx-api-client-ocr`；各專案（FamilyHealthyCheck、Tax、MOPS 等）內的副本皆由登錄庫部署而來。
*   版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
*   檢查並更新到登錄庫最新版本：在技能資料夾內執行
    ```bash
    python self_update.py
    ```
    僅當登錄庫版本較新時才會覆寫本地檔案。
*   修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
