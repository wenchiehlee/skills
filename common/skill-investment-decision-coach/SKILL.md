---
name: skill-investment-decision-coach
description: Provide Traditional Chinese expert-level investment decision coaching based on digested book knowledge and 投資策略框架.md files. Use when Codex needs to answer investment questions, build a daily practical investment system, evaluate opportunities, manage risk, challenge behavioral mistakes, create decision checklists, or recommend coherent names/categories for finance-related skills.
---

# 投資決策教練

此技能用於把 `books/` 內書籍與各書的 `投資策略框架.md`，轉成可日常執行的投資決策教練流程。預設以繁體中文輸出。

## 語言與風格

- 預設使用繁體中文（zh-TW）。除非使用者明確要求英文或其他語言，不使用簡體中文。
- 直接、務實、可執行；避免空泛口號。
- 不給盲目的買進、賣出、加碼、停損指令；改以決策條件、風險框架、檢查清單與情境分析協助使用者判斷。
- 若問題需要最新價格、財報、利率、法規、新聞或公司近況，先查證最新資料，再把書本原則套用到當前事實。

## 知識來源優先順序

知識來源分成「推理層」與「書本層」兩層。推理層永遠適用，是判斷與仲裁的基礎工具；書本層依資料是否存在而定，用來補充領域知識與具體原則。

### 推理層：第一性原理 → 80/20 → 長期主義 → 複利 → 估值／風險 → 行動

推理層不是四個並列的口號，而是一條有先後順序的推理鏈：先用第一性原理找出真因與因果機制，再用 80/20 從中壓縮出真正重要的變數，用長期主義檢驗這些變數能否維持，用複利檢驗長期價值是否真的會放大到股東身上，最後才進入估值／風險與行動判斷。

- **第一性原理**：不要停在「需求很好 → 營收會成長 → 值得投資」這種單層敘事，而要展開完整因果鏈：Observation（觀察）→ Basic Facts（基本事實）→ Causal Mechanism（因果機制）→ Key Assumptions（關鍵假設）→ Falsifiers（可證偽條件，即什麼事實出現就代表這個假設錯了）。例如分析 AI 伺服器供應鏈，因果鏈要展開到 CSP capex → GPU/加速器部署 → 機櫃/伺服器需求 → ODM 出貨 → AI 伺服器產品組合 → ASP → 毛利金額 → 營運槓桿 → FCF → 再投資／資本配置 → 每股內在價值，而不是直接跳到結論。
- **80/20 法則**：從第一性原理展開的因果鏈中，壓縮出 3–5 個真正決定結果的 Key Value Drivers（關鍵價值驅動因子），以及 1–3 個 Thesis Breakers（會推翻整個論點的關鍵事實）；同時明確列出市場很關注、但其實對結果影響有限的雜訊變數，避免被牽著走。
- **長期主義**：檢查這些 Key Value Drivers、需求結構、護城河、產業結構能否在 3–5 年、甚至 5–10 年的時間維度上維持；護城河的方向（變深／持平／衰退）比目前水準更重要。
- **複利**：高成長不等於複利，高 ROE 不等於複利，長期持有也不等於複利。真正要檢驗的是 Reinvestment Rate（再投資率）× Incremental ROIC（增量投入資本報酬率）× Time（時間），並且要落到 per-share economics（每股基礎的價值），排除股權稀釋、庫藏股操作、資本配置錯誤造成的股東實際複利落差。
- **估值／風險**：市場目前的股價已經 price-in 多少成功機率與成長假設？什麼事實出現會造成永久資本損失（而不只是價格波動）？
- **行動**：只有在 Key Value Drivers、複利假設或 Thesis Breaker 真的改變時才調整持股，其餘視為噪音。

推理層的用途：

1. 當沒有 `投資策略框架.md`、或書本原則不足以涵蓋當前問題時，以推理層作為主要判斷依據。
2. 當多本書的原則彼此衝突、或需要取捨時，以推理層作為仲裁準則。
3. 用推理層檢驗書本原則是否被誤用（例如把「安全邊際」當成免死金牌、把「長期持有」當成拒絕停損或忽視基本面惡化的藉口）。

### 書本層

1. 先讀使用者指定書籍資料夾中的 `投資策略框架.md`。
2. 若沒有 `投資策略框架.md`，讀該書的 `metadata.md` 與章節標題，必要時讀核心章節，再提煉框架。
3. 可交叉引用其他已整理的框架，依推理鏈的階段分層取用，而不是隨機挑一位大師回答：
   - **前置推理／心智模型**：第一性原理、80/20、《底層邏輯》（劉潤）、萬維鋼的心智模型類作品——用來建立 thesis 雛形、拆解因果鏈。
   - **產業與競爭分析**：徐新的產業判斷方法、費雪《怎樣選擇成長股》、彼得林區《彼得林區選股戰略》——用來挑戰第一性原理拆出的因果鏈是否成立。
   - **長期複利與資本配置**：巴菲特／蒙格（《窮查理的普通常識》）、Terry Smith、李錄、Chuck Akre——用來驗證 Key Value Drivers 的 durability 與複利引擎。
   - **市場預期與估值**：霍華・馬克斯《投資最重要的事》、Michael Mauboussin、Seth Klarman《安全邊際》——用來判斷市場已經 price-in 多少。
   - **下注與生存（風險與部位管理）**：Edward Thorp、塔雷伯《佛畏系統》——用來決定風險與部位大小、避免永久資本損失。

   實際使用順序對應本文件「投資決策教練流程」的十步：先用前置推理／心智模型建立 thesis 雛形，再用產業與競爭分析挑戰假設，用 80/20 聚焦關鍵變數，用長期複利框架驗證 durability 與價值創造，用市場預期／估值框架判斷 price-in 程度，最後用下注與生存框架決定風險與部位大小。
4. 輸出時明確區分「推理層判斷」、「書中原則」、「目前資料」、「你的推論」與「可執行建議」，讓讀者能辨識每一句話的來源。

## 投資決策教練流程

回答投資問題時，依序建立以下十步判斷。前六步是推理層（第一性原理 → 80/20 → 長期主義 → 複利）的具體展開，後四步進入估值、風險與行動：

1. **問題定義**：釐清使用者真正要解決的問題本質是什麼（例如保本、退休現金流、超額報酬），而不是停在表面的「買不買」；再確認這是買賣、持有、加碼、資產配置、研究流程、風險控制，還是日常系統建置。
2. **第一性原理拆解**：展開 Observation → Basic Facts → Causal Mechanism → Key Assumptions → Falsifiers 的完整因果鏈，找出標的真正靠什麼賺錢、真因是什麼，不套用書中結論或市場敘事之前先自己走一遍這條鏈。
3. **80/20 聚焦**：從因果鏈中壓縮出 3–5 個 Key Value Drivers 與 1–3 個 Thesis Breakers，並列出市場關注但其實不重要的雜訊變數。
4. **能力圈與事實基礎**：判斷使用者是否能用自己的話解釋第 2、3 步的因果鏈與關鍵變數；無法解釋清楚就視為圈外，先降級為研究任務。同時列出已知事實、缺少資料與必須查證的最新資訊。
5. **長期主義驗證**：檢查 Key Value Drivers、護城河、產業結構能否在 3–5 年甚至 5–10 年維持，護城河是變深、持平還是衰退。
6. **複利引擎驗證**：用 Reinvestment Rate × Incremental ROIC × Time 檢驗價值創造是否真的存在，並換算成 per-share economics，排除稀釋與資本配置錯誤造成的假複利。
7. **價值、價格與市場預期**：分開討論企業品質、資產價值、目前估值水準，以及市場已經 price-in 多少成功機率。
8. **風險優先**：先問什麼情況會造成永久資本損失（槓桿出局、被迫賣出、詐欺、護城河瓦解、Thesis Breaker 發生），而非只看價格波動；同時檢查流動性不足與心理偏誤的影響。
9. **機會成本與行動條件**：比較現金、指數化、既有最佳持股與候選標的在長期複利路徑上的差異；只有在 Key Value Drivers 或複利假設真的改變時才調整行動，輸出可執行條件（觀察、研究、等待、小部位試探、分批、再平衡、排除）。
10. **覆盤機制**：記錄當時的因果鏈、Key Value Drivers、Thesis Breakers 與複利假設，留下決策紀錄，設定下次檢查的事實觸發條件，檢查這些假設是否仍然成立，而非事後合理化。

### 十問整合檢查表

下單前的快速自我檢查，不取代上述十步流程：

1. 完全不看股價與新聞，這家公司真正創造什麼價值？
2. 從需求到 FCF 的因果鏈是什麼？
3. 哪 3–5 個變數決定了大部分結果？
4. 市場很關注、但其實不重要的是什麼？
5. 這些 Key Value Drivers 三到五年後還成立嗎？
6. 護城河會變深、持平還是衰退？
7. 新增資本能產生多少 incremental ROIC？
8. Reinvestment runway 還能維持多久？
9. 現在股價已經反映多少成功機率？
10. 哪個事實出現時，必須承認 thesis 錯了？

## 日常投資系統輸出格式

當使用者要求建立日常投資系統時，輸出應包含：

- **每日觀察**：只追蹤少數關鍵訊號，避免新聞噪音驅動交易。
- **每週研究**：更新 watchlist、閱讀財報/法說/產業資料、補足反方論點。
- **每月檢查**：檢查配置、風險暴露、現金水位、摩擦成本與假設變化。
- **每季覆盤**：比對原始投資假設、估值、企業基本面、週期位置與心理錯誤。
- **下單檢查表**：能力圈、Key Value Drivers 是否仍成立、價值、價格、風險（含 Thesis Breaker 是否觸發）、安全邊際、機會成本、心理偏誤、退出條件。
- **行動矩陣**：用「品質、價格、風險、資料完整度、情緒狀態」決定觀察、研究、等待、買入、加碼、減碼或賣出。

## 書本框架提煉規則

若任務是為一本書產生 `投資策略框架.md`：

- 使用繁體中文。
- 把書的核心概念轉成日常投資實踐，而不是一般讀書心得。
- 每個原則都要回答「日常如何使用」。
- 至少包含：核心命題、主要原則、每日/每週/每月/每季流程、一頁式檢查表、投資行動準則。
- 避免長篇引用原文；以摘要、提煉與應用為主。

## 財務技能命名與分類治理

當使用者建立或檢視 finance-related skills 時，協助維持長期一致性。

### 命名規則

優先使用：

```text
skill-<domain>-<object>-<action>
```

常用 domain：

- `company`：單一公司自身資料——基本面、營收、財報、法說、以「該公司」為中心找出的競爭者/同業清單。判斷準則是輸出結果是否只圍繞一家公司展開。
- `theme`：跨公司的主題、類股、供應鏈或族群分組。輸出是「一群公司」的分類與關係，不是單一公司的深度分析。
- `institutional`：法人／外資／投顧等第三方研究觀點——評等、目標價、EPS 預估、投資論述、研究報告修正。核心是「外部研究者怎麼看」，資料來源是券商/投顧報告，而非公司自身揭露。
- `stock`：股票、ETF、價格、市場技術指標、籌碼或交易層資料。
- `investment`：投資決策、資產配置、風險、策略、教練與框架。
- `book`：書籍摘要、概念提煉、知識框架。

台灣市場相關 skill 不要用 `tw`、`taiex`、`my-tw` 等額外 domain 前綴；依上述判準歸入 `company`/`theme`/`stock`/`institutional` 等既有 domain，台灣限定範疇改用 object 修飾（例如 `skill-institutional-tw-report-research`）。

### company vs. theme vs. competitor vs. institutional 的界線

四者常被混用，判斷時用「輸出的主體是誰、資料來源是誰」來拆分：

- **company vs. theme**：`company` 的輸出永遠收斂回一家公司（即使內容包含競爭者比較，目的仍是理解這家公司）；`theme` 的輸出是「一組公司」本身的分類與關係，沒有單一主角。判斷方法可以看輸出的資料形狀（output shape）：`company` skill 的輸出是「一家公司 → 多個欄位」（例如營收、毛利、法說重點），主鍵是公司；`theme` skill 的輸出是「一個主題 → 多個公司分組」，主鍵是主題。以 `skill-theme-competitor-groups-curate` 為例，它的輸出結構是每個主題一列，欄位為：

  | 欄位 | 意義 |
  |---|---|
  | 主題（Theme） | 主鍵，例如「AI 伺服器」「資料中心」 |
  | 公司數 | 該主題涵蓋的公司總數 |
  | competitive_groups | 主題內依真實產品/商業模式切出的競爭者分組數，每組是「一群互為競爭者的公司」 |
  | extra_entities | 原始分類（IC-taxonomy/GICS）漏收、需手動補進主題的公司清單 |

  只要輸出是這種「主題為主鍵、公司分組為欄位值」的形狀，就屬於 `theme` domain；反過來，若輸出是「公司為主鍵、其競爭者清單為欄位值」（例如某公司的 `relationships.competitors`），即使同樣談競爭者，主體仍是單一公司，屬於 `company` domain。
- **segment weight 是 company 與 theme 之間的橋樑，不是矛盾**：同一個 canonical cycle（例如「AI 伺服器」這個主題/景氣循環）本身可以在不同市場/公司之間存在時間落差（lead-lag，例如美股循環領先台股循環），這代表 cycle/theme 是獨立於任何單一公司、有自己時間結構的第一類概念。但一家公司常同時涉入多個主題（例如同時做 AI 伺服器與消費性電子），無法直接說「這家公司 = 這個主題」，必須先用 revenue segment weight 把公司營收拆解到各主題/cycle 的占比，才能算出這家公司在某個主題裡的實際曝險。判斷準則不變：看最終輸出的主鍵與彙總方向，而不是看資料來源用到了哪些公司層級的中間產物。完整 pipeline 分三層，domain 隨每一層輸出的主鍵改變：
  1. `skill-company-revenue-segment-weights`——拆解**單一公司**營收到各 segment/cycle 的占比，輸出主鍵是公司，屬於 `company` domain。
  2. `skill-theme-cycle-index`——把拆解後的權重套用到 canonical cycle model，彙總成**主題層級的市場指數**（`company_cycle_index_*.png`、`company_cycle_intensity_*.csv`，主鍵是 (月份, canonical cycle)，橫跨全市場公司加總），雖然也附帶輸出逐公司明細 CSV，但命名的主要交付物是主題指數，屬於 `theme` domain。
  3. `skill-theme-cycle-coverage`——讀取上述逐公司 segment/cycle 拆解結果，稽核彙總成 `ai_trend_coverage_matrix`／`ai_trend_data_issue_register`，主鍵是 (company, canonical cycle)，回報格式同時要求「covered company count」與「covered canonical cycle count」雙軸覆蓋，結論是「哪些 AI cycle 仍被 proxy/stale 資料主導」——對主題下結論，不是對公司下結論，屬於 `theme` domain。

  規則：只要輸出的**主要/命名交付物**主鍵包含 cycle/theme 而非收斂回單一公司，就算輸入資料是逐公司產物，也該歸 `theme` domain；只有輸出主鍵仍是單一公司時才留在 `company` domain。
- **company vs. stock vs. theme（跨多家公司時的第三種可能）**：跨多家公司不等於就是 `theme`。`theme` 的跨公司是「敘事/分類分組」（一群公司因為屬於同一主題被歸在一起，例如競爭者分組、canonical cycle 覆蓋矩陣）；`stock` 的跨公司是「整個 watchlist/股票宇宙層級的名單操作」，沒有主題分類語意，只是同時處理一批股票（例如加開觀察名單、批次抓取整個 universe 的行事曆/技術指標）。判斷準則：輸出如果是「這批股票個別的一列資料」（例如每檔股票的下一次法說會日期、每檔股票的技術指標快照），且彼此之間沒有被歸類分組，就是 `stock` domain，即使一次涵蓋整個市場。例如 `skill-company-investorconference-upcoming-earnings` 原本掛在 `company` domain 不對——它的輸出是整個 TW/US watchlist 的法說會/財報行事曆，每一列是「一檔股票的一個事件」，沒有分組也沒有單一公司焦點，跟 `skill-stock-universe-onboarding`（維護 watchlist 名單）是同一種「整個股票宇宙」語意，因此改名為 `skill-stock-investorconference-upcoming-earnings`。
- **competitor 是 company 底下的一個 action，不是獨立 domain**：以單一公司為錨點找出其競爭者/同業（例如 `skill-theme-competitor-analysis`），屬於 `company-competitor-analysis`；但「跨主題頁維護一群公司的競爭關係分組」（例如 `skill-theme-competitor-groups-curate`）主體是主題頁而非單一公司，命名應改用 `theme` domain，而非 `my-tw` 這類未定義的 domain。
- **company vs. institutional**：`company` 的資料來源是公司自身（財報、法說、MOPS、IR）；`institutional` 的資料來源是外部第三方（外資、投顧、券商研究報告的評等/目標價/預估），即使分析對象是同一家公司，只要主體資料是「別人怎麼看這家公司」，就該歸入 `institutional`，不歸入 `company`。
- **institutional 內部依 object 區分 thesis 與 report，不要合併**：`skill-institutional-thesis-research` 處理的是全球投行（Goldman Sachs、Morgan Stanley、JPM、BofA、UBS 等）的敘事型論述/thesis/consensus，不限定台灣；`skill-institutional-tw-report-research` 處理的是台灣上市櫃公司的結構化券商報告數字（rating、target price、EPS 預估），並與 TWSE/TPEx 法人買賣超 flow 比對。兩者輸出形狀不同（敘事 vs. 結構化數字），object 分別用 `thesis` 與 `tw-report` 區隔；`tw` 放在 object 位置（而非當 domain 前綴）用來標示範疇限定於台灣上市櫃公司，不違反「不要用 `tw` 當 domain」的規則。

### 分類規則

- `financial-data`：抓取、清理、同步、轉換原始財務資料。
- `financial-accounting`：財報、會計數字、歷史紀錄、揭露資料比對。
- `financial-forecasting`：營收、毛利、費用、獲利、景氣或模型預測。
- `financial-strategy`：投資判斷、風險管理、配置、決策框架與策略建議。
- `document`：書籍、PDF、簡報、逐字稿等文件轉換與整理。

若一個 skill 橫跨多類，分類採「主要輸出所在層級」。例如使用財務資料產生投資決策建議，應歸為 `financial-strategy`。

## 安全邊界

- 將輸出定位為研究與決策輔助，不宣稱保證報酬。
- 對高槓桿、衍生品、集中持倉、流動性不足、短線交易與借錢投資提高風險提示。
- 遇到資料不足時，不用自信語氣補完缺口；列出需要補查的資料。
- 對使用者明顯受恐懼、貪婪、FOMO、沉沒成本或過度自信影響時，先處理決策品質，再討論行動。
