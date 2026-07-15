# Skills Registry

本儲存庫是共享的技能登錄庫，用來集中管理從多個儲存庫收集而來的可重用技能。目標是讓技能更容易被發現、版本化、重用與更新，避免各專案複製到缺少文件或已過期的技能定義。

## 目標

- 將不同儲存庫中的可重用技能集中收集到同一個位置。
- 為每個技能保留清楚的擁有者、來源與版本資訊。
- 讓下游儲存庫能夠偵測本地技能是否已過期。
- 支援從本儲存庫自動取得最新核准版本並更新技能。
- 依照各目標 LLM 的規則部署技能。
- 讓每個技能都能自包含，重用時不需要依賴原始來源儲存庫。

## 目前收錄的技能

下表由 `scripts/generate_skills_index.py` 自動產生（每日透過 GitHub Actions 更新），資料同步於機器可讀的 [`skills-index.yaml`](skills-index.yaml)。「修訂日期」為該技能資料夾在 git 中的最後 commit 日期。

<!-- SKILLS-TABLE:START -->
| 技能 | 群組 | 版本 | 說明 | 修訂日期 |
| :--- | :--- | :--- | :--- | :--- |
| [skill-all-models-benchmark](common/skill-all-models-benchmark) | common | 1.0.0 | 多模型與分析師共識效能評估標準作業程序。 | 2026-07-07 |
| [skill-conference-digest](common/skill-conference-digest) | common | 1.2.0 | 法說會重點萃取與分析 SOP（台灣股市）— 從法說會字幕(SRT)與簡報(Markdown)萃取影響股價的重要資訊 | 2026-07-05 |
| [skill-download-logo](common/skill-download-logo) | common | 1.0.0 | 指定台灣股票代碼或美股概念股 Ticker，自動下載高解析度公司官方 Logo PNG，並限制在固定大小。 | 2026-07-07 |
| [skill-mac-mini-ocr](common/skill-mac-mini-ocr) | common | 1.1.1 | 使用自建在 Mac-mini 上的 OCR API 服務（Tailscale 網內），將 PDF 或圖片轉錄為 Markdown 格式，適用於健康報告、稅務文件、財報等各類文件的數位化分析。 | 2026-07-07 |
| [skill-market-cost-distribution](common/skill-market-cost-distribution) | common | 1.0.0 | 台股市場籌碼持股成本分佈模擬（台新小時K+日K暖機雙池模型），輸出一致格式 PNG/CSV 與統一可信度、資料新鮮度標籤。 | 2026-07-15 |
| [skill-pptx-to-md](common/skill-pptx-to-md) | common | 1.0.0 | 使用 python-pptx 將 PowerPoint (.pptx) 簡報轉換為 Markdown 格式，保留標題、項目符號、表格與講者備忘稿，並可選擇抽取內嵌圖片。 | 2026-07-09 |
| [skill-revenue-expense-profit-predict](common/skill-revenue-expense-profit-predict) | common | 1.0.0 | 季度損益三線（營業收入 / 總支出 / 營業利益）底部加總預測 SOP | 2026-07-05 |
| [skill-revenue-predict](common/skill-revenue-predict) | common | 1.0.0 | 營收預測與 10-Model 評估 SOP | 2026-07-05 |
| [skill-taiex-compare](common/skill-taiex-compare) | common | 1.0.0 | 財報公布後，從 GitHub Issue 取得貼文內容，與內部 CSV 數字逐欄比對，自動回報差異 | 2026-07-07 |
| [skill-taiex-monitor](common/skill-taiex-monitor) | common | 1.0.0 | 財報行事曆監控：偵測資料缺漏並自動開 Issue，更新 README 看板 | 2026-07-07 |
| [skill-taiex-report](common/skill-taiex-report) | common | 1.0.0 | 生成台股/美股 SVG 投資決策報告（Finguider 卡片 + 營收歷史圖） | 2026-07-07 |
| [skill-taiex-sync](common/skill-taiex-sync) | common | 1.0.0 | 更新本地資料目錄索引，生成批次處理所需的投資標的清單 | 2026-07-07 |
| [skill-taiex-viz](common/skill-taiex-viz) | common | 1.0.0 | 不需 LLM，用 matplotlib 直接生成美股分部營收靜態 PNG 圖 | 2026-07-07 |

最後產生日期：2026-07-15
<!-- SKILLS-TABLE:END -->

## 技能版本管理

本登錄庫中的每個技能都必須版本化。版本資訊讓使用者可以比較本地副本與登錄庫版本，並判斷技能是否已過期。

建議版本格式：

```text
MAJOR.MINOR.PATCH
```

版本變更應遵循以下規則：

- `MAJOR`：行為、必要輸入、檔案結構或外部假設有破壞性變更。
- `MINOR`：向後相容的新功能、新工作流程或涵蓋範圍擴充。
- `PATCH`：修正、文字改善、metadata 校正，或不改變預期行為的小型內部更新。

每個技能都應包含可識別以下資訊的 metadata：

- 技能名稱
- 目前版本
- 來源儲存庫或原始出處
- 維護者或負責團隊
- 簡短描述
- 最後更新日期
- 相容性備註，如適用

## 建議技能目錄結構

技能應依目標 LLM 分組。每個 LLM 在 `skills/` 底下都有自己的子資料夾，該資料夾中的技能必須遵循該 LLM 的部署規則。

```text
skills/
  <llm-name>/
    <skill-name>/
      SKILL.md
      metadata.json
      README.md
      references/
      scripts/
```

最低必要檔案：

- `SKILL.md`：主要的可重用技能指令。
- `metadata.json`：供版本檢查與更新自動化使用的機器可讀 metadata。

選用檔案：

- `README.md`：供人閱讀的技能使用說明。
- `references/`：支援文件、範例或範本。
- `scripts/`：技能使用的輔助腳本。

`metadata.json` 範例：

```json
{
  "name": "example-skill",
  "version": "1.0.0",
  "source": "https://github.com/example/project",
  "maintainer": "example-team",
  "description": "Reusable instructions for an example workflow.",
  "updated_at": "2026-07-05",
  "compatibility": {
    "codex": ">=1.0.0"
  }
}
```

## LLM 部署規則

部署依 LLM 專屬資料夾組織。技能應從符合目標 LLM runtime 的資料夾部署，因為不同 LLM 可能期待不同的檔名、metadata 欄位、封裝規則或指令格式。

例如：

```text
skills/
  codex/
    skill-a/
  claude/
    skill-a/
  gemini/
    skill-a/
```

同一個概念上的技能可以存在於多個 LLM 資料夾中，但每份副本都必須有自己的版本與 metadata。如果某個 LLM 專屬版本與共用行為產生差異，應獨立更新該版本號，並在 `metadata.json` 中記錄相容性備註。

部署工具應執行：

1. 選擇目標 LLM 資料夾。
2. 驗證每個技能都符合該 LLM 要求的結構。
3. 在選定的 LLM 資料夾內比較版本。
4. 只安裝或更新與該目標 LLM 相容的技能。

## 更新模型

下游儲存庫應將本儲存庫視為共享技能的唯一可信來源。

使用者可以透過比較本地技能 metadata 與本登錄庫中的 metadata 來檢查更新：

1. 讀取本地技能名稱與版本。
2. 從本儲存庫取得對應技能的 metadata。
3. 比較版本。
4. 如果登錄庫版本較新，從本儲存庫取代或合併本地技能。
5. 在使用端儲存庫記錄更新後的版本。

這讓過期技能更容易被發現，也讓各專案能用一致方式更新到最新核准的技能定義。

## 收集規則

新增或更新技能時：

1. 將技能放在正確 LLM 資料夾底下的專屬目錄。
2. 包含 `SKILL.md` 與 `metadata.json`。
3. 使用語意化版本管理。
4. 在 metadata 中保留原始來源或出處。
5. 保持技能自包含。
6. 遵循目標 LLM 資料夾的部署規則。
7. 以增加 `MAJOR` 版本記錄破壞性變更。
8. 從其他儲存庫匯入技能時，避免不相關的格式調整。
9. 確認技能不需要私有儲存庫脈絡也能被閱讀與重用。

## 未來自動化

本儲存庫預期支援以下工具：

- 版本檢查器：回報使用端儲存庫中已過期的技能。
- 更新器：從本登錄庫取得最新技能版本。
- 驗證指令：檢查必要檔案與 metadata 欄位。
- changelog 產生器：依版本彙整技能更新內容。

第一個自動化目標應是一個能回答以下問題的簡單指令：

```text
哪些本地技能相較於本登錄庫已經過期？
```

第二個目標應是：

```text
將選定的本地技能更新到最新相容版本。
```

## 狀態

這是登錄庫 README 的第一版。隨著更多技能被收集，儲存庫結構、metadata schema 與自動化指令可能會持續演進。
