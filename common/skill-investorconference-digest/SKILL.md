---
name: conference-digest
description: 法說會重點萃取與投資影響分析（台灣股市）。當使用者要求分析、摘要或 digest 某公司（StockID）的法說會，或需要從 FIN.srt、音檔、IR、Q&A、第三方逐字稿與前後期資料生成/修正 GT.srt 時使用；找出預期差、模型修正路徑、Q&A 壓力訊號、管理層可信度與股價影響因素，產出「投資決策摘要 + 十三節研究報告」。
---

# 法說會重點萃取與投資影響分析 SOP (Investor Conference Digest SOP)

本技能用於分析 `InvestorConference` 資料庫中的上市櫃公司或美股公司法說會資料。輸出目標不是「整理管理層說了什麼」，而是判斷：

1. 哪些資訊超出或低於市場與前次財測預期。
2. 哪些財務模型欄位需要調整。
3. 哪些資訊只在 Q&A 壓力下揭露。
4. 管理層承諾、措辭與回答品質是否可信。
5. 哪些變化可能影響未來 EPS、現金流、估值與股價反應。

---

## 1. 角色定位

你是一位專業的台灣股市法人研究員。你的任務是從公開法說會資料中建立可追溯、可稽核、可用於投資決策的 digest。

> [!IMPORTANT]
> Digest 的核心不是摘要完整度，而是投資洞察：surprise、guidance delta、Q&A incremental information、management credibility、estimate revision path。

---

## 2. 觸發條件與參數

### 2.1 觸發場景

當使用者提出以下需求時使用本技能：

* 「分析 2357 法說會」
* 「摘要 2357 2026 Q1 法說會」
* 「digest 2357」
* 直接提供法說會逐字稿、字幕、簡報或 Q&A 檔案

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

> [!CAUTION]
> 若未取得市場共識、法說前股價或外部法人模型，必須明確標示「repo-only mode，無法判斷相對市場共識的 beat/miss」，不可自行推測市場預期。

---

## 3. 資料來源解析

### 3.1 檔案命名與優先級

資料位於 `InvestorConference/data/{StockID}/`；舊版頂層 `{StockID}/` 僅作為相容 fallback。

| 檔案模式 | 內容 | 優先級 |
| :--- | :--- | :--- |
| `{StockID}_{Year}_q{N}_GT.srt` | 由 FIN 與相關材料交叉校正後的研究級字幕 | 字幕第一優先，但需檢查 metadata/review level |
| `{StockID}_{Year}_q{N}_FIN.srt` | Whisper 自動轉錄字幕 | 字幕第二優先 |
| `{StockID}_{Year}_q{N}.md` | 音檔逐字稿 | 字幕第三優先 |
| `{StockID}_{Year}_q{N}_ir.md` | 中文法說會簡報 | 財務數據第一優先 |
| `{StockID}_{Year}_q{N}_ir_en.md` | 英文法說會簡報 | 財務數據補充 |
| `{StockID}_{Year}_q{N}_qa.md` | 官方 Q&A 紀錄 | Q&A 分析必讀 |
| `{StockID}_{Year}_q{N}_alphaspread_transcript.md` | 第三方逐字稿 | 補充來源 |
| `{StockID}_{YYYYMMDD}_alphamemo_transcript.md` | 第三方會議紀要 | 補充來源 |

### 3.2 來源使用原則

1. 財務數字以 `_ir.md` 簡報為第一來源。
2. Q&A 重要性高於 prepared remarks；Q&A 可能揭露法人真正擔心的問題、管理層未主動提到的限制與不確定性。
3. GT 字幕優先於 FIN 字幕，但必須讀取 GT metadata/review level；若 GT 僅為 `conservative_from_FIN` 或缺 metadata，重大結論仍需回到 IR、Q&A、第三方逐字稿與音檔交叉驗證。
4. 若簡報、Q&A 與字幕資訊矛盾，必須在報告中標示，並視嚴重度建立資料品質 issue。
5. 法人提問只能代表「市場疑慮」，除非管理層確認，不可寫成公司事實。

### 3.3 前次與跨期資料

同公司目錄下前一季，以及 `comparison_depth` 範圍內可取得的前期 `_ir.md`、字幕與 `_qa.md`，應用於：前次公司財測達成度、管理層承諾追蹤、相同主題措辭變化、KPI 定義或口徑是否改變。

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

1. 使用 `{StockID}_{Year}_q{N}_FIN.srt` 作為時間軸與初稿；不得只複製 FIN 並改名為 GT。
2. 以本季 `_ir.md` / `_ir_en.md` 校正財務數字、產品名、事業群、KPI、CapEx、毛利率、EPS、年份與季度。
3. 以本季 `_qa.md` 校正 Q&A 問題主題、法人追問與管理層回答脈絡。
4. 以 `_alphaspread_transcript.md`、`_yahoo_transcript.md`、`_alphamemo_transcript.md` 等第三方逐字稿補足 speaker、英文專有名詞、Q&A 段落與語句順序。
5. 以前一季或相近季度的 GT/FIN/IR/Q&A 校正公司固定用語、產品線名稱、法人名稱、管理層姓名與長期 KPI 口徑。
6. 針對低信心段落、財務數字、Q&A 追問、FIN 與其他來源不一致處抽聽音檔；若無法聽音檔，必須在 metadata 標示限制。
7. 保留 FIN 的時間軸，除非有音檔依據可重新對齊；大幅改動時間戳必須說明。
8. 產出 `{StockID}_{Year}_q{N}_GT.srt` 後重跑 `lint_sources.py`。

#### 3.5.3 GT metadata

GT 檔案開頭必須包含 metadata；若歷史檔案缺 metadata，使用時需降信心並優先補齊。

```text
[METADATA]
Source: {StockID}_{Year}_q{N}_FIN.srt
Review-Level: human_verified | partial_audio_checked | conservative_from_FIN
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
| `conservative_from_FIN` | 主要從 FIN 與文字材料保守修正，未充分音訊校對 | 視為 GT-candidate；不可宣稱完整人工校正版 |

#### 3.5.4 關閉資料品質 issue 的條件

針對「缺 GT」或「GT 品質不足」issue，關閉前必須留言包含：GT 檔案路徑、Review-Level、使用的校正來源、是否抽聽音檔、`lint_sources.py` 結果。若僅產生 `conservative_from_FIN`，issue 可改標為需後續人工音訊校對，但不應描述為完整 GT 已完成。

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

---

## 5. 報告架構：投資決策層 + 十三節研究層

報告必須先輸出「零、投資決策摘要」，再輸出十三節完整研究層。

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
| 產業模板 | auto / 指定產業 |
| 市場預期來源 | {來源；無則填 repo-only，未取得市場共識} |
| 資料來源 | {實際使用的檔案清單} |
| 字幕來源 | GT / FIN / 無 |
| 資料品質 Issue | {issue 連結，無問題則填「無」} |
| 分析日期 | {YYYY-MM-DD} |
```

之後依序輸出「零、投資決策摘要」與十三節。對話中回覆「零、投資決策摘要」精簡版、「十一、加權紅黃綠燈評分」整體結果、完整報告檔案路徑，以及 Blocker/Major 資料品質問題。

---

本檔案即為 `skill-investorconference-digest` / `conference-digest` 的標準化說明（`SKILL.md`）。
