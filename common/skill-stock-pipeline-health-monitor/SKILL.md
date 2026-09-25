---
name: skill-stock-pipeline-health-monitor
description: 複合技能（composite skill），本身不抓資料，而是委派給 skill-finmind-fetch、skill-goodinfo-fetch、skill-google-alert-fetch、skill-googlesearch-factsets-fetch 等所有 skill-*-fetch 抓取技能；負責維護 biztrends.TW README.md 的 Data Health Dashboard 新鮮度、資料系統架構 Repo 角色對照表，並稽核跨 repo CSV 同步 YAML 是否與 docs/data_sync_table.md 一致，同時在 GoodInfo 與 FinMind 輸出同一份 CSV schema 時，判斷該優先委派哪個 fetch 技能補資料。
---

# 資料健康與系統架構協調技能 (Data Health & Architecture Orchestrator)

## 定位：複合技能 (Composite Skill)

此技能是**協調層（orchestrator）**，不是另一個抓取技能：

- **不重新實作**任何網站爬蟲、API 呼叫或 XLS→CSV 轉檔邏輯——那些邏輯已存在於各個 `skill-*-fetch` 技能中。
- 職責只有三件事：(1) 判斷「該找哪個 fetch 技能」、(2) 彙整各 fetch 技能產出的健康度成單一 Dashboard、(3) 稽核跨 repo 的資料流與同步設定是否仍與 README/docs 一致。
- 呼叫其他技能時，一律使用 `Skill` 工具原生委派（例如 `Skill(skill: "skill-finmind-fetch", ...)`），不要用 Bash 手動重建那些技能已經封裝好的指令細節；本文件列出的指令範例只是給協調者判斷「該委派誰」用的參考。

## 適用場景

- 使用者要求更新或檢查 README.md 的 **Data Health Dashboard**（表一核心管線新鮮度、表二上游媒體/新聞收錄品質）。
- 某個 `raw_*.csv` 資料過期或損壞，需要判斷該委派 `skill-goodinfo-fetch` 重新下載，還是改委派 `skill-finmind-fetch` 用 API 補資料（兩者輸出同一份 stage1 CSV schema）。
- 需要確認跨 repo 的 CSV 同步（`repo-file-sync-action` 的 `.github/sync-*.yml`）是否仍與 `docs/data_sync_table.md`、`data/data_freshness_manifest.csv` 一致，避免文件與實際 workflow 設定各說各話。
- 新增一個上游 repo 或一個新的 `skill-*-fetch` 技能後，需要同步更新 README.md 的「資料系統架構」Repo 角色對照表與 `docs/data_pipeline_diagram.md`。

## 委派對照表 (Delegation Map)

判斷「這個資料類別歸哪個 fetch 技能負責」的第一張查表：

| 資料類別 | 委派技能 | 產出健康度來源 |
|---|---|---|
| 台股個股/大盤：股利、營收、K線、融資融券、財務比率（stage1 raw CSV） | `skill-finmind-fetch`（API 管道，避開反爬蟲）或 `skill-goodinfo-fetch`（網頁下載，欄位最完整） | `data/Python-Actions.GoodInfo.Analyzer/stage1_goodinfo_health.csv`（見下方「流程二」） |
| GoodInfo 下載／轉檔／公司層級富化三段管線 | `skill-goodinfo-fetch` | `data/Python-Actions.GoodInfo/goodinfo_download_health_summary.csv`、`stage1_goodinfo_health_summary.csv` |
| 台股財報 PDF → MD（含 OCR） | `skill-mops-fetch` | `data/MOPS/mops_health_summary.csv` |
| Google Alert 新聞 + LLM 情緒分析 | `skill-google-alert-fetch` | `data/GoogleAlertManager/google_alert_health_summary.csv` |
| FactSet 分析師預估、搜尋結果 | `skill-googlesearch-factsets-fetch` | `data/reports/` 下 quarantine/coverage 報告 |
| 法說會音檔/簡報/逐字稿與官方財務結果材料 ingestion | `skill-company-investorconference-ingest`（音檔、IR、transcript、US earnings release/SEC 8-K financial PDF）／`skill-company-investorconference-ir-pdf-md`（PDF→MD） | `data/InvestorConference/investor_conference_health_summary.csv` |
| 法說會重點萃取 Digest | `skill-company-investorconference-digest` | 同上（依 `investor_conference_digest` 欄位） |
| 法說會/財報行事曆 | `skill-stock-investorevent-fetch` | — |
| Facebook 粉專貼文 | `skill-facebook-fetch` | — |
| Yahoo Finance 分析師預估、法說會前摘要 | `skill-yahoo-finance-fetch` | — |
| YouTube 頻道影片/字幕 | `skill-youtube-channel-fetch` | — |
| Scribd/Miz 文件下載 | `skill-scribd-pdf-fetch` / `skill-miz-fetch` | — |

新出現的 `skill-*-fetch` 技能一律先加進這張表，再決定要不要在 Dashboard 表二新增一列。

## 流程一：Data Health Dashboard 刷新

Dashboard 由 `<!-- DATA_HEALTH_DASHBOARD_START -->` … `<!-- DATA_HEALTH_DASHBOARD_END -->` 包住，位於 README.md 頂部，分兩張表：

1. **表一（核心管線新鮮度）**：由既有的 `python scripts/check_csv_freshness.py` 產生/覆寫，讀取 `data/data_freshness_manifest.csv` 逐檔驗證，寫回 `data/data_freshness_status.csv`、`data/data_freshness_summary.csv`、`data/data_health_dashboard.csv` 並更新 README 表一。此技能不重寫這支腳本，只在委派前後檢查它是否成功執行（exit code、`data_health_dashboard.csv` 的 `checked_at` 是否比執行前新）。
2. **表二（上游媒體/新聞收錄品質）**：每一列的資料來自對應 fetch 技能各自維護的 `*_health_summary.csv`（見上方委派對照表最後一欄）。此技能**不產生**這些 summary CSV——那是各 fetch 技能的職責；此技能只負責：
   - 檢查每個 `*_health_summary.csv` 是否存在、`checked_at` 是否在 `stale_after_days` 門檻內。
   - 若缺檔或過期，回報「應委派哪個 fetch 技能重新產生」（對照上表）。
   - 若欄位/表格結構跟 README 表二既有欄位對不上，回報需要更新 README 表格結構，而不是自行捏造欄位。

標準操作順序：

```bash
python scripts/check_csv_freshness.py
python skills/skill-stock-pipeline-health-monitor/scripts/audit_health_summaries.py
```

### 表二 `mops_pdf_sync` 的 `ocr_needed_count` 非零時

`mops_health_summary.csv` 的 `ocr_needed_count` 只給總數，不列出是哪幾份 PDF。此技能不做 OCR（那是 `skill-mops-fetch` 的職責），但會掃描本機 sibling `MOPS` repo 的 `downloads/` 找出實際還有 `TODO:OCR` 標記的檔案，並印出委派指令：

```bash
python skills/skill-stock-pipeline-health-monitor/scripts/detect_mops_ocr_backlog.py
```

實際修復一律委派 `skill-mops-fetch` 的 `scripts/refine_pending_ocr.py`（於 `MOPS` repo 執行）——它會一次掃描整個 `downloads/` 樹並呼叫 Mac-mini OCR API 修補，不需要逐一知道是哪個 company/year/quarter。

## 流程二：GoodInfo vs FinMind 智慧選源 (Smart Source Selection)

GoodInfo 與 FinMind 對同一批 GoodInfo Type（1/4/5/6/7/8/9/11/12/13/14/15/16/17/18/19）輸出**完全相同欄位結構**的 stage1 CSV（詳見 `skill-finmind-fetch` SKILL.md），因此當某個 Type 過期/損壞時，可以選擇改用 API 管道而非重跑網頁下載。

判斷依據：`data/Python-Actions.GoodInfo.Analyzer/stage1_goodinfo_health.csv`（同步自 Analyzer 的逐檔健康度，欄位含 `data_type`＝GoodInfo Type 編號、`dest_path`＝`data/stage1_raw/raw_*.csv`、`stage1_health_status`）。

```bash
python skills/skill-stock-pipeline-health-monitor/scripts/select_data_source.py
# 只看特定 type
python skills/skill-stock-pipeline-health-monitor/scripts/select_data_source.py --type 13
```

腳本輸出每個 Type 的建議：

- `stage1_health_status` 為 `healthy`/`warning` → 不需要委派，維持現況。
- 為 `stale`/`broken`/缺檔，且 Type 有 FinMind adapter → 建議委派 `skill-finmind-fetch`（附上對應 `fetch_typeN.py` 指令範本）。
- 為 `stale`/`broken`，但 Type 沒有已知 FinMind adapter → 建議委派 `skill-goodinfo-fetch` 的 `download` 段重跑（附上 `goodinfo_pipeline.py download <TYPE>` 指令範本），因為沒有替代來源。

不自動執行委派動作，只輸出建議與指令範本；實際執行一律由使用者或呼叫端透過 `Skill` 工具觸發對應技能。

## 流程三：跨 Repo CSV 同步 YAML 稽核

三層同步架構（見 README「資料系統架構 §4 資料同步機制」）：Source Repo 腳本產出 → `repo-file-sync-action`（`.github/sync-*.yml`）推送 → 下游 repo 本地刷新。此技能稽核第二層是否仍與文件一致：

```bash
python skills/skill-stock-pipeline-health-monitor/scripts/audit_sync_config.py
```

腳本行為：

1. 解析 `docs/data_sync_table.md` 每一列的 `來源 Repo` / `核心檔案` / `同步目標` / `目標 Repo` / `同步設定 YAML`。
2. 對每個唯一的 `(來源 Repo, YAML 檔名)`，到本機 sibling repo 路徑（`../<來源 Repo>/<YAML 檔名>`）讀取該 `repo-file-sync-action` 設定檔，重用 `scripts/generate_sync_table.py` 既有的 YAML 解析函式。
3. 檢查文件列出的 `核心檔案`／`同步目標` 是否真的出現在該 YAML 的 `files:` 清單與 `repos:` 目標中。
4. 回報三類問題：YAML 檔案不存在（repo 可能已刪除該 workflow）、YAML 存在但文件列的檔案不在清單裡（文件過期）、YAML 裡有文件沒列出的新檔案（文件漏更新）。

此稽核只讀取本機 sibling repo（NAS 同層目錄）的檔案，不做任何遠端 git 操作，也不修改來源 repo。

## 流程四：資料系統架構維護

新增一個上游 repo 或 `skill-*-fetch` 技能時，下列項目要一起更新，缺一個就會讓 Dashboard 或架構圖與實況脫節：

1. README.md「資料系統架構 → Repo 角色對照表」：新增一列（層次／核心資料／信號類型／頻率）。
2. `docs/data_pipeline_diagram.md`：跨儲存庫資料流管線架構圖，補上新節點與資料流向箭頭。
3. `docs/data_sync_table.md` + `data/data_freshness_manifest.csv`：新增同步列（含 `source_repo`/`dest_path`/`stale_after_days`/`sync 設定 YAML`）。
4. `docs/manifest_definition_coverage.md`：若有新的 `raw_column_definition_*.md`，補上對照。
5. 若新增的是 `skill-*-fetch` 技能，回頭補上本文件「委派對照表」的一列。

本技能不自動改寫 README/docs 內容（避免用臆測資料覆寫既有敘述），只在委派前列出「這次變更要同步碰哪些檔案」的清單，實際文字修改由使用者確認後再編輯。

## 安全邊界

- 不直接呼叫任何外部網站或第三方 API；所有資料抓取一律透過 `Skill` 工具委派給對應 `skill-*-fetch`。
- 不覆寫其他 repo 自行維護的 `*_health_summary.csv`，只讀取彙整；那些檔案的產生邏輯屬於各自 fetch 技能。
- 跨 repo 檔案操作限定於本機 sibling repo 路徑（同一層 NAS 目錄），不做遠端 git push／PR；發現 YAML 與文件不一致時只回報，不自動修改其他 repo 的 workflow 設定。
- 資料不足或無法判斷時，明確列出缺少的檔案/欄位，不用自信語氣補完缺口。
