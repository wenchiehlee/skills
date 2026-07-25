---
name: skill-finmind-fetch
description: 從 FinMind API 獲取台灣股市個股與大盤指數的融資融券以及收盤價資料，並格式化/合併寫入與 GoodInfo 結構相同的 stage1 raw CSV 中。
---

# FinMind Fetch Skill (FinMind 資料抓取與合併技能)

此技能利用 FinMind API，獲取台灣股市個股與大盤的每日收盤價與融資融券數據。它會將獲取的資料整理為與 `raw_margin_daily.csv` (Type 13: ShowMarginChart) 相同的 31 個欄位格式，並自動與現有資料進行增量合併（Incremental Update）及去重。欄位排序與定義完全遵循 [raw_column_definition_Analyzer.md](file:///C:/Users/WJLEE/SynologyDrive/NAS/github.com/Python-Actions.GoodInfo.Analyzer/definitions/raw_column_definition_Analyzer.md) 規格。

## 適用場景

- 需要透過穩定的 API 管道（FinMind）獲取每日融資融券數據，以避開 GoodInfo 網頁強大的反爬蟲機制。
- 需要更新 `Python-Actions.GoodInfo.Analyzer` 專案中的 `data\stage1_raw\raw_margin_daily.csv`，使後續的籌碼分析管道（如 `margin_daily_report.py`）能使用最新資料。

## 依賴需求

- `pandas`
- `requests`
- `numpy`
- 建議設定環境變數 `FINMIND_TOKEN` 或 `FINMIND_API_TOKEN` 以提高每小時的 API 呼叫額度。

## 核心腳本與指令

技能的執行腳本位於技能目錄下的 `scripts/fetch_to_csv.py`。

### 1. 增量更新（推薦）

讀取現有 CSV，分析每檔股票（與大盤）在 CSV 中的最新日期，並只向 API 請求最新日期之後的資料，追加並合併寫回：

```bash
python scripts/fetch_to_csv.py --input-csv "/path/to/raw_margin_daily.csv" --stock-list "/path/to/StockID_TWSE_TPEX.csv"
```

### 2. 獲取特定範圍與股票（全量或指定更新）

```bash
python scripts/fetch_to_csv.py --stocks "0000,2330,0050" --start-date "2026-07-01" --end-date "2026-07-10" --output-csv "/path/to/output.csv"
```

## 參數說明

- `--input-csv`：現有 `raw_margin_daily.csv` 檔案的路徑。若提供此參數，程式會自動以此進行增量更新。
- `--stock-list`：包含股票代號與名稱的 CSV 路徑（格式：`代號,名稱`）。若不指定 `--stocks`，則以此列表中的股票為更新目標。
- `--stocks`：以逗號分隔的股票代碼字串（例如 `0000,2330`）。會覆蓋 `--stock-list`。大盤代碼為 `0000`。
- `--start-date`：手動指定的起始日期 (YYYY-MM-DD)。
- `--end-date`：手動指定的結束日期 (YYYY-MM-DD)，預設為今天。
- `--output-csv`：輸出的 CSV 儲存路徑，若未指定則預設覆寫 `--input-csv` 的檔案。
- `--token`：手動指定的 FinMind API Token。
- `--debug-limit`：除大盤外，限制只下載前 N 檔個股，供測試使用。
