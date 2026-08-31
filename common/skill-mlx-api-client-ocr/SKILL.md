---
name: skill-mlx-api-client-ocr
description: 使用自建在 Mac-mini 上的 OCR API 服務，將 PDF 或圖片報告轉錄為 Markdown 格式，適用於健康報告或各類文件的數位化分析。
---

# Mac-mini OCR API 整合技能 (skill-mlx-api-client-ocr)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.6.1（詳見 `metadata.json`） |
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
    ├── ocr_client.py      # 連線與 API 傳送客戶端腳本 (支援 CLI 與模組導入)
    ├── pdf_fallback.py    # Mac-mini 離線時的本地非 OCR PDF→Markdown 退援轉換
    ├── refine_todo_ocr.py # 補轉錄 Markdown 中標記 TODO:OCR 的頁面
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
在目標專案的根目錄下建立 `.env` 檔案（並務必在 `.gitignore` 中排除 `.env`），寫入您的 Mac-mini API 伺服器位址與 API 金鑰：
```env
# Mac-mini OCR API 設定
OCR_API_URL=http://mac-mini.tail28f10.ts.net:5001/ocr
OCR_API_KEY=<your-api-key>
```

## 📊 AI Model Usage 統計

OCR 的模型使用量由 `skill-mlx-api-server` 的 `/ocr` endpoint 送出 Amplitude `llm_call`：`service=mlx-api-server`、`stage=ocr`、`provider=baidu-ocr`、`model=baidu/Unlimited-OCR`。本 client skill 的責任是讓呼叫端能正確歸因 app，因此 HTTP request 應傳 `X-App-Name`；未傳時 server 會 fallback 到 `Baidu-OCR`，但全域報表就無法看出是哪個專案消耗 OCR。

## 🚀 使用方式與範例

### 💡 方式 A：在 Python 程式碼中作為模組導入
您可以直接導入 `transcribe_document_to_markdown` 函數，在您的自動化腳本中直接呼叫：
```python
from scripts.ocr_client import transcribe_document_to_markdown

try:
    markdown_text = transcribe_document_to_markdown("path/to/report.pdf", dpi=200)
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
```

### 📈 方式 C：批次處理法說會簡報 (IR PDFs)
如果您需要批次處理多個投資關係相關的 PDF，可以使用 `convert_ir_pdfs.py`。此腳本會先做文字層抽取，再只對必要頁面補 OCR；Mac-mini 離線時會保留 `TODO:OCR` 標記，不會用低品質 OCR 覆蓋乾淨文字層：
```bash
# 掃描全部股票資料夾進行轉換：
python scripts/convert_ir_pdfs.py

# 只處理特定指定股票代碼的資料夾：
python scripts/convert_ir_pdfs.py 2301 DELL
```

### 🔌 方式 D：Mac-mini 離線時的退援模式與 TODO:OCR 工作流程
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
*   Mac-mini OCR API 若回傳 detector/debug 標記或 `save results` 區塊，client 會在寫檔前清理，只保留可讀 Markdown。
*   注意：對純掃描 PDF（如掃描的健檢報告）只能先產生整頁 TODO:OCR 標記的骨架；表格與版面資訊仍需等 OCR 補轉錄後才可用。

### 📸 方式 E：HEIC 圖片轉錄

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

## 🔄 版本管理與更新
*   本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-mlx-api-client-ocr`；各專案（FamilyHealthyCheck、Tax、MOPS 等）內的副本皆由登錄庫部署而來。
*   版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
*   檢查並更新到登錄庫最新版本：在技能資料夾內執行
    ```bash
    python self_update.py
    ```
    僅當登錄庫版本較新時才會覆寫本地檔案。
*   修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
