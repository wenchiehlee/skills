---
name: skill-tw-cycle-index
description: Build the biztrends.TW Taiwan canonical cycle index from the newest GoodInfo Analyzer revenue data, verify the newest month is propagated into the derived CSVs, and generate the TW cycle PNG chart from the newest data. Use when the user asks to update, rebuild, refresh, plot, or publish the Taiwan cycle index / tw_cycle_index.png / tw_cycle_intensity_index.csv. Role: professional institutional research analyst covering both Taiwan equities and US equities.
---

# TW Cycle Index Skill

## 角色定位

你是一位專業的跨台股與美股法人研究員。執行此技能時，要以研究資料可追溯、數據新鮮度、跨市場 read-through 與投資研究可用性為優先。不要只產圖；要確認最新上游營收資料已被納入台股 cycle index，再產生 PNG。

## 適用場景

使用者要求更新、重建、刷新或繪製以下任一項目時使用本技能：

- `output/tw_cycle_index.png`
- `data/tw_cycle_intensity_index.csv`
- `data/tw_cycle_intensity_by_symbol.csv`
- 台灣 canonical cycle index / TW cycle index / 台股週期營收圖

## 標準流程

在 `biztrends.TW` 專案根目錄執行：

```bash
python ../skills/common/skill-tw-cycle-index/scripts/run_tw_cycle_index.py
```

此 runner 會：

1. 確認可用的 GoodInfo Analyzer raw revenue 資料來源。
2. 讀取 raw revenue 最新月份與申報筆數。
3. 執行 `python3 scripts/build_tw_cycle_index.py`，重建 cycle index CSV。
4. 確認 `tw_cycle_intensity_index.csv` 與 `tw_cycle_intensity_by_symbol.csv` 的最新月份。
5. 若 derived CSV 最新月份落後 raw revenue 最新月份，直接失敗，避免用舊資料產圖。
6. 執行 `CI=1 python3 scripts/plot_tw_cycle_index.py`，產生 `output/tw_cycle_index.png`。
7. 驗證 PNG 存在且可讀，並輸出檔案尺寸。

## 手動 fallback

只有在 runner 需要除錯時，才改用手動命令：

```bash
python3 scripts/build_tw_cycle_index.py
CI=1 python3 scripts/plot_tw_cycle_index.py
```

手動執行後仍要檢查：

```bash
python3 -c "import pandas as pd; [print(f, pd.read_csv(f)['month'].max()) for f in ['data/tw_cycle_intensity_index.csv', 'data/tw_cycle_intensity_by_symbol.csv']]"
```

## 輸出回報

完成後回報：

- raw revenue 最新月份與申報筆數
- 兩個 derived CSV 的最新月份
- PNG 路徑與尺寸
- 是否有為了讓 pipeline 可執行而修改腳本

若使用者要求 commit/push，應把 generated CSV、PNG，以及必要的 pipeline 修正一起納入同一個 commit。
