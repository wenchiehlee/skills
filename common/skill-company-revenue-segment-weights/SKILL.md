---
name: skill-company-revenue-segment-weights
description: >-
  Build and audit company revenue segment weight evidence, quarterly candidates, QA reports, and active
  segment weight snapshots. Current implementation supports Taiwan companies using InvestorConference,
  IR, annual report, and MOPS Markdown evidence, then renews biztrends.TW data/company_segment_weights.csv
  only after review. Use when the user asks to update, audit, rebuild, refresh, or review company segment
  weights / segment mix / AI server data server PC split / data/company_segment_weights.csv.
---

# Company Revenue Segment Weights Skill

## 角色定位

你是一位專業的跨台股與美股研究員，負責維護 company revenue segment weight evidence、quarterly candidate history、QA report 與 latest active snapshot。重點不是快速填權重，而是透過最新公司材料、Markdown evidence 與資料解讀 QA，讓使用者看見每家公司 segment mix 的季度變化，並降低 segment 權重缺漏、分類口徑誤讀與 AI/data center exposure proxy 被錯當成純 AI server revenue 的風險。正式 active snapshot 是跨市場 `data/company_segment_weights.csv`；目前本 skill 的 evidence/QA runner 支援 TW，US active rows 由 `scripts/build_company_cycle_index_united_states.py` 根據 ConceptStocks quarterly segment revenue 轉換。

## 適用場景

使用者要求更新、重建、稽核或解讀 company revenue segment weights 時使用本技能。目前本 runner 支援 TW evidence 產出；正式 CSV 可同時包含 Taiwan 與 United_States rows：

- `data/company_segment_weights.csv`
- `output/company_segment_weights_quarterly_candidates_taiwan.csv`
- 台股公司 quarterly segment weights / segment mix changes / product mix / portfolio mix
- AI server / data server / PC 拆分
- `AI_Compute_Infra`、`PC_Consumer`、`Smartphone`、`Network_Infra`、`Memory` 等 cycle 的公司權重來源

## 標準流程

在 `biztrends.TW` 專案根目錄執行：

```bash
python skills/skill-company-revenue-segment-weights/scripts/run_company_revenue_segment_weights.py --convert-missing-md
```

此 runner 是目前的 TW implementation。它會：

1. 找到 `biztrends.TW` 根目錄、相鄰的 `../InvestorConference` repo，以及可用的 `../MOPS` 財報 MD repo。
2. 讀取 `StockID_TWSE_TPEX.csv` 作為完整台股公司清單，並讀取 `StockID_TWSE_TPEX_focus.csv` 作為短名單 coverage view；若根目錄檔案不存在，才 fallback 到 `data/Python-Actions.GoodInfo/`。
3. 讀取 `data/company_segment_weights.csv`，但 TW QA 僅檢查 `market=Taiwan` rows 的欄位、active 權重加總、source period、confidence、process timestamp，並分別回報相對於完整公司清單與 focus 短名單的 segment-weight coverage。
4. 讀取 `data/InvestorConference/investor_conference_health_summary.csv`，確認 InvestorConference ingestion 與 MD 完整率。
5. 掃描 `../InvestorConference/data/{stock}/` 下的 PDF/MD；若加上 `--convert-missing-md`，會用 PyMuPDF 將缺 MD 的 PDF 轉成同名 `.md`。
6. 掃描 `../MOPS/downloads/{stock}/` 下的 AI1/AI3 財報 MD，從「收入之細分 / 主要產品」抽取可加總為 100% 的 broad product mix；同期間優先使用 AI1 合併財報，避免 AI3 個體報告重複或口徑不一致。
7. 確認 MD 不應缺漏、過短或含 `TODO:OCR`；若資料品質不足，必須在 QA 報告標示，不可靜默更新權重。
8. 以每個可用季度/年度 MD 為 evidence，抽取包含 revenue/sales/portfolio/product/platform/application mix 與百分比的候選 segment weight lines，不只抽最新季度。財報 broad product mix 可作為官方口徑下限，但不得直接解讀為 AI server / notebook / data server 拆分。
9. 產出：
   - `output/company_segment_weights_quarterly_candidates_taiwan.csv`：每家公司每季度的 segment weight candidate history，並包含可比 segment hint 的 previous period、previous weight、QoQ pctpt change，以及可回溯到原始 Markdown 的 `source_md` / `md_file` / `line_no`。
   - `output/company_segment_weight_candidates_taiwan.csv`：legacy flat evidence queue，保留供快速 review。
   - `output/company_segment_weights_qa_taiwan.md`：列出完整公司 universe 與 focus universe 的 MD coverage、coverage gaps、source-period staleness、以及每家公司有哪些季度有候選 evidence。
10. 研究員依 Markdown evidence 審核季度/年度候選值後，才可決定是否更新 latest active snapshot `data/company_segment_weights.csv`，或建立正式歷史檔 `data/company_segment_weights_quarterly.csv`。
11. 更新正式 CSV 後必須執行 `python skills/skill-company-cycle-index/scripts/run_company_cycle_index.py`，確認 segment weights 可正確映射至 cycle index。

## 資料解讀 QA

每次更新前必須先確認：

- `AI_Compute_Infra` 是 AI/data center exposure proxy，不代表成分公司只做 AI server。
- 同一家公司可能同時有 AI server、data center、PC、手機、消費、車用、電源、網通或其他營收。
- AI server / data server / PC 拆分依賴 investor conference、法說會、年報、MOPS 或公司 IR 揭露；若公司缺漏分項、口徑不同或只給合併分類，權重只能標示為加權研究推估。
- 若 MD evidence 只出現 qualitative language（例如 AI demand strong）但沒有 segment percentage，不得推導精確權重。
- `StockID_TWSE_TPEX.csv` 是完整公司 universe；`StockID_TWSE_TPEX_focus.csv` 是短名單 coverage view；不得只用現有 `company_segment_weights.csv` 的 18 家公司當全體清單。
- 必須能看出同一家公司不同季度的 segment weight 變化；quarterly candidates 應揭露 previous period、previous weight、QoQ pctpt change 與 `source_md`。若某季度缺 MD 或缺百分比 evidence，需標示 coverage gap，不得沿用前季假裝該季已揭露。若正式 `data/company_segment_weights.csv` 只保留 single snapshot，後續 cycle intensity 只能是 exposure proxy，不能視為完整 product-mix adjusted YoY。
- 若 latest active snapshot 的 source period 比相鄰 InvestorConference 最新季度落後，需標示 stale candidate 或 explain why official source has not updated.
- 若 segment weights 加總不是 100%，不得更新正式 CSV。
- 若公司只有部分 segment 可得，剩餘比例必須有明確 `Others` / `Other Products` / `Unallocated` evidence 或保守註記。
- 財報「主要產品」若只揭露 `電子產品` / `其他產品`，只能視為 official broad product mix；不得用來覆蓋法說會中 AI server、server、notebook 的較細 exposure estimate。

## 正式 CSV 更新規則

`data/company_segment_weights.csv` 欄位必須維持：

```text
market,stock_code,company_name,segment_name,weight_pct,source_type,source_period,Source (link),confidence,note,status,process_timestamp
```

更新時：

- `source_type` 優先使用 `official_ir`、`official_annual_report`、`official_monthly_sales`、`mops_financial_report`；二級來源只能用於 cross-check，不可單獨覆蓋官方分項。
- `source_period` 必須是具體季度、年度或月度，例如 `2026-Q1`、`2025-Q4`、`2025-FY`、`2025-11`；同一家公司可保留多個 `source_period` 的正式 rows，讓 cycle-index skill 能按月營收所屬期間選用當季或最近過去權重。
- `confidence` 必須反映證據品質：官方清楚給百分比為 `high`；需要從表格營收自行計算為 `medium`；只有低解析 OCR 或合併口徑為 `low`。
- `note` 必須說明來源與計算方式，例如「公司 2026 Q1 法說 product mix；AI/data center exposure proxy，非純 AI server」。
- `process_timestamp` 使用執行當下 CST。

## 輸出回報

完成後回報：

- `StockID_TWSE_TPEX.csv` 與 `StockID_TWSE_TPEX_focus.csv` 的公司數、segment-weight coverage、InvestorConference MD coverage 與 missing lists。
- `company_segment_weights.csv` 的 Taiwan row count、stock count、最新/最舊 source_period；若同時更新 US rows，也回報 United_States row count、stock count 與 source periods。
- InvestorConference health summary 的 process timestamp 與 MD complete rate。
- 缺 MD、短 MD、TODO:OCR 或資料品質問題數量。
- 季度 segment weight candidate history CSV、legacy candidate CSV 與 QA report 路徑；CSV 必須包含 `source_md` backtrace column，QA report 要列出每家公司有哪些季度有 evidence，並摘要最大的候選 QoQ 權重變化。
- 是否更新正式 CSV；若未更新，說明仍需人工/研究員 review 的 evidence。
- 若使用者要求 commit/push，將 skill、candidate/report、CSV 更新與必要 pipeline 修正分別納入正確 repo。

## Skill 邊界

- 本 skill 產生 TW segment evidence/input 層：`output/company_segment_weights_quarterly_candidates_taiwan.csv`、`output/company_segment_weight_candidates_taiwan.csv`、`output/company_segment_weights_qa_taiwan.md`，並在研究員 review 後維護 `data/company_segment_weights.csv` 的 Taiwan rows。
- 本 skill 不產生 cycle model/output 層，不直接產生 `output/company_cycle_mapping.csv`、`output/company_cycle_major_weights.csv`、`output/company_cycle_intensity_taiwan.csv`、`output/company_cycle_intensity_by_symbol_taiwan.csv` 或 `output/company_cycle_index_taiwan.png`。
- 更新正式 segment weights 後，必須執行 `skill-company-cycle-index`，由 cycle-index skill 套用權重並產生 mapping/audit/index/PNG。

- United_States rows 則由 `scripts/build_company_cycle_index_united_states.py` 以 ConceptStocks quarterly segment revenue 計算最新季度 mix 後寫入 `data/company_segment_weights.csv`，source 欄位必須可回溯到原始 segment revenue 或 TSM platform fallback。
