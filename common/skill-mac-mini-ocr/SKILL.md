---
name: mac-mini-ocr
description: 使用自建在 Mac-mini 上的 OCR API 服務，將 PDF 或圖片報告轉錄為 Markdown 格式，適用於健康報告或各類文件的數位化分析。
---

# Mac-mini OCR API 整合技能 (mac-mini-ocr)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.1（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee/FamilyHealthyCheck |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-mac-mini-ocr`） |
| 維護者 | wenchiehlee |

此技能封裝了與 Tailscale 虛擬局域網路內自建的 Mac-mini OCR API 的連線與排版抓取。它能自動將您上傳的 PDF 檔案或圖片（JPG/PNG 等）傳送至 Mac-mini 伺服器，利用強大的 OCR 引擎進行文字轉錄，並以結構清晰的 Markdown 格式回傳，方便後續的數據提取與分析。

## 📦 技能結構說明
當您將此技能複製到其他專案時，整個技能資料夾結構如下：
```text
mac-mini-ocr/
├── SKILL.md          # 技能描述與對接指引 (本檔案)
├── metadata.json     # 機器可讀 metadata（名稱、版本、來源），供版本檢查使用
├── self_update.py    # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    └── ocr_client.py # 連線與 API 傳送客戶端腳本 (支援 CLI 與模組導入)
```

## ⚙️ 前置環境配置
在目標專案中啟用此技能前，請確保完成以下配置：

### 1. 安裝 Python 套件依賴
在專案中執行以下命令安裝必備套件：
```bash
pip install requests python-dotenv
```

### 2. 配置環境變數
在目標專案的根目錄下建立 `.env` 檔案（並務必在 `.gitignore` 中排除 `.env`），寫入您的 Mac-mini API 伺服器位址與 API 金鑰：
```env
# Mac-mini OCR API 設定
OCR_API_URL=http://mac-mini.tail28f10.ts.net:5001/ocr
OCR_API_KEY=<your-api-key>
```

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

## 🛡️ 穩健性設計與異常處理 (Robust Design)
*   **超時控制**：由於 PDF 的轉錄需要較長時間，請求的讀取超時（timeout）設為 `900` 秒，防止大型檔案傳輸中斷。
*   **例外捕捉**：自動補捉伺服器忙碌（503 錯誤）、網路中斷及認證失敗等異常，並拋出詳細的診斷訊息。
*   **編碼相容性**：針對 Windows 主機提供 UTF-8 stdout 自動重新配置，防止因檔名或內容中的中文字元導致 Unicode 噴錯。

## 🔄 版本管理與更新
*   本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-mac-mini-ocr`；各專案（FamilyHealthyCheck、Tax、MOPS 等）內的副本皆由登錄庫部署而來。
*   版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
*   檢查並更新到登錄庫最新版本：在技能資料夾內執行
    ```bash
    python self_update.py
    ```
    僅當登錄庫版本較新時才會覆寫本地檔案。
*   修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
