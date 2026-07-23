---
name: conference-digest
version: 2.4.4
description: 法說會/earnings call 與財報結果 digest。當使用者要求分析台股/美股法說會、從 FIN/GT/IR/Q&A 修正 GT，或針對 README 類型=財報 的事件使用 Celine/公司財報文件/Yahoo consensus 產出 earnings-result digest 時使用；找出預期差、模型修正路徑、管理層可信度、股價影響因素，並在美股案例列出台股 read-through。
---

# 法說會重點萃取與投資影響分析 SOP (Investor Conference Digest SOP)

本技能用於分析 `InvestorConference` 資料庫中的上市櫃公司或美股公司法說會/earnings call 資料，也支援 README `類型=財報` 的 earnings-result digest。輸出目標不是「整理管理層說了什麼」，而是判斷：

1. 哪些資訊超出或低於市場與前次財測預期。
2. 哪些財務模型欄位需要調整。
3. 哪些資訊只在 Q&A 壓力下揭露。
4. 管理層承諾、措辭與回答品質是否可信。
5. 哪些變化可能影響未來 EPS、現金流、估值與股價反應。

---

## 1. 角色定位

你是一位專業的跨台股與美股法人研究員。你的任務是從公開法說會資料中建立可追溯、可稽核、可用於投資決策的 digest；遇到美股 earnings call 時，需額外整理對台股供應鏈、同族群與市場情緒的 read-through。

> [!IMPORTANT]
> Digest 的核心不是摘要完整度，而是投資洞察：surprise、guidance delta、Q&A incremental information、management credibility、estimate revision path。

---

## 2. 觸發條件與參數

### 2.1 觸發場景

當使用者提出以下需求時使用本技能：

* 「分析 2357 法說會」
* 「摘要 2357 2026 Q1 法說會」
* 「digest 2357」
* 「分析 GOOGL 財報結果」或 README 中 `類型=財報` 的事件
* 直接提供法說會逐字稿、字幕、簡報、Q&A 檔案、earnings release、financial tables 或 Celine 財報結果

### 2.2 必要參數

| 參數 | 說明 |
| :--- | :--- |
| `StockID` | 股票代碼，如 `2357` |
| `Year` | 西元年；未指定時使用該公司最新季度 |
| `Quarter` | `q1` 到 `q4`；未指定時使用該公司最新季度 |

### 2.3 建議參數

| 參數 | 預設值 | 用途 |
| :--- | :--- | :--- |
| `output_language` | `zh-TW` | 預設繁體中文，可由使用者覆寫 |
| `analysis_mode` | `repo_only` | `repo_only` 僅用 repo 內資料；`enhanced` 可加入外部共識、股價、同業與產業資料 |
| `sector_template` | `auto` | 自動辨識產業，或由使用者指定產業 KPI |
| `expectation_source` | 空值 | 市場共識或法人預估來源；未提供時不可假裝有共識資料 |
| `confidence_mode` | `strict` | 嚴格限制低證據推論 |
| `comparison_depth` | `4` | 跨期比較深度，建議 1 到 8 季 |
| `quote_mode` | `critical_only` | `critical_only` 僅引用關鍵證據；`full` 增加引用量 |
| `scoring_mode` | `weighted` | 紅黃綠燈使用權重與分數加總 |
| `market` | `auto` | `auto` / `TW` / `US`；英文字母 ticker 預設 US，數字股票代碼預設 TW |
| `correlation_mode` | `auto` | `none` / `tw_readthrough` / `quantitative`；US stock 預設 `tw_readthrough` |

> [!CAUTION]
> 若未取得市場共識、法說前股價或外部法人模型，必須明確標示「repo-only mode，無法判斷相對市場共識的 beat/miss」，不可自行推測市場預期。若 repo 內已同步 `data/Yahoo.Finance/raw_yahoo_finance_consensus_history.csv`，可將其列為 repo 內市場共識來源，但必須標示覆蓋範圍限制。

市場預期資料層的後續擴充 TODO 見 `references/market_expectations_todo.md`；當任務涉及新增 consensus、price-implied expectation、estimate revision 或 model-line consensus 管線時，先讀該文件。

---

## 3. 資料來源解析

### 3.1 檔案命名與優先級

資料位於 `InvestorConference/data/{StockID}/`；舊版頂層 `{StockID}/` 僅作為相容 fallback。

| 檔案模式 | 內容 | 優先級 |
| :--- | :--- | :--- |
| `{StockID}_{Year}_q{N}_GT.srt` | 由 FIN 與相關材料交叉校正後的字幕；可能是人工校正版或 GT-candidate | 字幕第一優先，但需檢查 metadata/review level 與 conservative 驗收門檻 |
| `{StockID}_{Year}_q{N}_FIN.srt` | Whisper 自動轉錄字幕 | 字幕第二優先 |
| `{StockID}_{Year}_q{N}.md` | 音檔逐字稿 | 字幕第三優先 |
| `{StockID}_{Year}_q{N}_ir.md` | 中文法說會簡報 | 財務數據第一優先 |
| `{StockID}_{Year}_q{N}_ir_en.md` | 英文法說會簡報 | 財務數據補充 |
| `{StockID}_{Year}_q{N}_qa.md` | 官方 Q&A 紀錄 | Q&A 分析必讀 |
| `{StockID}_{Year}_q{N}_report_en.md` / `_financial_tables.md` | 美股 earnings release / tables | US 財務數據第一來源 |
| `{StockID}_{Year}_q{N}_performance_review.md` / `_ir_en.md` | 美股簡報或 performance review | US guidance / segment 補充 |
| `{StockID}_{Year}_q{N}_10q.md` | SEC 10-Q/10-K 摘要或連結 | US filing 交叉驗證（若可得） |
| `{StockID}_{Year}_q{N}_alphaspread_transcript.md` | 第三方逐字稿 | 補充來源 |
| `{StockID}_{Year}_q{N}_yahoo_transcript.md` | Yahoo Finance 第三方逐字稿 | 補充來源 |
| `{StockID}_{YYYYMMDD}_alphamemo_transcript.md` | 第三方會議紀要 | 補充來源 |

### 3.2 來源使用原則

1. 財務數字以公司正式文件為第一來源：TW 優先 `_ir.md`/`_ir_en.md`；US 優先 earnings release/report、financial tables、performance review/deck 與 SEC filing（若可得）。
2. Q&A 重要性高於 prepared remarks；Q&A 可能揭露法人真正擔心的問題、管理層未主動提到的限制與不確定性。
3. GT 字幕優先於 FIN 字幕，但必須讀取 GT metadata/review level；若 GT 僅為 `conservative_from_FIN` 或缺 metadata，重大結論仍需回到 IR、Q&A、第三方逐字稿與音檔交叉驗證。
4. 產生 GT 或 digest 前必須檢查 repo 根目錄 `audio_metadata.json`；若目標 stem `status` 為 `duplicate`、`invalid` 或 checksum 與其他季度相同，視為音訊錯配 Blocker/Major，不可把 FIN 時間軸視為本季音訊證據。
5. 若簡報、Q&A 與字幕資訊矛盾，必須在報告中標示，並視嚴重度建立資料品質 issue。
6. 法人提問只能代表「市場疑慮」，除非管理層確認，不可寫成公司事實。

### 3.1.1 財報事件與 Celine 財報結果

若 README 事件 `類型=財報`，不得要求音檔、FIN 或 GT 作為 digest 前置條件。此時 digest 類型為 `earnings_result_digest`，資料來源優先級為：

1. 公司正式 earnings release/report、financial tables、supplemental/performance deck、SEC filing。
2. Celine 財報結果檔：`{StockID}_{Year}_q{N}_celine_result.md` 或 `.json`。
3. repo-synced Yahoo Finance consensus history，僅用於 revenue/EPS consensus 比較。
4. Yahoo Finance financials 或其他二級資料，只能作補充或 discovery。

Celine 使用規則：

* Celine 可用來快速取得財報實績、beat/miss 初判與結果摘要，但不可取代公司正式文件。
* Celine 欄位必須與公司文件交叉驗證；無法驗證的欄位標示 `Celine-only`，信心最高為中。
* 若 Celine 缺資料，digest 應明確標示 `Celine unavailable`，不要改走法說會 FIN/GT 流程。
* 財報 digest 不輸出 Q&A 壓力地圖、管理層回答品質或 GT 證據台帳，除非同一季度另有 earnings call transcript/audio。
* 財報 digest 應聚焦 earnings surprise、guidance delta、EPS 品質、segment/platform surprise、CapEx/FCF、market read-through 與後續需要補抓的 call material。

### 3.2.1 市場共識資料來源：Yahoo.Finance consensus history

若 repo 內存在 `data/Yahoo.Finance/raw_yahoo_finance_consensus_history.csv`，digest 可在 `repo_only` 模式下使用該檔作為「市場共識」來源，並在報告 metadata 的 `市場預期來源` 標示：`Yahoo.Finance consensus history (repo-synced)`。

使用規則：

1. 以法說會日期或財報發布日期作為 cutoff，選擇 `forecast_asof_date <= cutoff_date` 且最接近 cutoff 的該公司資料列，避免後視偏誤。
2. `earnings_0q_avg` 可作為當季 EPS 共識；`revenue_0q_avg` 可作為當季營收共識；`earnings_1q_avg` / `revenue_1q_avg` 可作為下一季初步共識。
3. `revenue_*q_avg` 單位為元；台股報告通常需轉為 `NT$B` 或 `億元` 後再與公司實績比較。
4. 此檔只足以支援 EPS 與 revenue 的 consensus beat/miss；不得用來判斷毛利率、營益率、CapEx、segment revenue、股價隱含期待或法人模型細項。
5. 若該公司或 cutoff 前沒有資料，仍須標示市場共識 NA。若資料基準日距離法說會超過 45 天，信心降為中或低。
6. 報告中的 Surprise Matrix 必須分開顯示「相對公司財測」與「相對市場共識」。若市場共識只涵蓋 revenue/EPS，其餘項目填 `NA`，不可推估。
7. 欄位定義以 `definitions/raw_yahoo_finance_consensus_history_definition.md` 為準；若資料與 definition 不一致，建立資料品質 issue。

### 3.2.2 來源層級與一級來源優先

Digest 必須明確區分一級來源與二級來源。二級來源可以提高搜尋效率與校正品質，但不得覆蓋公司或交易所正式資料。

| 層級 | 來源 | Digest 用途 | 不可做的事 |
| :--- | :--- | :--- | :--- |
| 一級來源 | 公司 IR 官網、公司正式 PDF/音檔/webcast replay、MOPS/TWSE 官方公告、SEC filing、公司 earnings release/financial tables | 判定季度、日期、正式財務數字、guidance、檔案類型與是否可引用為硬數據 | 若一級來源彼此衝突，需標示矛盾並降信心 |
| 二級來源 | FinmoConf、AlphaSpread、Yahoo transcript、AlphaMemo、第三方法說索引、第三方摘要 | 發現材料、補 speaker/Q&A、校正 FIN/GT 專名與語句、交叉驗證 | 不得覆蓋一級來源的季度、日期、檔案類型、財務數字或 guidance |

若一級與二級來源衝突，必須採用以下處理：

1. 報告、README 建議、GT metadata 與 evidence ledger 均以一級來源為準。
2. 二級來源只標示為 `secondary_index`、`secondary_transcript` 或 `cross_check`。
3. 在資料品質問題中記錄 mismatch，例如「FinmoConf 將 TSMC 官方 2026 Q2 頁面標為 2026Q3」。
4. 若二級來源提供 transcript，但官方沒有 transcript，仍可用於 `conservative_from_FIN` 的行內校正；但重大財務數字、季度與日期必須回到一級來源確認。
5. 若只有二級來源而缺一級來源，必須明確標示 `source_level: secondary_only`，並降低信心；不得寫成公司正式揭露。

### 3.3 前次與跨期資料

同公司目錄下前一季，以及 `comparison_depth` 範圍內可取得的前期 `_ir.md`、字幕與 `_qa.md`，應用於：前次公司財測達成度、管理層承諾追蹤、相同主題措辭變化、KPI 定義或口徑是否改變。

### 3.3.1 業務平台與財務數據萃取與跨期檢核防錯機制

在萃取業務平台（Net Revenue by Platform）、製程（by Technology）、地區或產品線營收占比與財務 KPI 時，必須遵循以下防錯守則：

1. **表格優先原則 (Table-First Principle)**：
   * 定量數據（如各平台營收占比）必須**優先讀取與採用「結構化表格」**，而非僅依賴文章段落的口語或總結敘述（Narrative Text）。
   * 內文敘述經常使用並列句式，如 *"HPC and Smartphone represented 66% and 22% of net revenue respectively..."*。未經語法拆解的解析器極易誤將其擷取為單一類別 `"HPC and Smartphone"` 並誤填數值 `66%`。

2. **嚴禁標籤誤合併 (No Improper Label Merging)**：
   * 除非官方原始表格中明確列出合併類別（如「其他及未列明」），否則**不得將多個獨立類別合併為單一標籤**。
   * 若內文出現 *"X and Y represented A% and B% respectively"*，必須在語意解析層強制拆解為獨立項：`X: A%` 與 `Y: B%`。

3. **跨期合理性與異常檢核 (Cross-Quarter Anomaly Check)**：
   * 萃取最新季度數據時，應與前 1 至 4 季（如 1Q26、4Q25）同項目數據進行跨期波動比對。
   * 若某項 Segment 的權重或標籤出現異常跳動（例如 HPC 突然從 61% 驟升至 88%，或出現含有 `and` 的複合標籤），必須觸發警示（Anomaly Warning）並重新回到原始簡報表格校正標籤對位。

### 3.4 輔助腳本

分析前於 repo 根目錄執行：

| 腳本 | 用途 | 時機 |
| :--- | :--- | :--- |
| `python skills/skill-investorconference-digest/scripts/find_sources.py {StockID} [Year q{N}]` | 解析主要、備援、前季與缺漏資料來源；可加 `--json` 輸出 manifest | 每次分析第一步 |
| `python skills/skill-investorconference-digest/scripts/lint_sources.py {StockID} [Year q{N}] [--issue-draft out.md] [--issue-json out.json]` | 機械性資料品質檢查與 issue 草稿 | 分析前必跑 |
| `python skills/skill-investorconference-digest/scripts/evaluate_digest.py <digest.md>` | 檢查 digest 是否缺少來源、信心、模型影響、Q&A-only、預期差等欄位 | 產出報告後必跑 |
| `python skills/skill-investorconference-digest/scripts/check_digest_freshness.py [--srt-only]` | 掃描全庫尚未產出 digest 的季度 | 批次補做規劃 |

`lint_sources.py` 回傳非零 exit code 代表有資料品質問題；ERROR/Blocker 會使財務結論錯誤或無法分析時，必須先處理或在報告中降信心。


### 3.5 GT 字幕生成與校正 SOP

本節屬於 digest skill，而非 ingest skill。`skill-investorconference-ingest` 的責任是蒐集音檔、IR、Q&A、第三方逐字稿與 metadata；`skill-investorconference-digest` 的責任是在分析前，使用這些材料生成或修正可供研究引用的 `{StockID}_{Year}_q{N}_GT.srt`。

#### 3.5.1 何時必須處理 GT

若出現以下任一情況，先處理字幕品質，再產出 digest：

* 缺少 `{StockID}_{Year}_q{N}_GT.srt`，但有 FIN 或其他逐字稿可作初稿。
* GT 與 FIN 幾乎相同，疑似只改檔名。
* GT 缺 metadata 或 review level。
* FIN、GT、IR、Q&A 或第三方逐字稿對財務數字、產品名、人名、法人名、年份/季度、Q&A 段落有明顯衝突。
* `lint_sources.py` 對字幕提出 Major/Blocker。

#### 3.5.2 GT 生成流程

1. 先檢查 `audio_metadata.json`、`audio_manifest.json` 與 FIN 開頭內容是否一致；若音檔 checksum 被標成 duplicate 或 FIN 明確屬於其他季度，FIN 只能作為近似時間 scaffold，不得作為本季音訊證據。
2. 使用 `{StockID}_{Year}_q{N}_FIN.srt` 作為時間軸與初稿；不得只複製 FIN 並改名為 GT。若 FIN 來自錯配音檔，GT metadata 必須標示 `Audio-Checked: none` 與 timing limitation。
3. 以本季 `_ir.md` / `_ir_en.md` 校正財務數字、產品名、事業群、KPI、CapEx、毛利率、EPS、年份與季度。
4. 以本季 `_qa.md` 校正 Q&A 問題主題、法人追問與管理層回答脈絡。
5. 以 `_alphaspread_transcript.md`、`_yahoo_transcript.md`、`_alphamemo_transcript.md` 等第三方逐字稿補足 speaker、英文專有名詞、Q&A 段落與語句順序；若第三方逐字稿沒有 timestamp，只能作為行內校正參考，不得把全文重新切段塞回 FIN timestamp。
6. 以前一季或相近季度的 GT/FIN/IR/Q&A 校正公司固定用語、產品線名稱、法人名稱、管理層姓名與長期 KPI 口徑。
7. 針對低信心段落、財務數字、Q&A 追問、FIN 與其他來源不一致處抽聽音檔；若無法聽音檔，必須在 metadata 標示限制。
8. 保留 FIN 的時間軸、行數與 line boundary，除非有音檔依據可重新對齊；大幅改動時間戳或重排 transcript 不可標示為 `conservative_from_FIN`。
9. 產出 `{StockID}_{Year}_q{N}_GT.srt` 後重跑 `lint_sources.py`，並用 GT/FIN diff 檢查確認沒有 transcript-wide reflow。

#### 3.5.3 Conservative GT 驗收門檻

`conservative_from_FIN` 的意思是「在 FIN scaffold 上做低風險校正」，不是把另一份 transcript 重新對齊到 FIN。產生或接受 GT 前必須檢查：

| 檢查項目 | 驗收規則 | 不合格處理 |
| :--- | :--- | :--- |
| 行數 | GT timestamp 行數應與 FIN 相同或極接近；預設需完全一致 | 若差異明顯，標為結構異常，不可列為可用 GT |
| timestamp | GT 應保留 FIN timestamp；除非有音訊校對依據，不得大量改動 | 大量改動需改標 `partial_audio_checked` 或退回缺 GT |
| line boundary | 第三方逐字稿不得整段 reflow 到 FIN timestamps | 若發生 reflow，刪除/重建 GT；不可標 `conservative_from_FIN` |
| 文字修改比例 | 只允許專名、術語、數字單位、明顯錯字與低風險 Q&A speaker 修正；一般應低於 10% 到 15% 的 timestamp 行 | 若每行幾乎都改，代表不是 conservative GT |
| 第三方來源 | 英文 FIN + 英文 AlphaSpread/Yahoo/official transcript 可做行內修正；中文/中英混合 FIN + 英文 transcript 只能修專名、數字、術語 | 不得翻譯、改寫或補寫 FIN 未辨識出的整句 |
| 無第三方逐字稿 | 若只有弱 FIN + IR，不能產生 research-usable GT | 保持 GT 缺失，或只建立低信心 issue draft，不放 README GT 欄 |

案例準則：

* DELL/QCOM 類英文 earnings call：若 FIN 與第三方英文 transcript 高度重疊，可修正 `OpenClaw -> OpenAI`、`ADATs -> ADAS`、人名、產品名等局部錯誤。
* 2454 類有 AlphaSpread 但無 timestamp 的 transcript：可用 AlphaSpread 校正 FIN 行內錯字，但不可把 AlphaSpread 段落全文重切到 FIN timestamp。
* 8299 類只有弱 FIN 與 IR、缺 AlphaSpread/Yahoo/official transcript：不應產生 GT；README GT 欄維持 `-`，資料品質 issue 應標示需要第三方逐字稿或人工音訊校對。

#### 3.5.4 GT metadata

GT 檔案開頭必須包含 metadata；若歷史檔案缺 metadata，使用時需降信心並優先補齊。

```text
[METADATA]
Source: {StockID}_{Year}_q{N}_FIN.srt
Review-Level: human_verified | partial_audio_checked | conservative_from_FIN | rejected_low_confidence
Reviewer: Codex/user
Reviewed-At: YYYY-MM-DD
Audio-Checked: full | sampled | none
Correction-Sources: FIN, IR, IR_EN, QA, AlphaSpread, Yahoo, AlphaMemo, prior_quarters, audio
Corrections: terminology, hallucination-removal, numbers, names, qa-alignment
Confidence: high | medium | low
Notes: ...
---
```

Review level 定義：

| Review-Level | 定義 | Digest 使用方式 |
| :--- | :--- | :--- |
| `human_verified` | 已完整或接近完整對音訊校正，並與關鍵材料交叉確認 | 可作字幕第一來源；重大財務數字仍以 IR 為準 |
| `partial_audio_checked` | 已抽聽低信心段落與關鍵數字/Q&A，但未全段校對 | 可優先於 FIN；重大結論需交叉驗證 |
| `conservative_from_FIN` | 主要從 FIN 與文字材料保守修正，未充分音訊校對；必須通過 conservative GT 驗收門檻 | 視為 GT-candidate；不可宣稱完整人工校正版 |
| `rejected_low_confidence` | FIN 太弱且缺第三方逐字稿/音訊校對，或 GT 發生 transcript-wide reflow/結構異常 | 不可放入 README GT 欄；應刪除或保留為 issue 附件，不作 digest 主要字幕來源 |

#### 3.5.5 關閉資料品質 issue 的條件

針對「缺 GT」或「GT 品質不足」issue，關閉前必須留言包含：GT 檔案路徑、Review-Level、使用的校正來源、是否抽聽音檔、`lint_sources.py` 結果。若僅產生 `conservative_from_FIN`，issue 可改標為需後續人工音訊校對，但不應描述為完整 GT 已完成。若缺第三方逐字稿且 FIN 品質低，應保持缺 GT 或標示 `rejected_low_confidence`，不得為了關 issue 產生低品質 GT。

#### 3.5.6 音檔錯配時的 GT 規則

若 `audio_metadata.json` 顯示本季音檔與前期或其他季度 checksum 相同，或 FIN 內容明確指向其他季度：

* 不可宣稱已完成本季 audio-verified GT。
* 只有在有本季 AlphaSpread/Yahoo/官方逐字稿、IR 與 Q&A 支持，且能通過 conservative GT 驗收門檻時，才可建立 `conservative_from_FIN` GT candidate。
* FIN 時間戳只能標示為 approximate scaffold；引用時應優先引用文字來源位置，時間戳僅供閱讀導覽。
* GT metadata 必須包含 `Audio-Checked: none`、`Correction-Sources`、`Timing-Note` 與 `Confidence: medium/low`；若只有弱 FIN + IR，應改列缺 GT，不得產生 README 可用 GT。
* 資料品質 issue 不得因 GT candidate 產生就直接關閉；必須明確說明正確音檔仍缺失，或另行取得正確音檔後再關閉音訊錯配項目。

---

## 4. 輸出語言與證據格式

預設使用繁體中文（台灣），採用台灣投資市場術語：法說會、財測、毛利率、營益率、EPS、資本支出、接單能見度、庫存、自由現金流、估值、法人模型、上修、下修。

每個重大結論都必須附上：結論、證據類型、信心、原因、時間範圍、來源、是否有矛盾。

| 證據類型 | 定義 |
| :--- | :--- |
| 硬數據 | 簡報或財報中的明確數字 |
| 管理層說法 | 管理層直接表述，但未必已驗證 |
| Q&A 增額資訊 | 僅在法人追問下揭露 |
| 法人疑慮 | 問題所反映的市場擔憂 |
| 分析推論 | digest 根據資料做出的推論 |

| 信心 | 條件 |
| :--- | :--- |
| 高 | 簡報有明確數字、多來源一致、時間與口徑明確、無重大矛盾 |
| 中 | 管理層直接說法但缺乏數字、客戶或時間細節，或僅有單一來源 |
| 低 | 僅能從措辭推論、字幕疑似錯誤、跨來源不一致、管理層回答模糊或迴避 |


### 4.1 市場模板：TW vs US

`market=auto` 時，數字股票代碼視為 TW，英文字母 ticker 視為 US。兩者共用 GT、Q&A 壓力地圖、證據/信心、模型影響與管理層可信度框架，但財務語彙與來源優先級不同。

| 項目 | TW | US |
| :--- | :--- | :--- |
| 主要公司文件 | `_ir.md`, `_ir_en.md`, MOPS 財報 | earnings release/report, performance review/deck, financial tables, SEC 10-Q/10-K |
| 財務口徑 | 營收、毛利率、營益率、EPS、CapEx、自由現金流 | revenue、gross margin、operating margin、GAAP/non-GAAP EPS、diluted shares、FCF、buyback/dividend |
| Guidance | 公司財測、管理層展望、法人追問 | revenue/EPS/gross margin/op margin/segment guidance vs consensus |
| KPI | 依台股產業模板 | 依 US 產業模板；SaaS: ARR/RPO/NRR，半導體: channel inventory/design win，硬體: backlog/AI server orders |
| 估值影響 | EPS/現金流/本益比/台股族群評價 | estimate revision、multiple expansion/compression、GAAP vs non-GAAP quality、share count |

US digest 必須額外檢查：

1. GAAP 與 non-GAAP 差異及 reconciliation。
2. EPS 成長是否來自本業、稅率、回購、一次性項目或股數下降。
3. Segment revenue / operating income 對總體 guidance 的貢獻。
4. Management guidance 與市場共識差異；無共識時標示 repo-only。
5. Buyback、dividend、share count 對 EPS 品質的影響。
6. SEC filing 或 company release 與第三方 transcript 的矛盾。

---

## 5. 報告架構：投資決策層 + 十三節研究層

報告必須先輸出「零、投資決策摘要」，再輸出十三節完整研究層。若事件類型是 `財報` 且沒有 call transcript/audio，改用「財報結果 digest」精簡架構；不要填充 FIN/GT 或 Q&A 章節。

### 5.0 財報結果 digest 架構

適用於 README `類型=財報`，例如 `GOOGL Alphabet Inc. | 2026 Q1 | 財報 | 2026-07-22`。

1. 財報結果摘要：revenue/EPS、GAAP/non-GAAP、主要 beat/miss、guidance 變化、信心與缺口。
2. Surprise Matrix：本季實績 vs Yahoo consensus/Celine/company guidance；Yahoo 只支援 revenue/EPS，其餘填 `NA`。
3. EPS 品質與現金流：稅率、股數、回購、一次性項目、FCF 與營業現金流。
4. Segment / platform read-through：廣告、Cloud、AI capex、硬體或其他公司專屬 segment 對模型的影響。
5. Guidance delta：下一季/全年財測與市場共識差異；資料不足時標 `NA`。
6. 台股供應鏈/市場 read-through：US ticker 預設輸出，並區分 direct supply、supply-chain exposure、sentiment/valuation。
7. 待補材料：是否仍需 earnings call transcript/audio、10-Q、financial tables 或 Celine 欄位補強。
8. 證據台帳：公司文件、Celine、Yahoo consensus 與其他來源分開標示來源層級與信心。

### 5.1 法說會 / earnings call digest 架構

以下十三節適用於有法說會、earnings call、字幕、逐字稿或 Q&A 的事件。

### 零、投資決策摘要

限制在一頁內，優先回答投資決策問題。

| 項目 | 結論 |
| :--- | :--- |
| 核心預期差 | 相對前次公司財測、QoQ/YoY、可得市場共識或 repo-only 限制的 beat/miss |
| 財測變化 | 上修、維持、下修、措辭轉強/轉弱、區間變寬/變窄 |
| Q&A 增額資訊 | 僅在法人追問下揭露的重要資訊 |
| 管理層可信度 | 直接、保守、迴避、前後不一致、承諾達成度 |
| 可能上修項目 | 可能讓法人上修的營收、毛利率、費用率、EPS、FCF 或估值假設 |
| 可能下修項目 | 可能讓法人下修的模型欄位與原因 |
| 股價反應條件 | 正面、中性、負面情境與條件，不可保證漲跌 |
| 分析信心 | 高、中、低，並說明主要限制 |

### 一、法說會一句話重點

固定四句：最大正面 surprise、最大負面 surprise、最重要的 Q&A 增額資訊、最可能改變法人模型或股價的變數。

### 二、財務表現與 Surprise Matrix

先建立 Surprise Matrix：

| 項目 | 本季實績 | QoQ | YoY | 前次公司財測 | 市場預期 | 結果判定 | 模型影響 |
| :--- | ---: | ---: | ---: | ---: | ---: | :--- | :--- |
| 營收 | | | | | | Beat/In-line/Miss/NA | |
| 毛利率 | | | | | | | |
| 營益率 | | | | | | | |
| EPS | | | | | | | |
| FCF | | | | | | | |
| 存貨 | | | | | | | |

必須分析 EPS 品質、一次性項目、匯率與業外影響、營業現金流、FCF 與淨利差異、DSO/DIO/DPO/現金轉換週期。資料不足時標示 NA。

### 三、財測與未來展望

拆成三層：明確量化財測、定性展望、財測變化。所有財測結論都必須相對於前次財測；若有 `expectation_source`，再相對於市場共識。

### 四、成長動能與成熟度

| 成長動能 | 階段 | 時程 | 是否已貢獻營收 | 證據 | 主要不確定性 |
| :--- | :--- | :--- | :--- | :--- | :--- |

階段固定為：概念/策略、研發、客戶驗證、小量試產、量產、營收放量、獲利貢獻。

### 五、毛利率分析

建立毛利率 bridge：

| 影響因素 | 方向 | 估計影響 | 是否持續 | 證據 |
| :--- | :---: | ---: | :--- | :--- |

必須區分結構性改善、週期性改善、一次性因素、會計或匯率影響。

### 六、CapEx 分析

分析 CapEx 金額、YoY/QoQ、用途、CapEx/營收比、CapEx/折舊比、投產時間、對應客戶或需求、是否已有訂單支持、折舊何時開始、產能利用率風險、對 FCF 的影響、可否推估回收期。

> [!CAUTION]
> CapEx 增加不一定正面，可能代表被迫擴產、客戶要求、遷廠、地緣政治成本、替換設備、建廠延誤或低報酬投資。

### 七、策略重點

必須回答：策略是否與財務資源配置一致、是否有具體 KPI、是否有客戶或訂單驗證、是否形成差異化、是否可提高毛利率/ROIC/市占率、是否只是敘事。

### 八、風險

| 風險 | 來源 | 發生機率 | 財務衝擊 | 時間範圍 | 領先指標 | 是否已反映 |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |

來源分為管理層主動提到、法人追問、合理推論。「是否已反映」限用：已反映在財測、部分反映、尚未反映、無法判斷。

### 九、Q&A 壓力地圖

> [!IMPORTANT]
> Q&A 是報告中最高優先區塊，必須從摘要升級為壓力測試地圖。

Q&A 統計表：

| 指標 | 結果 |
| :--- | ---: |
| 法人問題總數 | |
| 追問次數 | |
| 涉及財測問題數 | |
| 涉及毛利率問題數 | |
| 涉及需求/訂單問題數 | |
| 完整回答比例 | |
| 有效回答比例 | |
| 部分回答比例 | |
| 重新框架比例 | |
| 迴避/非回答比例 | |
| Q&A-only 新資訊數 | |

法人追問熱點：

| 排名 | 主題 | 被問次數 | 是否追問 | 管理層回答品質 | 股價重要性 |
| ---: | :--- | ---: | :---: | :--- | :---: |

回答品質五級：完整回答、有效回答、部分回答、重新框架、迴避/非回答。還必須列出 Q&A-only 資訊、尚未回答的重要問題、管理層態度、追問壓力、CEO/CFO 或其他高管語氣是否一致。

### 十、前次財測、承諾與措辭追蹤

拆成三張表：正式財測達成情況、管理層承諾追蹤、相同主題措辭變化。

| 承諾事項 | 首次提出時間 | 原定時程 | 本季進度 | 是否達成 | 評估 |
| :--- | :--- | :--- | :--- | :---: | :--- |

| 主題 | 前次法說 | 本次法說 | 變化判讀 |
| :--- | :--- | :--- | :--- |

> [!CAUTION]
> 不可只依單一正面或負面詞彙判斷語氣；必須比較同一主題在前後兩次法說中的用詞、量化程度、時間承諾與回答直接程度。

### 十一、加權紅黃綠燈評分

固定核心項目：營收、毛利率或核心獲利率、EPS、財測、現金流、資產負債表、管理層可信度、風險、訂單或需求能見度。

依產業選 2 到 4 個動態項目：半導體（稼動率、先進製程占比、庫存週轉）、ODM/伺服器（AI Server、Rack 出貨、客戶集中度）、IC 設計（ASP、產品組合、庫存天數、Tape-out/Design win）、航運（運價、裝載率、船舶供給、合約價）、金融（淨利差、信用成本、資產品質、資本適足率）、零售（同店成長、客單價、展店效率）、SaaS（ARR、NRR、RPO、CAC、營業槓桿）。

| 項目 | 權重 | 分數 | 燈號 | 信心 | 原因 |
| :--- | ---: | ---: | :---: | :---: | :--- |

分數：`+2` 明顯正面、`+1` 小幅正面、`0` 中性、`-1` 小幅負面、`-2` 明顯負面、`NA` 資料不足。整體分數必須以權重加總，不可只憑直覺給整體燈號。若公司不適用 AI，不得強行加入 AI 項目。

### 十二、股價影響分析：事件-模型-估值鏈條

| 事件 | 影響模型欄位 | 影響方向 | 時間範圍 | 可能估值影響 |
| :--- | :--- | :---: | :--- | :--- |

必須區分短期股價催化劑、中期基本面變化、長期策略價值、已知資訊、新增資訊、可能已反映在股價的資訊。股價影響不是單純判斷消息好壞，而是判斷該消息是否改變市場原先的營收、毛利率、EPS、現金流或估值假設。

### 十三、證據台帳

| 結論 | 原文引用 | 來源 | 位置 | 證據類型 | 信心 | 是否有矛盾 |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |

> [!CAUTION]
> 不得杜撰引用。引用不超過兩句；若使用字幕，保留 SRT 時間戳；若使用簡報，保留頁碼。

---

## 6. KPI 衛生檢查

遇到公司自定義或 non-GAAP KPI，必須建立 KPI 檢查：KPI 名稱、公司定義、GAAP/non-GAAP/公司自定義、與上季是否一致、是否可與財報調節、本季變動原因、模型影響、是否只揭露有利部分或改變口徑。


## 6.1 美股對台股供應鏈/市場 Read-through

當 `market=US` 或 `correlation_mode=tw_readthrough` 時，必須新增本節。目標是把 DELL、QCOM、NVDA、AMD 等美股 earnings call 對台股可能的供應鏈、同族群或市場情緒影響整理成可稽核表格。

### 6.1.1 分類規則

| Link Type | 定義 |
| :--- | :--- |
| Direct supply | 有來源支持的直接供應/客戶/合作關係 |
| Supply-chain exposure | 同一產品鏈或零組件鏈，但未證明直接供應 |
| End-market correlation | 共同暴露於 AI server、smartphone、PC、networking、auto 等需求循環 |
| Competitive relationship | 產品或客戶預算存在競爭或替代 |
| Sentiment / valuation | 美股事件可能帶動台股同族群評價或交易情緒 |
| Quantitative correlation | 有價格資料計算的 rolling correlation；若未計算，不得填數字 |

> [!CAUTION]
> 不可把「可能受惠」寫成直接供應關係。除非有公司文件、法說、可靠新聞或資料庫支持，否則 `Link Type` 必須標示為 `Supply-chain exposure`、`End-market correlation` 或 `Sentiment / valuation`。

### 6.1.2 必輸出表格

| Taiwan Stock | Company | Link Type | Relationship to US Company | Evidence | Impact Direction | Confidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2308 | 台達電 | End-market / supply-chain exposure | AI server power/thermal exposure to US AI infrastructure cycle | InvestorConference materials / company filings / cited source | Positive if US AI server demand rises | Medium |

### 6.1.3 常見 US → TW read-through 候選池

這些只是候選池，不可自動視為直接供應商：

| US ticker | 台股候選方向 |
| :--- | :--- |
| DELL | ODM/EMS、AI server、power、thermal：2382、3231、6669、2356、4938、2317、2308、3017、3324 |
| QCOM | smartphone/AP/RF/foundry/testing：2330、2454、3034、2379、2317，以及資料庫中的 RF/PA/封測供應鏈 |
| NVDA / AMD | foundry、CoWoS/advanced packaging、server ODM、power/thermal、memory/PCB：2330、2382、3231、6669、2308、3017、3324、3711、2449 |

若使用者要求 `quantitative`，才加入 rolling correlation；否則本節只做供應鏈與事件 read-through，不杜撰相關係數。

---

## 7. 常見失敗模式與禁止事項

1. 不可把正面措辭當作成長確定；必須檢查數字、訂單、客戶驗證、量產時程與是否已貢獻營收。
2. 不可把「沒有下修」直接判為正面；須相對前次財測與市場預期。
3. 不可把法人問題本身寫成公司事實。
4. 不可把管理層沒有否認視為確認。
5. 不可過度解讀單一語氣詞；需與數字、前季措辭、回答直接程度與財測範圍交叉判斷。
6. 不可重複同一資訊造成報告冗長；前段給結論，後段給證據。
7. 不可用固定科技股模板套所有公司；必須使用 sector-aware template。
8. 不可把 CapEx 增加一律解讀為正面。
9. 不可忽略 EPS 品質。
10. 不可保證股價漲跌；只能描述催化劑、風險、預期差、模型影響與估值可能方向。

---

## 8. 資料品質檢查與 Issue 回報

分析過程若發現資料來源問題，除了在 digest 標示，還需提交 GitHub Issue 至 `https://github.com/wenchiehlee-money/InvestorConference/issues`。

| 等級 | 定義 |
| :--- | :--- |
| Blocker | 會使財務結論錯誤或無法分析 |
| Major | 會明顯降低分析可信度 |
| Minor | 不影響主要結論，但應修正 |

應回報：字幕轉錄錯誤、簡報 OCR 缺漏、跨檔案不一致、檔案缺漏、Metadata 錯誤、KPI 口徑問題。

回報流程：執行 `lint_sources.py` 並輸出 `--issue-draft` 與 `--issue-json`；補充 LLM 判讀到的語意類錯誤；用 `gh issue list -R wenchiehlee-money/InvestorConference --search "{StockID} {Year} q{N}"` 查重；一季一 issue 或同公司多季同類問題合併；digest metadata 加註資料品質 issue 連結。

Issue sidecar JSON 格式：

```json
{
  "stock_id": "2357",
  "quarter": "2026_q1",
  "issues": [
    {
      "severity": "major",
      "file": "2357_2026_q1_FIN.srt",
      "location": "03:11",
      "type": "transcription_error",
      "description": "新臺幣被轉錄為新南幣"
    }
  ]
}
```

---

## 9. 輸出規範

輸出路徑：`InvestorConference/data/reports/conference-digests/{StockID}/{StockID}_{Year}_q{N}_digest.md`

報告開頭必須包含：

```markdown
# {StockID} {公司名稱} {Year} Q{N} 法說會重點萃取與分析

| 欄位 | 內容 |
|------|------|
| 股票代碼 | {StockID} |
| 季度 | {Year} Q{N} |
| 分析模式 | repo_only / enhanced |
| 市場模板 | auto / TW / US |
| 產業模板 | auto / 指定產業 |
| Correlation Mode | none / tw_readthrough / quantitative |
| 市場預期來源 | {來源；無則填 repo-only，未取得市場共識} |
| 資料來源 | {實際使用的檔案清單} |
| 字幕來源 | GT / FIN / 無 |
| 資料品質 Issue | {issue 連結，無問題則填「無」} |
| 分析日期 | {YYYY-MM-DD} |
```

之後依序輸出「零、投資決策摘要」與十三節。對話中回覆「零、投資決策摘要」精簡版、「十一、加權紅黃綠燈評分」整體結果、完整報告檔案路徑，以及 Blocker/Major 資料品質問題。

---

本檔案即為 `skill-investorconference-digest` / `conference-digest` 的標準化說明（`SKILL.md`）。
