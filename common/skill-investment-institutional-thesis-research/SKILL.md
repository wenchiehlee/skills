---
name: skill-investment-institutional-thesis-research
description: Maintain and extend the TW-institutional-investment-theses repository in Traditional Chinese. Use when Codex needs to add or update institutional sources, articles, theses, forecast ledgers, taxonomy mappings, comparisons, consensus reports, research TODOs, or interpret an article/news item through selected institutional lenses such as Goldman Sachs, Morgan Stanley, J.P. Morgan, Bank of America, and UBS.
---

# Institutional Thesis Research

使用此 skill 時，把本 repository 當成可長期維護的 institutional thesis database，而不是文章剪貼簿。預設以繁體中文輸出；但 official titles、URLs、entity names、taxonomy keys、schema field names、status values、quotes 與檔案路徑，在準確性需要時保留原文。

## 必讀脈絡

編輯前，依任務讀取相關 repo 文件：

- `AGENTS.md`：non-negotiable research rules。
- `TAXONOMY.md`：新增或調整 themes 前必讀。
- `DATA_MODEL.md`：調整 schema 或 forecast ledger 前必讀。
- `RESEARCH_WORKFLOW.md` 與 `SOURCE_POLICY.md`：ingest 新來源時必讀。
- `institutions/<institution>/` 既有檔案：建立新 thesis 前必讀。

## Epistemic Rules

- 優先使用 primary institutional sources；若只有 secondary source，明確標示並新增 primary-source verification TODO。
- 不得捏造 titles、authors、dates、URLs、forecasts、quotes 或 institutional positions。
- 嚴格區分 `fact`、`institution_interpretation`、`repository_inference`。
- forecast revision 必須 append chronologically，不得覆蓋舊 forecast。
- 不強迫形成 consensus；disagreement、scope mismatch、不可比數字都是研究結果。
- 不從 article 直接跳到 ticker；必須先寫清楚 transmission chain。

## Article / News Interpretation Mode

當使用者提供 article、news、excerpt、URL、chart 或 market claim，並要求用不同 institutions 解讀時，使用此模式。輸出是「institutional lens analysis」，不是宣稱該機構已評論這篇文章；除非 primary source 證明該機構真的評論過。

處理流程：

1. 判斷輸入型態：pasted text、URL、source title、chart claim 或 user paraphrase。
2. 若使用者提供 URL，或要求 latest / current / verify，先查證 source。
3. 分離 article facts、user framing 與 repository inference。
4. 若使用者沒有指定 institutions，預設使用目前五家：Goldman Sachs、Morgan Stanley、J.P. Morgan、Bank of America、UBS。
5. 對每個 selected institution，先對照既有 thesis files、forecast ledgers 與 comparison reports，再評論。
6. 判斷該 news 對既有 thesis 是 `supports`、`strengthens`、`weakens`、`contradicts`、`reframes` 或 `not material`。
7. 不得 invent institutional reaction。除非該 institution 直接發布此來源，否則使用「從 Goldman lens 看...」或「Repository inference based on UBS stored thesis...」這類表述。

建議輸出格式：

```text
## News / Article Fact Layer
## Institution Lens
| Institution | Likely Lens | Thesis Impact | Confidence | Why |
## Consensus / Disagreement
## Forecast / Number Check
## Repository Update Recommendation
## Open Questions / Verification TODO
```

Institution lens shortcuts：

- Goldman Sachs：demand validation、ROI、utilization、power/grid bottlenecks，以及 capex 是否連到 revenue benefits。
- Morgan Stanley：industrial buildout、macro variable、financing absorption、time-to-power and infrastructure bottlenecks。
- J.P. Morgan：multiyear capex wave、growth-engine framing、bond issuance、private credit、leverage containment and power constraints。
- Bank of America：physical AI、manufacturing productivity、data-center power reliability and grid / energy investment；不要強行給可比 capex forecast。
- UBS：capex discipline、cash capex vs. operating cash flow、capex taper tantrum risk、valuation selectivity and real-asset infrastructure shift。

若 article 本身來自已追蹤的 institution，先當作 source-ingestion 任務處理，再做 lens comparison。若 article 是 secondary news，先把它當 discovery/context，建立 durable repository records 前要找 primary institutional 或 company sources。

## Core Workflow

1. 驗證 source identity、publication date、URL、institution 與 source tier。
2. 用 URL、normalized title、institution/date、syndicated copies 與 repeated claims 檢查 duplicate。
3. 在 `institutions/<institution>/articles/<year>/` 建立 article metadata。
4. 擷取 key claims 與 quantitative forecasts，標示 confidence 與 epistemic layer。
5. 建立新 thesis 前，先搜尋既有 thesis files 是否已有 conceptual overlap。
6. 更新 thesis evidence、history、invalidation conditions 與 theme mappings。
7. 若來源含重要數字，追加到 `data/<institution>-forecasts.yaml`。
8. 只有當新 evidence 改變 cross-institution view、open questions 或 reader navigation 時，才更新 `comparisons/` 或 `reports/`。

## Repository Maturity Map

- Goldman Sachs 是 pilot，已有 article records、multiple thesis files、forecast ledger、forecast summary、open questions 與 deeper reports。
- Morgan Stanley、J.P. Morgan、Bank of America、UBS 是 first-touch institutions；在更多 primary sources 累積前，confidence 應較保守。
- 目前 five-institution AI capex overview 使用 Goldman Sachs、Morgan Stanley、J.P. Morgan、Bank of America、UBS。
- 目前 focus themes 包含 `AI_CAPEX`、`AI_INFRASTRUCTURE`、`POWER_DEMAND`、`POWER_GRID`、`DATA_CENTERS`、`AI_ROI`、`PHYSICAL_AI`、`PRIVATE_CREDIT`、`RELEVERAGING`、`HALO_REAL_ASSETS`。
- BofA 目前支持 power / physical-AI transmission layer，但本 repo 尚未保存可比 hyperscaler capex point forecast。
- UBS 目前提供 explicit AI capex anchors，以及 capex-discipline / capex-taper-tantrum lens；與較窄的 hyperscaler estimates 平均前必須先確認 scope。
- `POWER_EQUIPMENT`、cooling、networking and AI infrastructure financing 仍是 candidate sub-theses；必須等 direct evidence 足夠後才能拆 thesis。

## Output Patterns

- Article records：一個 source 一個 Markdown file，保留 official metadata，並分離 claims 與 inference。
- Thesis records：記錄 recurring institutional interpretation，包含 evidence、status、conviction、invalidation conditions、history 與 taxonomy mapping。
- Forecast ledgers：append-only dated observations；新增 ledger 時使用 `templates/forecast-ledger-template.yaml`。
- Comparisons：提出 consensus 或 ranges 前，先說明 scope mismatch；不要在 metric scope 不可比時平均 Goldman、Morgan Stanley、J.P. Morgan、UBS 的 capex anchors。
- TODOs：當 evidence missing、ambiguous 或不足以拆 thesis 時使用。

## Validation

編輯 forecast ledgers 後，執行：

```bash
python3 skills/skill-investment-institutional-thesis-research/scripts/check_forecast_ledger.py data/goldman-forecasts.yaml data/morgan-stanley-forecasts.yaml data/jpmorgan-forecasts.yaml data/bank-of-america-forecasts.yaml data/ubs-forecasts.yaml
```

commit Markdown / YAML 前，執行：

```bash
git diff --check
```
