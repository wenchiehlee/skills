---
name: skill-stock-investorevent-fetch
description: >-
  在本機依據儲存庫自己的台股觀察名單
  (StockID_TWSE_TPEX.csv / StockID_TWSE_TPEX_focus.csv) 與美股觀察名單
  (raw_conceptstock_company_metadata.csv)，重新產生該儲存庫的 raw_event_upcoming_earnings.csv。
  將每筆事件分類為財報、法說會或受邀法說。以相同版本部署至 InvestorConference 與
  InvestorEvents，讓兩個儲存庫以相同方式計算事件日期與會計季度標籤。
  適用於即將發布的財報／法說會行事曆過時、觀察名單變更，或
  skill-company-investorconference-ingest 的 --auto-todo /
  --update-readme 需要最新行事曆資料之前。
---

# 投資人事件擷取技能

## 角色

你負責讓執行此技能的儲存庫內的 `raw_event_upcoming_earnings.csv` 保持正確且自足。
`InvestorConference` 與 `InvestorEvents` 都在 `skills/skill-stock-investorevent-fetch/` 下部署相同副本。
InvestorConference 的 `skill-company-investorconference-ingest` `--auto-todo` 掃描與 README 產生流程，
以及 InvestorEvents 的 `weekly-earnings.yml` + `sync-to-Downstream.yml`，都依賴這份 CSV
具有正確的日期*與*正確的類別分類，且兩邊的計算方式必須相同。

> [!IMPORTANT]
> 絕不可讓兩個儲存庫的 `scripts/fetch_upcoming_earnings.py` 副本出現差異。
> 應在此技能的集中管理儲存庫 (`../skills`) 修正錯誤或新增分類邏輯，再使用
> `self_update.py --deploy-all` 重新部署至兩個使用端，不要直接修改單一儲存庫內的副本。
> 先前曾出現版本分歧：InvestorEvents 停留在尚未支援 `受邀法說` 的 645 行版本，
> 而 InvestorConference 已使用 946 行版本，包含 `KNOWN_US_CALENDAR_YEAR_EARNINGS`
> 會計季度不一致問題的修正。這正是此共用技能要避免的失敗情境。

## 前置條件

從使用此技能的儲存庫根目錄 (`InvestorConference` 或 `InvestorEvents`) 執行。
該目錄必須有以下檔案（若缺少，先下載；不可自行編造或手動編輯）：

- `StockID_TWSE_TPEX.csv` — 完整台股觀察名單 (代號,名稱)，透過 yfinance 取得台股財報日期。
- `StockID_TWSE_TPEX_focus.csv` — 重點台股觀察名單，用於逐檔擷取 MOPS 法說會資料（速度較慢）。
- `raw_conceptstock_company_metadata.csv` — 美股觀察名單，包含 `Ticker`、`公司名稱` 與 `即將發布`（權威會計季度標籤）。

若資料看起來已過時，執行此技能前，先透過 `Get觀察名單.py` 更新兩份
`StockID_TWSE_TPEX*.csv`，並透過 ConceptStocks 同步更新 `raw_conceptstock_company_metadata.csv`。

## 事件識別與預定事件的界線

行事曆是事件紀錄清單，不是資料匯入健康狀態表：

- 同日的 `法說會` 與 `財報` 應保留為兩筆獨立紀錄 (`1 + 1`)。不可依日期將它們去重；應透過相同的公司／會計季度識別資訊配對。
- 未來的行事曆資料列若尚無素材，狀態應為 `planned/not_due`，而非 `Broken`。在到期日之前，或在明確要求收集素材之前，下游健康監控必須將未來／尚未到期的資料列排除於 Healthy/Warning/Broken 的分母之外。
- 配對的 `財報` 資料列，即使日期與 `法說會` 相同，仍然是財報紀錄。`pdf_only` 僅適用於沒有法說會／音訊／逐字稿訊號的獨立財報事件。

## 標準流程

```bash
python skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py
```

可選擇明確指定日期範圍（預設：今天往前 30 天至往後 60 天）：

```bash
python skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py --start 2026-07-01 --end 2026-10-31
```

InvestorEvents 的 `weekly-earnings.yml` 與 `fetch_all_events.py` 會從儲存庫根目錄
呼叫此腳本的 `generate_upcoming_earnings()`，詳見下方「InvestorEvents 整合」。

腳本依序執行以下步驟：

1. 從美股觀察名單來源載入美股觀察名單與 `即將發布` 會計季度對照表，來源為 `raw_conceptstock_company_metadata.csv`。
2. 從 MOPS 擷取重點觀察名單 (`StockID_TWSE_TPEX_focus.csv`) 的台股法說會日期。
3. 透過 `yfinance` 取得美股觀察名單中每個股票代號的財報日期。
4. 透過 `yfinance` 取得完整觀察名單 (`StockID_TWSE_TPEX.csv`) 的台股財報日期；上櫃／OTC 股票在 `.TW` 查詢失敗時改用 `.TWO`。
5. 若先前取得的 MOPS 法說會日期較可靠，將台股財報日期同步至該日期（yfinance 的台股日期常是過時的估計值）。
6. 合併至 `raw_event_upcoming_earnings.csv`：依事件名稱比對既有資料列，更新日期與類別，新增資料列；為每筆尚未配對法說會的美股財報資料列衍生一筆同日法說會資料列（包含先前執行時已儲存的資料列，不限於本次新擷取的資料。yfinance 沒有獨立的法說會時間來源，因此美股的財報與法說會無法據此區分）；移除近似重複的財報資料列，並依日期由新到舊排序。

## 類別分類規則

每筆資料列的類別必須且只能是以下其中之一：

| 類別 | 意義 | 指派方式 |
|------|---------|--------------------|
| `財報` | 財務報告發布日期 | 任何來自 yfinance 的財報日期資料列（美股或台股）。 |
| `法說會` | 配合該季度財報舉行的例行投資人法說會 | MOPS 台股資料列，其日期距事件所屬會計季度結束日在 `INVITED_MEETING_THRESHOLD_DAYS`（50 天）以內。 |
| `受邀法說` | 受邀參加的投資人論壇／會議，未與新發布的季度財報連動 | MOPS 台股資料列，其日期在季度結束日之後超過 50 天；採用與 `skill-company-investorconference-ingest` 的 README 產生器相同的判斷方式，讓整個流程的分類一致。 |

這是完整重新分類，不是由下游加上的標籤：每次 `save_csv()` 重寫時，也會重新統一*既有*
資料列的類別（包含舊版的 `財報公告` 值）。因此，執行此技能會自動遷移舊資料，
不需要另寫一次性的遷移腳本。

## 來源規則

- 絕不可手動編輯 `raw_event_upcoming_earnings.csv`；一律透過此腳本重新產生，確保合併／去重／分類一致。
- 台股與美股觀察名單是決定追蹤哪些股票的唯一依據；不要在此技能內寫死股票清單。
- 美股會計季度標籤應先呼叫 `skill-stock-fiscal-quarter-resolve`。若回傳 `fiscal_offset` 或 `calendar_year`，優先使用依日期推導的標籤，而非 `raw_conceptstock_company_metadata.csv`，因為中繼資料可能已過時（例如 NVDA 2026-08-26 的官方季度是 `FY2027 Q2`，不是過時的 `FY2026 Q4`）。若解析器回傳 `unknown`，才改用中繼資料的 `即將發布`。
- 下游使用端（`skill-company-investorconference-ingest` 的 `ingest_from_todo` / `update_readme`）會直接將類別讀為 `財報` / `法說會` / `受邀法說`；不要重新將 `財報公告` 作為輸出值。
- `受邀法說` 資料列可能代表與該季度例行財報日法說會分開的出席活動（例如數週或數月後的受邀論壇）。`update_readme` 會防止將例行法說會已匯入的素材附加至這類資料列，除非其日期與同季度 `財報` 日期相距 14 天以內；詳見 `skill-company-investorconference-ingest` 的 SKILL.md（「README `--update-readme` 合併規則」）。即使該季度已有素材，也不要假設每筆 `受邀法說` 資料列都有音訊／逐字稿。

## InvestorEvents 整合

`InvestorEvents` 除了可獨立執行此腳本，也會將它匯入為模組：
`fetch_all_events.py` 使用 `from fetch_upcoming_earnings import generate_upcoming_earnings`，
預期能從儲存庫根目錄匯入此模組。由於正式副本目前位於
`skills/skill-stock-investorevent-fetch/scripts/fetch_upcoming_earnings.py`，InvestorEvents 的
`fetch_all_events.py` 與 `.github/workflows/weekly-earnings.yml` 會在匯入前，將該 scripts/ 目錄加入
`sys.path`（或設定 `PYTHONPATH` 後執行）；具體機制請參閱各檔案開頭。
不要在 InvestorEvents 根目錄重新加入 `fetch_upcoming_earnings.py` 副本，這正是最初造成版本分歧的原因。

## 取代方式

此技能是 `InvestorConference` 與 `InvestorEvents` 內產生 `raw_event_upcoming_earnings.csv`
的持續維護方式。絕不可手動編輯資料列，也不可讓任一儲存庫的副本出現差異；
應在集中管理儲存庫擴充此技能的腳本，再重新部署。

## 驗證

執行後，檢查標準輸出中的合併摘要（`新增 N 筆` / `更新日期 N 筆` /
`無變更`），再抽查分類：

```bash
python -c "
import csv
from collections import Counter
with open('raw_event_upcoming_earnings.csv', encoding='utf-8-sig') as f:
    print(Counter(r['類別'] for r in csv.DictReader(f)))
"
```

預期鍵值只會有 `財報`、`法說會`、`受邀法說`；任何其他值都代表分類出錯。
