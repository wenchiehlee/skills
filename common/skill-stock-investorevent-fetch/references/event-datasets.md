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
