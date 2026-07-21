---
name: skill-ai-trend-analytics
description: >-
  Build an auditable AI trend analytics layer from existing company segment weights,
  canonical cycle mappings, cycle performance tables, freshness reports, and research
  documents. Use when the user asks to advance AI trend analytics, validate AI trend
  conclusions, create coverage matrices, classify data as valid/estimated/proxy/missing/
  conflicting/stale/invalid, produce data issue registers, or turn company canonical
  cycle outputs into research-quality inference with explicit evidence chains.
---

# AI Trend Analytics Skill

## 角色定位

你是一位專業的跨台股與美股研究員。此 skill 的責任是把既有 canonical cycle、segment weights、cycle performance 與 freshness outputs 組成可稽核的 AI trend analytics layer。重點不是再寫一段看似完整的 AI 敘事，而是先標示每個數字的資料狀態、來源層級、限制、缺口與下一步修正行動，讓後續 trend inference 可以被回溯與反駁。

## Skill 邊界

- `skill-company-revenue-segment-weights` 負責 segment weight evidence、quarterly candidates、QA 與 active snapshot。
- `skill-company-cycle-index` 負責套用 active weights 到 canonical cycle model，產生 cycle mapping、cycle intensity、PNG 與 performance。
- 本 skill 消費上述 outputs，產生 coverage matrix、validity labels、issue register 與 inference quality gate；不直接抽取 IR/年報，也不直接產 cycle PNG。

## 標準流程

在 `biztrends.TW` 專案根目錄執行：

```bash
python3 skills/skill-ai-trend-analytics/scripts/run_ai_trend_analytics.py
```

runner 會讀取：

- `chats/AI_Trend_Analytics_Data_Refinement_Guideline.md`
- `docs/canonical_cycle_specification.md`
- `output/company_canonical_cycle_mapping.csv`
- `output/company_canonical_cycle_performance_details.csv`
- `output/company_segment_weights_qa_taiwan.md`
- `output/company_segment_weights_quarterly_candidates_taiwan.csv`
- `data/company_segment_weights.csv`
- `data/data_freshness_status.csv`

並產出：

- `output/ai_trend_coverage_matrix.csv`
- `output/ai_trend_coverage_matrix.md`
- `output/ai_trend_data_issue_register.csv`
- `output/ai_trend_data_issue_register.md`
- `output/ai_trend_inference.md`

## 資料狀態規則

每個 company/canonical cycle row 必須標示：

- `VALID_DIRECT`：官方直接揭露且期間可比。
- `VALID_DERIVED`：可由官方揭露資料重現計算。
- `ESTIMATED`：由公司層級財務或 segment proxy 加權推估。
- `PROXY`：供應鏈、概念股、fallback mapping 或 thematic exposure proxy。
- `MISSING`：必要 segment、performance 或 source 不存在。
- `CONFLICTING`：同一公司/期間/segment 有可靠來源衝突。
- `STALE`：來源期間落後且可能影響結論。
- `INVALID`：加總錯誤、重複計入、定義錯誤或不應納入推論。

若同一 row 同時有多個問題，`data_status` 採最保守狀態，issue register 保留所有問題。

## 輸出回報

完成後回報：

- coverage matrix rows、covered company count、covered canonical cycle count。
- issue register open issue count 與 P0/P1/P2/P3 分布。
- inference report 是否已產生，並摘要哪些 cycle 可以支持方向性推論、哪些只能視為 proxy。
- 哪些 major AI cycles 仍被 fallback/proxy 或 stale data 主導。
- 是否需要先回到 `skill-company-revenue-segment-weights` 補 evidence，或回到 `skill-company-cycle-index` 重算 cycle performance。

若使用者要求 commit/push，應把 skill、runner 與 generated coverage/issue/inference outputs 一起 commit。
