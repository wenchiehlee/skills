---
name: skill-company-cycle-index
description: >-
  Build company canonical cycle indexes by applying active company revenue segment weights to market revenue data.
  Current implementation supports the biztrends.TW Taiwan cycle index: read refreshed Taiwan segment weights,
  verify the newest GoodInfo Analyzer month is propagated into derived CSVs, generate the TW cycle PNG chart,
  and write deep cross-market research insights. Use when the user asks to update, rebuild, refresh, plot,
  analyze, or publish company cycle index outputs such as company_cycle_index_taiwan.png / company_cycle_intensity_taiwan.csv.
  Role: professional institutional research analyst covering both Taiwan equities and US equities.
---

# Company Cycle Index Skill

## 角色定位

你是一位專業的跨台股與美股研究員。執行此技能時，要以研究資料可追溯、數據新鮮度、segment weights 使用狀態、跨市場 read-through 與投資研究可用性為優先。此 skill 的責任是「套用」已審核的 company revenue segment weights 到 canonical cycle model，產生 cycle mapping、allocation audit、cycle index、PNG 與 README insights；不負責抽取或審核原始 segment weight evidence。目前實作路徑支援 TW：要確認最新 GoodInfo 月營收資料與 `data/company_segment_weights.csv` 已被納入台股 cycle index，再產生 PNG。

## 適用場景

使用者要求更新、重建、刷新或繪製 company/canonical cycle index 時使用本技能。目前支援 TW 產出：

- `output/company_cycle_index_taiwan.png`
- `data/company_cycle_intensity_taiwan.csv`
- `data/company_cycle_intensity_by_symbol_taiwan.csv`
- 台灣 canonical cycle index / TW cycle index / 台股週期營收圖

## 標準流程

在 `biztrends.TW` 專案根目錄執行：

```bash
python ../skills/common/skill-company-cycle-index/scripts/run_company_cycle_index.py
```

此 runner 是目前的 TW implementation。它會：

1. 確認可用的 GoodInfo Analyzer raw revenue 資料來源。
2. 讀取 raw revenue 最新月份與申報筆數。
3. 檢查 `data/company_segment_weights.csv` 存在、欄位完整且有可用 rows，並回報使用的 weighted company 數、segment row 數與最新 `source_period`。
4. 執行 `python3 scripts/build_tw_cycle_index.py`，重建 cycle index CSV；builder 會透過 `load_segment_weights()` 讀取 `data/company_segment_weights.csv`，再用 `data/segment_to_cycle_mapping.csv` 將公司分項營收權重分配到 canonical cycles。
5. 確認 `company_cycle_mapping.csv` 的 `segment_weight_override=Y` 與 `data/company_major_cycle_weights.csv` 有輸出，確保 segment weights 真的進入 cycle allocation，而不是只使用單一公司 cycle 分類。
6. 確認 `company_cycle_intensity_taiwan.csv` 與 `company_cycle_intensity_by_symbol_taiwan.csv` 的最新月份。
7. 若 derived CSV 最新月份落後 raw revenue 最新月份，直接失敗，避免用舊資料產圖。
8. 執行 `CI=1 python3 scripts/plot_tw_cycle_index.py`，產生 `output/company_cycle_index_taiwan.png`。
9. 驗證 PNG 存在且可讀，並輸出檔案尺寸。
10. 以專業研究員角度解讀目標 PNG，必要時回讀 `data/company_cycle_intensity_taiwan.csv`、`data/company_cycle_intensity_by_symbol_taiwan.csv`、`data/company_major_cycle_weights.csv` 支撐判斷。
11. 更新 `README.md` 的台灣 cycle index 區塊，將產出指令改為 skill runner，並寫入 timestamp 與深度洞察分析。

## 深度洞察分析

產圖後必須提供一段可直接放入研究備忘錄的深度分析，不可只描述圖表長相。可用 Malta Business School 對 Introduction / Growth / Maturity / Decline 的產業生命週期定義作為背景框架（https://mbs.edu.mt/knowledge/empowerment-through-knowledgeno-25-industry-life-cycle/），但 README 呈現必須是高階策略描述，不是生命週期明細表。分析至少涵蓋：

- 產出高階策略敘述，不輸出逐 cycle 明細表或生命週期操作欄位。
- 用 3-5 段研究備忘錄式文字說明目前台灣 cycle index 的市場含義：主線、輪動、擴散、集中度與風險。
- 最新月份的 cycle leadership：哪些週期 YoY、營收規模或加速度最強，哪些轉弱，並引用可追溯數字。
- 跨週期輪動：AI Compute Infra、Memory、Network Infra、PC Consumer、Smartphone、EV Automotive、Software SaaS 之間的相對強弱與領先/落後關係。
- 台股對美股 read-through：將台灣供應鏈週期變化連到美股 AI capex、半導體、雲端、網通、PC/手機、EV 等需求線索；明確標示這是從資料推論。
- 結構與集中度：指出主要貢獻公司或 top contributors 是否造成指數集中，必要時讀 by-symbol CSV 驗證。
- 資料解讀 QA：在提出策略結論前，先檢查資料缺口與可能誤讀，包括 `data/company_segment_weights.csv` 覆蓋率、`segment_weight_override=Y` 公司數、分類覆蓋率、混合營收公司、權重來源信心、YoY 極端值、YoY 斜率突變、Top contributors 集中度與 `Other` 占比；若任何一項可能影響結論，README 必須主動寫成 caveat。
- 異常與非預期資料提醒：主動標示 YoY 過高、YoY 斜率突變、單一或少數公司貢獻過度集中、或 `Other` 類別扭曲總指數的情況，並說明需回查一次性因素、分類權重或原始營收來源。特別注意 `AI_Compute_Infra` 是 AI/data center exposure proxy，不代表成分公司只做 AI server；同一家公司可能同時有 AI server、data center、PC、手機、消費或其他營收。AI server / data server / PC 的拆分依賴 investor conference、法說會、年報或公司揭露輸入；若公司缺漏揭露、口徑不同或只提供合併分類，分類結果應標示為加權研究推估，而非完整官方分項或純 AI server 營收。
- 投資研究含義：列出可追蹤的觀察點、風險與下一步資料驗證方向。

分析必須引用具體月份、YoY 百分比、營收金額或公司貢獻數等可追溯數字；README 呈現應是策略解讀，不是流程表、生命週期明細表或操作明細。若資料看起來異常、分類資料可能缺漏，或解讀容易被混合營收誤導，必須明確寫成研究提醒，而不是直接把異常值或分類 proxy 當成可外推趨勢。若只根據 PNG 視覺判讀而非 CSV 數字，要明確說明。

## 手動 fallback

只有在 runner 需要除錯時，才改用手動命令：

```bash
python3 scripts/build_tw_cycle_index.py
CI=1 python3 scripts/plot_tw_cycle_index.py
```

手動執行後仍要檢查：

```bash
python3 -c "import pandas as pd; [print(f, pd.read_csv(f)['month'].max()) for f in ['data/company_cycle_intensity_taiwan.csv', 'data/company_cycle_intensity_by_symbol_taiwan.csv']]"
```

## 輸出回報

完成後回報：

- raw revenue 最新月份與申報筆數
- `data/company_segment_weights.csv` weighted company 數、segment row 數與最新 `source_period`
- `company_cycle_mapping.csv` 中 `segment_weight_override=Y` 公司數，以及 `data/company_major_cycle_weights.csv` row 數
- 兩個 derived CSV 的最新月份
- PNG 路徑與尺寸
- `README.md` 是否已寫入 skill runner 產出指令、timestamp 與深度洞察分析
- 深度洞察分析摘要，含 cycle leadership、跨市場 read-through、風險與下一步驗證
- 是否有為了讓 pipeline 可執行而修改腳本

## Skill 邊界

- 本 skill 產生 cycle model/output 層：`data/company_cycle_mapping.csv`、`data/company_major_cycle_weights.csv`、`data/company_cycle_intensity_taiwan.csv`、`data/company_cycle_intensity_by_symbol_taiwan.csv`、`output/company_cycle_index_taiwan.png` 與 README insights。
- 本 skill 只消費已審核的 `data/company_segment_weights.csv`；不抽取 InvestorConference/IR/年報/MOPS evidence，也不產生 segment weight candidates 或 QA report。
- segment weight evidence、candidate、QA 與正式 active snapshot 的維護屬於 `skill-company-revenue-segment-weights`。

若使用者要求 commit/push，應把 generated CSV、PNG，以及必要的 pipeline 修正一起納入同一個 commit。
