# 五類新增事件資料流程

## 選擇產生器

以下指令一律從使用此技能的儲存庫根目錄執行。
先核對該專案的相依套件與非機密設定；AI、歷史崩盤、NVIDIA、股市事件使用
`skill-llm-api-client` 所提供的 `llm.LLMClient`。股利使用 requests、yfinance 與 python-dotenv。
財報季度解析相依僅在財報／法說會流程需要，不應強迫其他事件解析為 FY 標籤。

| 指定資料集 | 執行指令 | 主要來源與現有行為 |
|---|---|---|
| AI | `python skills/skill-stock-investorevent-fetch/scripts/fetch_ai_events.py` | LLM 產生 AI 商業／市場事件 CSV，依事件名稱與開始日期合併既有資料。 |
| 股利 | `python skills/skill-stock-investorevent-fetch/scripts/fetch_dividends_announce.py` | 台股 MOPS 董事會決議；美股 yfinance 股利資訊。重建輸出，不是歷史追加。 |
| 歷史崩盤 | `python skills/skill-stock-investorevent-fetch/scripts/fetch_historical_crashes.py` | LLM 分段產生歷史事件並去重；目前查詢期間為 1995–2010、2010–2026。 |
| NVIDIA | `python skills/skill-stock-investorevent-fetch/scripts/fetch_nvidia_events.py` | LLM 產生自 2012 年起的硬體／商業事件，依事件名稱與開始日期合併。 |
| 股市 | `python skills/skill-stock-investorevent-fetch/scripts/fetch_stock_events.py` | LLM 產生自 1990 年起的重大市場事件，依事件名稱與開始日期合併。 |

技能統一入口支援 `crashes stock ai nvidia earnings dividends`。未指定項目時更新全部六份；
指定項目時僅載入對應產生器。InvestorEvents 根目錄入口只為既有呼叫提供相容委派。

```bash
python skills/skill-stock-investorevent-fetch/scripts/fetch_all_events.py
python skills/skill-stock-investorevent-fetch/scripts/fetch_all_events.py ai dividends
```

各產生器的時間範圍不同；財報的 `--start` / `--end` 不套用至其餘五類事件。
歷史崩盤的既有範圍也不等於完整歷史。需要改變範圍時先調整對應產生器，
不得在回報中聲稱涵蓋未查詢的年份。

## 事件、日期與來源語意

- 保留各 CSV 自己的類別／子類別；財報的 `財報` / `法說會` / `受邀法說`
  三類限制不適用於 AI、股利、崩盤、NVIDIA 或一般股市事件。
- 事件開始／結束日期是實際事件期間。只有已確認屬於季度財報公告的事件才呼叫
  `skill-stock-fiscal-quarter-resolve`；市場危機、產品發布、除息日或董事會日期不可用來推算財季。
- LLM 回應是待驗證事件候選；逐筆核對日期、事件內容與 Link1／Link2 所支持的主張。
  優先官方來源，保留可信報導的來源連結；產生成功不等於來源或價格影響已查證。
  未確認的影響敘述不作為正式市場事實。跨 CSV 的同一事件保留資料集來源，
  不因 AI 與 NVIDIA 同時涵蓋該事件，就跨檔刪除其中一筆。
- 股利產生器目前以 yfinance `Ex-Dividend Date` 作為美股日期；這是除息日，
  不是公司宣告日。`dividendRate` 也不能直接當成單次派息金額。
  不將這些列描述成已確認的宣告日期／單次金額；需要精確宣告資料時，以公司正式公告核對，
  並在來源產生器修正語意，不在下游 CSV 手動替換。
- 股利產生器的「尚未公告股息」列是查詢狀態，不是真實股利宣告事件。
  擷取失敗或未取得資料不能證明公司沒有公告；今日填入的日期不是宣告日期。
  展示或統計時與實際股利事件分開，不以這些列填補素材矩陣。
- 五類事件作為市場／公司背景資料，不直接建立 `A/S/G/I/M/F/X/D` 素材完成標記，
  不改變矩陣的到期、隱藏或暫停規則。

## 輸出驗證與回報

### 與 skill-stock-topcrash 對齊

`raw_event_historical_crashes.csv` 提供事件名稱與開始／結束日期的背景標籤；
價格資料是否符合崩盤門檻及其排名，由 `skill-stock-topcrash` 判定。
在需要崩盤 Top N 分析時使用該技能，不以 LLM 事件清單當成已驗證的價格排名。

- topcrash 比較 1/3/5/7/9/11 個交易日報酬，取最小值排序；預設最壞跌幅須低於 -3%。
  直接呼叫其 `run_topcrash.py`，不在本技能複製偵測、VIX 分級或恢復算法。
- `--named-events-json` 優先，其次依 CSV 日期窗口包含最壞日期來配對；
  多筆 CSV 同日命中取最短窗口，未命中為「其他」。事件配對表示時間重疊，不能單獨證明因果。
- CSV 的 `事件名稱,開始日期,結束日期` 必須完整且為有效日期，結束日不得早於開始日。
  同日起始的不同事件、同名但不同窗口均保留；僅合併同名且相同起訖的重複資料。
  跨次產生的名稱／窗口差異須查證，不能靠任意擴大窗口吸收更多跌幅。
- topcrash 的排名去重另有規則：具名事件只取最壞一筆；「其他」依日期間隔
  （預設 10 個日曆天）去重。這不代表來源事件 CSV 也應只留同日一筆。
- 最壞日期不是事件開始日，事件結束日也不是恢復日。恢復參考是崩盤前預設
  120 個日曆天內最高收盤價；恢復天數 ≤45 為 V，否則為 U，資料範圍內未恢復另列。
  VIX/CNN 需另供對應 CSV，未提供時不產生該組欄位。
- 事件 CSV 保持原有十欄；排名 CSV 另存，不能覆寫來源事件 CSV，
  也不以排名日期取代來源事件期間。市場／symbol、查詢期間、門檻與資料限制須在分析回報中保留。

從已部署 topcrash 的使用端根目錄執行，例如：

```bash
python skills/skill-stock-topcrash/scripts/run_topcrash.py \
  --symbol '^TWII' --years 10 --top-n 50 --min-drop -3.0 \
  --events-csv raw_event_historical_crashes.csv \
  --output output/crash_top50.csv
```

biztrends.TW 的同步來源路徑則為 `data/InvestorEvents/raw_event_historical_crashes.csv`。
topcrash 是獨立的可選分析相依，未部署時仍可擷取事件，但不能聲稱已完成跌幅偵測／排名。

共同核心欄位為 `類別,子類別,事件名稱,開始日期,結束日期,備註,Link1,Link2`。
AI、歷史崩盤、NVIDIA 與股市檔案另有 `download_timestamp,process_timestamp`；
現有股利產生器只有八個核心欄位，不宣稱它已具備時間戳。

執行前後核對 CSV 可解析、日期格式為 YYYY-MM-DD、結束日不早於開始日、
必需欄位與來源連結有效，並檢查各資料集的重複鍵與輸出筆數。
保留既有已驗證資料；股利檔案重建前留可還原副本，避免抓取失敗覆蓋有效資料。

部分產生器會捕捉例外後只印出錯誤，仍以成功狀態結束；不能只看退出碼。
檢查標準輸出、實際寫檔結果與來源驗證結果，分別回報更新、無新事件、失敗或未執行。
既有腳本會重寫部分舊列的時間戳，時間戳變新不代表歷史事件重新驗證，
也不代表事件發生日期改變。不要把這些時間戳當成來源證據的新鮮度。
