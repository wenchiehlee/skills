---
name: pptx-to-md
description: 使用 python-pptx 將 PowerPoint (.pptx) 簡報轉換為 Markdown 格式，保留標題、項目符號、表格與講者備忘稿，並可選擇抽取內嵌圖片。
---

# PPTX 轉 Markdown 技能 (pptx-to-md)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-pptx-to-md`） |
| 維護者 | wenchiehlee |

此技能將 PowerPoint（`.pptx`）簡報檔案轉換為結構化的 Markdown 文本，
方便後續以純文字方式進行內容摘要、比對、搜尋或餵給 LLM 分析。
轉換完全在本地執行（不需外部 API 服務），依賴開源套件
[`python-pptx`](https://python-pptx.readthedocs.io/) 直接解析簡報 XML 結構。

## 📦 技能結構說明
當您將此技能複製到其他專案時，整個技能資料夾結構如下：
```text
pptx-to-md/
├── SKILL.md               # 技能描述與對接指引 (本檔案)
├── metadata.json          # 機器可讀 metadata（名稱、版本、來源），供版本檢查使用
├── self_update.py         # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    └── pptx_to_md.py      # PPTX → Markdown 轉換腳本 (支援 CLI 與模組導入)
```

## ⚙️ 前置環境配置
在目標專案中啟用此技能前，請確保完成以下配置：

```bash
pip install python-pptx
```

## 🚀 使用方式與範例

### 💡 方式 A：在 Python 程式碼中作為模組導入
```python
from scripts.pptx_to_md import convert_pptx_to_markdown

markdown_text = convert_pptx_to_markdown("path/to/deck.pptx", image_dir="images")
print(markdown_text[:500])
```

### 🖥️ 方式 B：在終端機中作為命令列工具執行
```bash
# 基本轉換，輸出到 stdout
python scripts/pptx_to_md.py path/to/deck.pptx > output.md

# 同時抽取投影片內嵌圖片到 images/ 資料夾（Markdown 內自動加上相對圖片連結）
python scripts/pptx_to_md.py path/to/deck.pptx --extract-images images > output.md

# 不包含講者備忘稿
python scripts/pptx_to_md.py path/to/deck.pptx --no-notes > output.md
```

## 📝 輸出格式說明

轉換結果採用以下慣例，方便後續程式化解析：

*   每張投影片以 `<!-- SLIDE:N -->` 標記開頭（N 為投影片序號，從 1 起算）。
*   投影片標題轉為 `## Slide N: 標題文字`。
*   一般文字方塊的段落轉為項目符號（`-`），並依原本的縮排層級巢狀呈現。
*   表格轉為標準 Markdown 表格（第一列視為表頭）。
*   群組圖形（group shape）會遞迴展開內部所有子圖形。
*   若指定 `--extract-images`／`image_dir`，圖片會存成 `slide{NNN}_img{NN}.{ext}`
    並在 Markdown 中以 `![slide{N} image](images/檔名)` 連結；未指定時圖片會被略過（不轉錄圖中文字，如需 OCR 請另行處理）。
*   講者備忘稿以 Markdown 引用區塊（`> **講者備忘稿：**`）附加在該投影片內容之後。
*   每張投影片結尾以 `---` 分隔線區隔。

## 🛡️ 穩健性設計與異常處理 (Robust Design)
*   **檔案不存在**：找不到指定的 `.pptx` 檔案時拋出 `FileNotFoundError` 並提前終止。
*   **空白段落過濾**：自動略過空白文字方塊與空白段落，避免產生大量空行。
*   **編碼相容性**：針對 Windows 主機提供 UTF-8 stdout 自動重新配置，防止因檔名或內容中的中文字元導致 Unicode 噴錯。
*   **圖片萃取失敗處理**：`python-pptx` 無法解析的圖形（如某些 OLE 物件）不會中斷整體轉換，僅該圖形略過。

## 🔄 版本管理與更新
*   本技能的唯一可信來源為 skills 登錄庫中的 `common/skill-pptx-to-md`；各專案內的副本皆由登錄庫部署而來。
*   版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json` 的 `version` 欄位。
*   檢查並更新到登錄庫最新版本：在技能資料夾內執行
    ```bash
    python self_update.py
    ```
    僅當登錄庫版本較新時才會覆寫本地檔案。
*   修改此技能時，請先更新登錄庫中的版本（並提升版本號），再部署到各使用端專案，避免副本之間出現分歧。
