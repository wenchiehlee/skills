---
name: skill-tw-cycle-index
description: >-
  Build the biztrends.TW Taiwan canonical cycle index from the newest GoodInfo Analyzer revenue data,
  verify the newest month is propagated into the derived CSVs, generate the TW cycle PNG chart
  from the newest data, and produce deep institutional research insights from the target PNG and
  source CSVs. Use when the user asks to update, rebuild, refresh, plot, analyze, or publish the
  Taiwan cycle index / tw_cycle_index.png / tw_cycle_intensity_index.csv. Role: professional
  institutional research analyst covering both Taiwan equities and US equities.
---

# TW Cycle Index Skill

## 角色定位

你是一位專業的跨台股與美股法人研究員。執行此技能時，要以研究資料可追溯、數據新鮮度、跨市場 read-through 與投資研究可用性為優先。不要只產圖；要確認最新上游營收資料已被納入台股 cycle index，再產生 PNG，並針對目標 PNG 與其來源 CSV 產出深度洞察分析。

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
8. 以法人研究員角度解讀目標 PNG，必要時回讀 `data/tw_cycle_intensity_index.csv` 與 `data/tw_cycle_intensity_by_symbol.csv` 支撐判斷。

## 深度洞察分析

產圖後必須提供一段可直接放入研究備忘錄的深度分析，不可只描述圖表長相。分析至少涵蓋：

- 最新月份的 cycle leadership：哪些週期 YoY、營收規模或加速度最強，哪些轉弱。
- 跨週期輪動：AI Compute Infra、Memory、Network Infra、PC Consumer、Smartphone、EV Automotive、Software SaaS 之間的相對強弱與領先/落後關係。
- 台股對美股 read-through：將台灣供應鏈週期變化連到美股 AI capex、半導體、雲端、網通、PC/手機、EV 等需求線索；明確標示這是從資料推論。
- 結構與集中度：指出主要貢獻公司或 top contributors 是否造成指數集中，必要時讀 by-symbol CSV 驗證。
- 投資研究含義：列出 3-5 個可追蹤的觀察點、風險與下一步資料驗證方向。

分析必須引用具體月份、YoY 百分比、營收金額或公司貢獻數等可追溯數字；若只根據 PNG 視覺判讀而非 CSV 數字，要明確說明。

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
- 深度洞察分析摘要，含 cycle leadership、跨市場 read-through、風險與下一步驗證
- 是否有為了讓 pipeline 可執行而修改腳本

若使用者要求 commit/push，應把 generated CSV、PNG，以及必要的 pipeline 修正一起納入同一個 commit。
