---
name: skill-company-cycle-index
description: >-
  Build company canonical cycle indexes by applying active company revenue segment weights to market revenue data.
  Current implementation supports Taiwan and United States company cycle indexes: read refreshed segment weights,
  verify the newest market revenue / quarterly segment data is propagated into derived CSVs, generate the market PNG chart,
  and write cross-market research insights. Use when the user asks to update, rebuild, refresh, plot,
  analyze, or publish company cycle index outputs such as company_cycle_index_taiwan.png,
  company_cycle_index_united_states.png, company_cycle_intensity_taiwan.csv, or company_cycle_intensity_united_states.csv.
  Role: professional institutional research analyst covering both Taiwan equities and US equities.
---

# Company Cycle Index Skill

## 角色定位

你是一位專業的跨台股與美股研究員。執行此技能時，要以研究資料可追溯、數據新鮮度、segment weights 使用狀態、跨市場 read-through 與投資研究可用性為優先。此 skill 的責任是「套用」已審核的 company revenue segment weights 到 canonical cycle model，產生 cycle mapping、allocation audit、cycle index、PNG 與 README insights；不負責抽取或審核原始 segment weight evidence。目前實作路徑支援 Taiwan 與 United_States：Taiwan 要確認最新 GoodInfo 月營收資料與 `data/company_segment_weights.csv` 已被納入台股 cycle index；United_States 要確認 ConceptStocks quarterly segment revenue 已轉成 `market=United_States` segment weights，並產生 `output/company_cycle_index_united_states.png`。因 segment weights 本質上會隨季度變動，cycle intensity 必須按 revenue month 選用當季或最近已揭露的過去權重；若早期沒有季度歷史，使用最早 snapshot 回填只為了維持歷史 level 連續，結果仍只能視為 exposure proxy。若只有 single snapshot 或缺季度歷史，README insights 必須明確標示問號與研究 caveat。

## 適用場景

使用者要求更新、重建、刷新或繪製 company/canonical cycle index 時使用本技能。目前支援 Taiwan 與 United_States 產出：

- `output/company_cycle_index_taiwan.png`
- `output/company_cycle_intensity_taiwan.csv`
- `output/company_cycle_intensity_by_symbol_taiwan.csv`
- `output/company_cycle_index_united_states.png`
- `output/company_cycle_intensity_united_states.csv`
- `output/company_cycle_intensity_by_symbol_united_states.csv`
- `output/company_cycle_demand_pull_united_states.csv`
- 台灣 canonical cycle index / TW cycle index / 台股週期營收圖
- 美股 canonical cycle index / US cycle index / 美股 quarterly segment revenue 週期圖

## 標準流程

在 `biztrends.TW` 專案根目錄執行：

```bash
# Taiwan monthly revenue cycle index
python skills/skill-company-cycle-index/scripts/run_company_cycle_index.py --market taiwan

# United States quarterly segment revenue cycle index
python skills/skill-company-cycle-index/scripts/run_company_cycle_index.py --market united_states

# Run both markets
python skills/skill-company-cycle-index/scripts/run_company_cycle_index.py --market all
```

`--market taiwan` 會：

1. 確認可用的 GoodInfo Analyzer raw revenue 資料來源。
2. 讀取 raw revenue 最新月份與申報筆數。
3. 檢查 `data/company_segment_weights.csv` 存在、欄位完整且有可用 `market=Taiwan` rows，並回報台灣 weighted company 數、segment row 數與最新 `source_period`。
4. 執行 `python3 scripts/build_company_cycle_index_taiwan.py`，重建 cycle index CSV；builder 會透過 `load_segment_weights()` 讀取 `data/company_segment_weights.csv`，按 `stock_code + source_period` 保留季度/年度/月度權重，再用 `data/segment_to_cycle_mapping.csv` 將公司分項營收權重分配到 canonical cycles。月營收 allocation 優先使用當季或最近過去可得權重；若早期月份沒有過去可得權重，為避免 100% fallback cycle 切換成 segment weights 造成假斷崖，會使用最早可得 snapshot 作為歷史 proxy。README 必須把 single snapshot proxy 風險寫成 caveat，並用 `segment_source_periods` / `yoy_data_quality` 標示可比性。
5. 確認 `company_cycle_mapping.csv` 的 `segment_weight_override=Y` 與 `output/company_cycle_major_weights.csv` 有輸出，確保 segment weights 真的進入 cycle allocation，而不是只使用單一公司 cycle 分類。
6. 確認 `company_cycle_intensity_taiwan.csv` 與 `company_cycle_intensity_by_symbol_taiwan.csv` 的最新月份。
7. 若 derived CSV 最新月份落後 raw revenue 最新月份，直接失敗，避免用舊資料產圖。
8. 執行 `CI=1 python3 scripts/plot_company_cycle_index_taiwan.py`，產生 `output/company_cycle_index_taiwan.png`。
9. 驗證 PNG 存在且可讀，並輸出檔案尺寸。
10. 以專業研究員角度解讀目標 PNG，必要時回讀 `output/company_cycle_intensity_taiwan.csv`、`output/company_cycle_intensity_by_symbol_taiwan.csv`、`output/company_cycle_major_weights.csv` 支撐判斷。
11. 更新 `README.md` 的台灣 cycle index 區塊，將產出指令改為 skill runner，並寫入 timestamp 與深度洞察分析。

`--market united_states` 會：

1. 讀取 ConceptStocks quarterly segment revenue：可讀取相鄰 `../ConceptStocks/raw_conceptstock_company_quarterly_segments.csv` 與 repo 內 `data/ConceptStocks/raw_conceptstock_company_quarterly_segments.csv`，但若同一 `symbol / fiscal_year / quarter / segment_name` 在兩邊都存在，必須以 repo 內 `data/ConceptStocks` 為準；US segment candidates 與 active snapshot 的 `source_period` 一律使用 fiscal period（例如 `2026-Q2`），不得以 `end_date` 轉成 calendar quarter，以免 ORCL、WDC 等非 12 月年結公司被錯置。
2. 若 TSM 某些季度沒有 auto-parsed segment rows，才使用 `data/company_platform_revenue.csv` × ConceptStocks income revenue 做 platform fallback；TSM 不再視為獨立特例，而是 US segment revenue coverage 的 fallback source。
3. 執行 `scripts/build_company_cycle_index_united_states.py`，同時產生：
   - `output/company_cycle_intensity_united_states.csv`
   - `output/company_cycle_intensity_by_symbol_united_states.csv`
   - `output/company_cycle_demand_pull_united_states.csv`
4. 將每個 US symbol 的最新完整季度 segment revenue mix 寫回 `data/company_segment_weights.csv` 的 `market=United_States` rows；`source_period` 必須是最新 fiscal period，`Source (link)` 必須回溯到 ConceptStocks segment CSV 或 TSM fallback source。若公司揭露同一 quarter 同時包含 broad segment 與其子拆分，必須避免 double count；目前 ORCL 若有 broad `Cloud` 或 `Cloud services and license support`，則 `Cloud Applications` / `Oracle Cloud Infrastructure` 只能作 evidence，不得同時計入同一 quarter segment mix。
5. 若某個 US symbol 的某一 fiscal period 完全沒有 segment rows，使用該公司最新 segment mix × quarterly total revenue 補齊 cycle index，並在 derived CSV 的 `segment_source_summary` 標示 `latest_mix_proxy`；不得覆蓋已有 official segment revenue rows。
6. 驗證 `data/company_segment_weights.csv` 有可用 `United_States` rows，並回報 stock count、segment row count 與最新 `source_period`。
7. 驗證三個 US derived CSV 的最新 `period` 與 row count。
8. 執行 `CI=1 python3 scripts/plot_company_cycle_index_united_states.py`，產生 `output/company_cycle_index_united_states.png`；PNG 應使用與 Taiwan 相同的 canonical terms，例如 `AI_Server_Rack`、`AI_Foundry_Packaging`、`AI_Network_Infra`、`AI_Accelerator`、`AI_Memory_HBM`、`Memory_Commodity`、`Cloud_AI_Compute`。
9. PNG 只繪製最新季度仍有資料且近 30 季覆蓋達最低門檻的 cycles；過度稀疏或已停止更新的 cycle 可留在 CSV audit，但不應放入主 PNG 造成缺季度誤讀。
10. 驗證 PNG 存在且可讀，並更新 `README.md` 的 US cycle index 產出指令與 timestamp。

US segment candidate HTML (`output/company_segment_weights_quarterly_candidates_united_states.html`) 必須遵守同一口徑：

- Quarter 欄顯示 fiscal period，不使用 calendar quarter。
- 同一 `symbol / fiscal_year / quarter / segment_name` 以 repo 內 `data/ConceptStocks` row 優先，避免 sibling repo 舊 row 與本 repo 新 row double count。
- ORCL 必須先做跨期 segment taxonomy 正規化：`Cloud services and license support` 併入 `Cloud`，`Cloud license and on-premise license` 併入 `Software`，讓 2025 前後的 segment mix 可以用同一組名稱比較。
- ORCL 的 broad `Cloud` 與 `Cloud Applications` / `Oracle Cloud Infrastructure` 不可在同一 period 同時計入 revenue mix；若 broad row 存在，子拆分只作回溯 evidence，不納入 bar 或 total segment revenue。
- 若某公司歷史上是多 segment disclosure，但某一 fiscal period 只剩單一 segment row，必須視為 incomplete extraction，不能把該單一 segment 正規化成 100% mix；例如 HPE 2026-Q1 / 2026-Q2 只有 `Networking` row 時，不應輸出成完整 company segment mix。
- `Evidence rows / source backtrace` 必須保留 source CSV，方便回查是哪一份 ConceptStocks CSV。

## 深度洞察分析

產圖後必須提供一段可直接放入研究備忘錄的深度分析，不可只描述圖表長相。可用 Malta Business School 對 Introduction / Growth / Maturity / Decline 的產業生命週期定義作為背景框架（https://mbs.edu.mt/knowledge/empowerment-through-knowledgeno-25-industry-life-cycle/），但 README 呈現必須是高階策略描述，不是生命週期明細表。分析至少涵蓋：

- 產出高階策略敘述，不輸出逐 cycle 明細表或生命週期操作欄位。
- 用 3-5 段研究備忘錄式文字說明目前台灣 cycle index 的市場含義：主線、輪動、擴散、集中度與風險。
- 最新月份的 cycle leadership：哪些週期 YoY、營收規模或加速度最強，哪些轉弱，並引用可追溯數字。
- 跨週期輪動：AI Server Rack、AI Foundry Packaging、AI Network Infra、Memory、Network Infra、PC Consumer、Smartphone、EV Automotive、Software SaaS 之間的相對強弱與領先/落後關係。
- 台股對美股 read-through：將台灣供應鏈週期變化連到美股 AI capex、半導體、雲端、網通、PC/手機、EV 等需求線索；明確標示這是從資料推論。
- 結構與集中度：指出主要貢獻公司或 top contributors 是否造成指數集中，必要時讀 by-symbol CSV 驗證。
- 資料解讀 QA：在提出策略結論前，先檢查資料缺口與可能誤讀，包括 `data/company_segment_weights.csv` 覆蓋率、`segment_weight_override=Y` 公司數、分類覆蓋率、混合營收公司、權重來源信心、single snapshot 公司數、是否具備季度權重歷史、YoY 權重口徑是否可比、YoY 極端值、YoY 斜率突變、Top contributors 集中度與 `Other` 占比；若任何一項可能影響結論，README 必須主動寫成 caveat。
- 異常與非預期資料提醒：主動標示 YoY 過高、YoY 斜率突變、單一或少數公司貢獻過度集中、或 `Other` 類別扭曲總指數的情況，並說明需回查一次性因素、分類權重或原始營收來源。特別注意 `AI_Server_Rack` 是 AI/data center exposure proxy 的一個子分類，`AI_Foundry_Packaging` 與 `AI_Network_Infra` 需分開判讀；同一家公司可能同時有 AI server、data center、PC、手機、消費或其他營收。AI server / data server / PC 的拆分依賴 investor conference、法說會、年報或公司揭露輸入；若公司缺漏揭露、口徑不同或只提供合併分類，分類結果應標示為加權研究推估，而非完整官方分項或純 AI server 營收。
- 投資研究含義：列出可追蹤的觀察點、風險與下一步資料驗證方向。

分析必須引用具體月份、YoY 百分比、營收金額或公司貢獻數等可追溯數字；README 呈現應是策略解讀，不是流程表、生命週期明細表或操作明細。若資料看起來異常、分類資料可能缺漏，或解讀容易被混合營收誤導，必須明確寫成研究提醒，而不是直接把異常值或分類 proxy 當成可外推趨勢。若只根據 PNG 視覺判讀而非 CSV 數字，要明確說明。

## 手動 fallback

只有在 runner 需要除錯時，才改用手動命令：

```bash
python3 scripts/build_company_cycle_index_taiwan.py
CI=1 python3 scripts/plot_company_cycle_index_taiwan.py

python3 scripts/build_company_cycle_index_united_states.py
CI=1 python3 scripts/plot_company_cycle_index_united_states.py
```

手動執行後仍要檢查：

```bash
python3 -c "import pandas as pd; [print(f, pd.read_csv(f)['month'].max()) for f in ['output/company_cycle_intensity_taiwan.csv', 'output/company_cycle_intensity_by_symbol_taiwan.csv']]"
```

## 輸出回報

完成後回報：

- raw revenue 最新月份與申報筆數
- `data/company_segment_weights.csv` 中目標市場 weighted company 數、segment row 數與最新 `source_period`
- `company_cycle_mapping.csv` 中 `segment_weight_override=Y` 公司數，以及 `output/company_cycle_major_weights.csv` row 數
- 兩個 derived CSV 的最新月份
- PNG 路徑與尺寸
- `README.md` 是否已寫入 skill runner 產出指令、timestamp 與深度洞察分析
- 深度洞察分析摘要，含 cycle leadership、跨市場 read-through、風險與下一步驗證
- 是否有為了讓 pipeline 可執行而修改腳本

## Skill 邊界

- 本 skill 產生 cycle model/output 層：Taiwan 的 `output/company_cycle_mapping.csv`、`output/company_cycle_major_weights.csv`、`output/company_cycle_intensity_taiwan.csv`、`output/company_cycle_intensity_by_symbol_taiwan.csv`、`output/company_cycle_index_taiwan.png`，以及 United_States 的 `output/company_cycle_intensity_united_states.csv`、`output/company_cycle_intensity_by_symbol_united_states.csv`、`output/company_cycle_demand_pull_united_states.csv`、`output/company_cycle_index_united_states.png` 與 README timestamp/insights。
- 本 skill 消費已審核或已結構化的 segment weights/revenue source：Taiwan 消費 `data/company_segment_weights.csv` 與 `data/segment_to_cycle_mapping.csv`；United_States 消費 ConceptStocks quarterly segment revenue 與 `data/cycle_mapping.csv`，並把最新 US segment mix 回寫到 `data/company_segment_weights.csv` 作為 active snapshot。
- 本 skill 不抽取 InvestorConference/IR/年報/MOPS evidence，也不產生 Taiwan segment weight candidates 或 QA report；這些 evidence、candidate、QA 與正式 active snapshot 的維護屬於 `skill-company-revenue-segment-weights`。

若使用者要求 commit/push，應把 generated CSV、PNG，以及必要的 pipeline 修正一起納入同一個 commit。
