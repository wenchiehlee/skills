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
  --update-readme 需要最新行事曆資料之前。與投資人素材矩陣整合時，保留來源識別與
  來源財季，依矩陣規則區分到期、適用性、暫停與素材缺漏。
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

## 與投資人素材矩陣對齊

在 biztrends.TW 使用此技能時，先閱讀 [素材矩陣](../../docs/investor_material_matrix.md)
的範圍定義與圖例，再核對 `data/InvestorConference/investor_material_matrix.csv`。
矩陣的涵蓋範圍、日曆季度顯示與素材狀態依該文件處理；本技能提供事件日期、
來源財季與類別，不以行事曆資料列推定素材已取得。

### 來源與季度識別

- 完整涵蓋範圍由 `StockID_TWSE_TPEX.csv` 的台股來源列，以及
  `data/ConceptStocks/raw_conceptstock_company_metadata.csv` 的公司來源列分別建立。
  `StockID_TWSE_TPEX_focus.csv` 僅限制逐檔 MOPS 擷取範圍，不縮減矩陣的台股母體。
- 保留 Source、Source ID 與原始公司識別。不可合併 `2330` 與 `TSM`。
  ConceptStocks 以公司識別（CIK/Ticker）去重；MU 保留一筆公司列，並保留有效的概念成員關係。
- 依矩陣指定的年份範圍展開每年 Q1–Q4，再將已觀察素材左連接至完整範圍。
  公司數、來源列數與涵蓋年份應從當次來源及矩陣設定取得，不將文件中的統計數字寫死。
  行事曆查詢的預設日期範圍不代表歷史涵蓋範圍；沒有事件或素材的季度仍須保留。
- 事件與素材的來源會計年度／季度保留作為追溯鍵；Markdown 顯示時才正規化為日曆年度／季度。
  台股兩者一致；非台股沿用矩陣產生器的轉換方式，不以法說會舉行日期的季度直接取代財報所屬期間，
  不改寫原始 FY 標籤或素材檔名來配合顯示。
- 同日財報與法說會在行事曆仍是兩筆事件，但配對到同一來源／公司／季度的素材欄位。
  腳本衍生的美股同日法說會列與 50 天分類判斷均不能單獨證明法說會已確認或音訊已發布。
  `受邀法說` 的素材也不可直接套用例行季度法說會素材。

### 素材欄位與狀態

每季保留 `A/S/G/I/M/F/X/D` 八個欄位。每個非空儲存格須連結至已驗證素材，
或支持該狀態的行事曆／官方來源；僅有事件列、網址或檔名不等於素材已驗證。

| 標記 | 矩陣語意與判定界線 |
|---|---|
| `A` / `S` / `G` | 音訊／FIN.srt／GT.srt；各自核對實際素材，不以一般逐字稿代替 FIN 或 GT。 |
| `I` / `M` | IR 簡報 PDF／IR 簡報 Markdown；依矩陣的素材判定規則驗證。 |
| `F` / `X` | 官方財報來源（PDF 或官方 HTML）／財報 Markdown；`F` 不限於 PDF。 |
| `☐` | 事件或季度已到期，待匯入；不可因檔案不存在就直接判定到期。 |
| `?` | 事件或素材適用性尚未驗證；行事曆無事件不代表素材未發布。 |
| `🚫` | 政策明確暫停；自動補抓應遵循暫停政策，不將其當成一般待補項目。 |
| `-` | 已查核官方來源，確認未發布符合條件的文件；擷取失敗或尚未查核不足以使用此標記。 |
| 空白 | 尚未到期／尚未規劃，或素材明確不適用；不可用空白掩蓋未驗證的適用性。 |
| `D` / `D-` | 已有 digest，且 `A/S/I/M/F/X` 全部齊備／其中一項以上缺漏；digest 在 GT 之前產生，缺少 `G` 不降級為 `D-`。 |

到期與適用性依矩陣的事件／季度規則判定；即使行事曆缺少事件，已到期的財報季度仍可能是待補項目。
未來／尚未到期的事件沿用 `planned/not_due` 邊界；素材標記不直接等同 Healthy/Warning/Broken。

### 隱藏、暫停與產生方式

- 完整 CSV 保留 `visibility`、`hide_reason` 與所有來源／公司／年度／季度格位。
  Markdown 不顯示隱藏欄位，並略過 `hide_reason = all_materials_unavailable` 的資料列。
- `all_materials_unavailable` 僅在該年 32 個季度素材儲存格全空，且每季到期日均已超過
  三個日曆月時適用；門檻前的空列保留。這是可見性規則，不是查核官方來源後的 `-`。
- `paused_stock_policy` 僅套用於 2020 年至當年度，不自動暫停未來年度。
  隱藏、暫停或低優先級不代表從完整涵蓋母體永久排除。
- biztrends.TW 的 `scripts/generate_investor_material_matrix.py` 是同步入口：
  複製 InvestorConference 的正式 CSV 與 Markdown。需要更新矩陣時，先在 InvestorConference
  執行其產生器，再執行本專案同步腳本；不可手動改寫產生的矩陣或讓事件擷取腳本代替素材驗證流程。

### biztrends.TW 執行前檢查

本專案的 ConceptStocks 輸入位於 `data/ConceptStocks/`，而目前事件腳本只搜尋儲存庫根目錄
與 `../ConceptStocks/` 的同名檔案，並要求相鄰部署的
`skill-stock-fiscal-quarter-resolve/scripts/fiscal_quarter.py`。
執行前核對實際輸入路徑與此相依技能；任一缺少時，不以空美股名單或自行推算季度繼續。
可在前置條件齊備的 InvestorConference／InvestorEvents 執行事件擷取，或先在集中管理庫
修正路徑支援並部署。此對齊說明不表示目前腳本已支援 biztrends.TW 的資料布局。

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

若本次作業涉及素材矩陣，再核對：`2330` 與 `TSM` 保持分開、非台股來源 FY 鍵保留而
顯示季度依矩陣轉換、同日事件保留兩筆但不重複計算素材、未到期／未驗證／官方未發布
與政策暫停的狀態區分正確，以及缺少 GT 不會單獨將 `D` 降為 `D-`。
核對完整 CSV 的空格位與隱藏理由，不能只從 Markdown 可見列判定完整涵蓋程度。
