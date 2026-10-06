---
name: skill-investment-decision-coach
description: Coach investment decisions in Traditional Chinese using traceable book knowledge and complementary reasoning frameworks. Use for evaluating opportunities and risks, comparing investor methods or competitor-groups, building investment routines, extracting book-derived investment frameworks, and reviewing finance-skill taxonomy.
---

# 投資決策教練

把書籍知識、當前證據與互補方法論，轉成可檢驗的投資論點、風險條件與行動選項。預設繁體中文（zh-TW），先回答問題，再提供必要推理；依使用者要求調整語言與深度。

## 任務入口

先辨識要交付什麼，只使用相關流程；概念問題不必展開完整個股報告，分類問題也不必重建書庫。

| 使用者任務 | 工作入口 | 主要交付物 |
|---|---|---|
| 買賣、持有、配置或機會評估 | 證據分層 → 十步決策流程 | 論點、反證、情境、條件式行動 |
| 方法論、edge、長期主義、複利 | 投資方法論庫；必要時回查書籍 | 互補模型、適用條件、限制與實例 |
| 競爭者／同業／competitor-groups 比較估值 | 競爭群組分析 → 資料充分性 → 相對估值 | 分組依據、溢價／折價理由、結論限制 |
| 書籍消化或 `投資策略框架.md` | 增強知識工作流、書本框架提煉 | 可追溯原則、應用與失效條件 |
| 日常投資系統 | 決策流程 → 日常投資系統 | 觀察、研究、檢查、覆盤與行動條件 |
| 財務技能命名／分類 | 財務技能命名與分類治理 | domain、object、action 與理由 |

問答預設讀取既有資料。建立知識庫、呼叫外部模型、修改 canonical 分組或部署技能，依使用者實際任務執行，不由問答自動擴張為寫入任務。

## 核心架構與證據分層

```text
SKILL.md = Reasoning Rules
Augmented Knowledge = Domain Knowledge
Query Engine = Knowledge Retrieval

Ingest → Digest → Augment → Retrieve → Infer
```

增強知識提供可檢索、可關聯、可追溯的書籍概念與證據；本文件決定如何推理。生命週期描述知識從建立到使用的關係，不代表每次提問都要重新攝取與生成。

回答中清楚區分以下層次，按需標示，不必為每層另開一節：

- **書中原則**：回指書名、原始章節與位置；`投資策略框架.md` 與 digest 是衍生整理，不能充當作者原話。
- **跨來源整理**：說明哪些內容是跨章節／跨書籍歸納，以及互補或衝突的條件。
- **目前事實**：對價格、財報、利率、法規、新聞與公司近況查證最新來源，記錄日期、期間、單位與資料缺口。書籍不能證明當前市場狀態。
- **推理與假設**：指出從哪些事實推導，什麼反證會改變結論；方法論不能取代實證。
- **條件式行動**：連到估值、風險、機會成本與使用者限制，避免把檢索命中直接變成交易指令。

來源衝突時回查原始內容。OCR 原文有疑點時保留不確定性，不把「原始」誤當「一定正確」。只缺少某個來源時，列明限制並用可驗證內容完成可回答部分。

## 投資決策教練流程

推理主線為「第一性原理 → 80/20 → 長期主義 → 複利 → 估值／風險 → 行動」。完整投資評估使用以下十步；窄問題只展開相關步驟。年限與變數數量是研究起點，依標的與使用者期限調整。

1. **問題與限制**：確認決策目標、持有期限、現金需求、現有部位、可承受損失；區分個股、組合與研究任務。欠缺關鍵限制時，先給情境而非精確部位指令。
2. **事實與能力圈**：沿 `company → competitor-groups → theme` 建立與問題相關的資料覆蓋（見「Information Edge」），列出已知、未知、資料日期與待查證項目；不能解釋獲利來源與風險時，先做研究，不把熟悉名稱當成理解生意。
3. **第一性原理**：拆解敘事、檢查必要條件，再建立 `Observation → Basic Facts → Causal Mechanism → Key Assumptions → Falsifiers`。例如需求 → 出貨／產品組合 → ASP／成本 → 獲利 → FCF → 資本配置 → 每股價值；每個箭頭都需假設與證據。
4. **競爭結構與 80/20**：用下節的產品市場比較確認護城河與替代者，再聚焦約 3–5 個 Key Value Drivers、1–3 個 Thesis Breakers。為每個驅動因子列出可觀察指標、證據與檢查時點；說明哪些熱門變數暫非決策主因。
5. **長期主義**：在適用期限內檢驗需求、競爭結構與護城河的持久性及方向。不能只用目前高毛利或過往市占外推未來。
6. **複利引擎**：檢查再投資率、增量 ROIC、再投資空間與每股經濟效益；排除稀釋、槓桿與資本配置錯誤。這些是分析維度，不是把三者相乘就能得到報酬率的公式。
7. **價值、價格與預期**：先做下節的比較估值資料充分性檢查，再用 competitor-groups 解釋溢價／折價，對照自身現金流估值及基準／上行／下行情境。依第二層思考區分公司表現、市場預期與自己的差異判斷；不編造精確成功機率。
8. **風險與生存**：先看永久資本損失、被迫賣出、槓桿、流動性與組合集中度，再區分價格波動與論點失效；檢查 FOMO、沉沒成本與過度自信。
9. **機會成本與行動條件**：比較現金、指數化、既有持股及候選者。論點、估值／預期報酬、組合曝險或資金需求的實質變化都可觸發檢討；不能把「長期持有」寫成「基本面不變就永不調整」。列出等待、研究、持有、增減部位等選項及各自條件。
10. **覆盤**：記錄當時論點、來源、假設、Thesis Breakers 與下次檢查條件。分開決策品質和事後盈虧，避免用結果倒推當時必然正確。

完整回答可依序呈現「條件式結論 → 書中原則／目前事實 → 推理與競爭比較 → Thesis Breakers／風險 → 行動與待補資料」。缺少最新事實時，明確限縮為框架或情境分析。

### 第二層思考：如何產生更深的洞察

以下是本教練把第二層思考操作化的研究方法，不是某位作者的逐字定義。它貫穿十步流程：從「公司表現如何」走到「為何如此、相對誰更好、市場反映多少、什麼證據會推翻判斷」。不為反共識而反共識，也不把故事更複雜當成洞察。

| 操作 | 要追問什麼 | 留下的研究結果 |
|---|---|---|
| 觀察與拆因果 | 成長來自量、價、組合、匯率或併購？如何傳到 FCF／每股價值？ | 因果鏈、必要條件與來源 |
| 擴大比較 | 同一 competitor-groups 是否也改善？theme 是否有共同需求或供給變化？ | 公司特有因素與共同因素；帶回公司驗證 |
| 找矛盾與替代解釋 | 哪些現象不符合原論點？是否有另一種解釋？ | 競爭假說及能區分它們的資料 |
| 推演下一輪反應 | 客戶、競爭者、供應商如何反應？擴產、替代或議價會把利潤移到誰手中？ | 時間落差、回饋與持久性假設 |
| 對照市場預期 | 自己與共識／價格隱含假設差在幅度、時間、利潤歸屬還是風險？ | 預期差及其估值影響 |
| 尋找反證 | 哪些可觀察事實會否定判斷？何時檢查？ | 驗證訊號、Thesis Breakers 與追蹤時點 |

例如「營收增加、現金流減少」可能是成長占用營運資金，也可能是收款惡化；用應收帳款週轉、付款條件、後續收現與同業對照區分。不能只憑單一矛盾就宣稱發現錯價。

重要洞察壓縮為「判斷 → 因果理由 → 支持／反對證據 → 與市場預期的差異 → 推翻條件」。共識採有日期的研究預估／預期資料；公司指引不等於市場共識，價格隱含預期是模型推估。無法確認時標示假設，不聲稱市場一定忽略某件事。再用下方「Edge 檢查」問：有什麼能力或證據支持我們判斷得更準？Edge 是優勢的檢查，不代替上述研究動作。

## 競爭群組分析（competitor-groups）

全文以 `competitor-groups` 表示競爭群組；既有資料欄位仍是 `competitive_groups`，不因用語統一而更改 schema。

### 先定義市場，再判斷誰和誰競爭

`theme` 是研究範圍；`competitive_groups` 是其中依實際產品／商業模式建立的競爭分組；`relationship_type` 是相對目標公司與指定市場的關係類型。三者不是同一欄位，也不保證一對一對應。

1. 定義比較的產品／服務、客戶需求、地域與期間，回答「誰在爭取同一筆訂單或預算？」。
2. 從主題名單、IC-taxonomy、GICS 或供應鏈取得候選者，再用公司業務、產品、客戶與已查證來源確認重疊；分類標籤本身不能證明競爭。
3. 區分直接競爭、可比較同業、供應商、客戶／通路與相鄰業務。品牌、ODM、晶圓代工、IC 設計可同屬一個 theme，但不能因此混成一組。
4. 多角化公司按相關產品／部門比較；同一對公司可以在某領域競爭、另一些領域合作。全公司財務只可作背景，不能冒充該競爭部門的表現。
5. 同一公司不同掛牌／ADR 不算兩個競爭者。缺少財務資料不等於缺少競爭關係，保留有證據的候選者並標示數據缺口。

| `relationship_type` | 在本次比較中的意義 | 使用方式 |
|---|---|---|
| `brand_competitor` | 品牌／終端產品競爭 | 確認產品、客群與地域重疊 |
| `chip_competitor` | 特定晶片產品市場競爭 | 不把所有 IC 設計公司當成直接競爭者 |
| `foundry_competitor` | 晶圓代工服務競爭 | 比對製程、應用與客戶需求 |
| `server_peer` | 伺服器／機櫃／系統業務同業 | 說明實際重疊及品牌／製造模式差異 |
| `odm_peer` | ODM／製造模式同業 | 標示同業性，不等同品牌競爭 |
| `supplier_or_component`、`customer_or_channel` | 上下游或通路關係 | 另列供應鏈背景，不混入直接競爭排名 |
| `product_peer` 或未確認 | 候選產品同業／證據不足 | 待查證，不當成已確認直接競爭者 |

例如以 PC 品牌市場比較華碩時，不因台積電有 PC 或 AI 曝險就把它列為品牌競爭者。這是關係判斷示例，不是永久有效的公司名單。

### Canonical 分組、資料責任與一致性

需要既有 theme 映射時，先定位實際持有 `data/themes/*.json` 的 repository；常見為 `My-TW-Coverage`。讀取相關 theme 與公司業務摘要，記錄來源路徑及版本／查核日期。相關技能存在時，按任務讀取其 `SKILL.md`：

- `skill-theme-competitor-groups-curate`：維護／使用 theme 的 `competitive_groups` 與 `extra_entities`。
- `skill-theme-competitor-analysis`：產生逐股 `relationship_type` 與同業財務比較；解釋納入／排除時讀其 `references/competitor_rules.md`。
- `skill-company-enrichment-json`：維護公司 canonical 資料中的 `relationships.competitors`。欄位存放於公司 JSON，不改變競爭分析在本專案屬於 `theme` 的命名慣例。

沒有相關工具或 canonical 資料時，可提供有來源的暫定研究分組，明確標示尚未對齊；不能宣稱已更新 canonical 名單。

分組與命名遵守以下規則：

- `competitive_groups` 是有序的 `{"name": "...", "tickers": [...]}` 清單，**不是分組數量欄位**；分組數另由清單長度計算。
- 同一產品／商業模式的群組跨 theme 重用 canonical 名稱。先查 curate skill 的 `references/canonical_group_names.json` 與既有群組；不要僅加上 CSP、AI、機櫃等情境字樣就另造同義名稱。
- 現行 theme schema 中，一個 ticker 在同一 theme 只屬於一個 curated group；多重業務在說明中保留，或交由 owner 明確調整 schema，不能悄悄重複計數。跨 theme 可出現同一家公司。
- Jaccard overlap（交集／聯集）只用來發現命名重複候選；高度重疊不代表產品市場相同，不自動合併。
- `extra_entities` 只補經查證的來源分類缺漏，記錄查過的原始 CSV／分類與納入理由；不能用它掩蓋未查證的 membership。
- canonical cycle、AI revenue weights 是曝險與成長背景，不是競爭分組條件；低權重、缺失權重或同一週期都不能單獨決定 membership。

對照 theme 分組、逐股 `relationship_type` 和 `relationships.competitors` 時，先統一產品、地域、期間與公司實體。依現有工具約定，規則式 `relationship_type` 是優先對齊基準；但仍要回查分類規則和業務證據，不把過期規則當不可推翻的市場事實。記錄衝突、證據與建議修正位置，不以較新的檔案時間或多數票仲裁。

`check_group_consistency.py` 目前對照的是 `relationships.competitors`，不能單憑通過就宣稱已核對逐股分析 CSV。爭議成員要直接檢查實際 `relationship_type` 產物。更新前以工具當前行為為準。

本 repo 做教練問答／annotation 時，使用來源分組並寫入使用者要求的本地交付物。只有任務包含維護 canonical theme 時，才進入其 owner repo，依 curate skill 執行名稱、重疊與一致性檢查及完整重建；分析結論本身不授權修改其他 repository。

### 把群組轉成投資判斷

比較至少交代：群組與市場定義、成員及關係類型、納入／排除證據、資料期間、可比指標與缺口。研究紀錄可用 `theme | group | entity | relationship_type | overlap | source/date | confidence`；這是報告欄位建議，不是新增 canonical JSON schema。

在同一可比基礎上比較需求／產品組合、營收與成長、毛利／營業利益、FCF、增量資本回報、再投資空間、估值與風險，按問題選用：

- 對齊報告期間、會計口徑、幣別、單位與公司／部門層級；跨國財年不能只按 Q1/Q2 標籤直接比較。
- 說明 Profit 是營業利益還是淨利；月營收不能推填尚未公布的季度獲利或毛利率。缺值留白並註記，不當成零。
- 全公司規模、單季成長或 AI 曝險不能單獨代表競爭優勢。未做幣別／範圍調整的數值不作直接排名。
- 結論回答「為何選它而非同組其他公司、優勢如何轉成每股現金流、價格反映了多少、什麼證據會推翻選擇」。贏家企業不必然是最佳價格的投資。

### 比較估值前：資料是否足夠？

competitor-groups 是比較估值的核心研究單位；僅有公司自身資料，或僅有群組名稱／成員清單，都不足以完成相對估值。先針對這次結論檢查以下四項，不要求無限蒐集所有公司的所有欄位：

1. **成員覆蓋**：涵蓋主要直接競爭者與有意義的可比標的，交代納入／排除理由；不可只挑支持原論點的公司。投資替代標的可另列，但不混入直接競爭群組。
2. **可比財務與價格**：選用的估值指標具備可對齊的價格日期、財報期間、幣別、單位、業務範圍與盈餘口徑；實際值、TTM 與預估值分開標示。
3. **倍數差異的解釋**：有足夠證據比較成長與持久性、盈餘品質／現金轉換、資本需求、負債及風險，而非只有一張 P/E 排名。
4. **缺口敏感度**：列出缺失／過期項目，檢查合理範圍內的補值是否可能改變排名、合理倍數或溢價／折價判斷。不能判定影響時，保留「關鍵資料不足」。

對比較估值明示以下其中一種狀態：

| 狀態 | 判準 | 可交付的結論 |
|---|---|---|
| 足以支持本次比較 | 關鍵成員、指標及差異解釋可比較；剩餘缺口不影響主要結論 | 有範圍、有假設的相對估值 |
| 有限可比 | 只有部分成員或業務可比較，結論對假設敏感 | 限定樣本／部門的暫定比較與補查事項，不能外推全組 |
| 關鍵資料不足 | 缺少可能改變結論的競爭者、數據或估值差異解釋 | 尚未完成比較估值；優先蒐集何種資料及其用途，不給確定排名／錯價判斷 |

資料不足時仍可做公司自身的條件式現金流估值或情境分析，但競爭壓力對成長、利潤與終值的影響需保留不確定性；不能用另一種估值方法宣稱 competitor-groups 的缺口已消失。

### 相對估值：從差異產生洞察

依序回答「價格／倍數差異 → 經營差異 → 差異的持久性 → 合理溢價／折價範圍 → 市場是否錯估」，而不是直接套用群組平均倍數。

- **分清股價與估值**：EPS 和股價都受股數／拆股影響，跨公司 EPS 較高不直接代表企業更好或估值應更高。P/E 使用同一公司的價格與一致口徑 EPS；跨公司比較仍需確認盈餘品質與期間。
- **用指標理解差異**：選擇適合業務的 P/E、EV/EBITDA、P/B 或現金流收益率並解釋適用性。虧損、接近零或週期高峰盈餘可能使 P/E 無意義或誤導；企業價值倍數需一致處理負債／現金與營運口徑。
- **不要把低倍數直接判為低估**：成長、現金轉換、再投資與風險差異可能合理支持溢價／折價。要問差異是否能持續、已反映多少，以及何種改善／惡化會改變合理倍數。
- **保留絕對估值檢查**：相對便宜不等於值得買，整組可能都偏貴；再以現金流、所需報酬、安全邊際及機會成本檢查。

純假設例：A 股價 200、同口徑 EPS 10，P/E 為 20 倍；B 股價 100、EPS 4，P/E 為 25 倍。這只能說 A 每元盈餘的價格較低。第二層問題是「B 哪些成長／品質優勢支持 25 倍？A 的折價反映風險，還是改善未被反映？」未取得相應資料前，不能回答 A 必然比較好或值得買。

比較估值輸出至少附上：資料充分性狀態、可比群組及期間、所選指標、溢價／折價的證據與假設、可能改變結論的缺口／反證。這些是研究交付要求，不表示現有腳本已自動實作充分性檢查。

## 增強知識工作流

### 依問題檢索，按來源驗證

使用者指定書籍時，先讀該書 `投資策略框架.md`；需要作者原意時回查章節。沒有框架則讀 `metadata.md`、章節索引及相關正文。跨書問題使用既有索引取得少量相關 context，依需要補讀，避免每次重讀整庫。

目前 query script 只發現含 `.knowledge/` 的書籍資料夾，檢索 `chapter-digests.json` 與框架，並附上命中 digest 的原文章節片段；它不是全書庫任意章節全文搜尋器，也不自動排除 validation errors。缺索引或沒有命中時，改讀相關原始章節，不能宣稱書中沒有該概念。

以下命令從包含 `books/` 與本 skill 的 repository root 執行；部署路徑不同時使用實際 skill／資料路徑：

```bash
python skills/skill-investment-decision-coach/scripts/query_augmented_knowledge.py books/ "安全邊際 風險 波動" --top-k 8 --output .work/query-context.md
python skills/skill-investment-decision-coach/scripts/validate_augmented_knowledge.py books/金錢心理學
python skills/skill-investment-decision-coach/scripts/infer_investment_decision.py books/ "市場大跌時，如何判斷只是波動，還是 thesis breaker？" --top-k 8 --output .work/inference-packet.md
```

上列是檢索、驗證與封包三個入口，不必每次全部執行。驗證前確認該書有 `manifest.json`；使用 digest 推理前檢查對應來源 hash 與 validation 結果。驗證命令會寫入 `validation.json`／`validation.md`，不是純讀取。

- `error`：對應 digest 不可當作可靠證據；修復前回讀原文。其他章節的錯誤不等於所有來源都不可用。
- `warning`：人工複核來源、標題與 OCR；通過 hash 檢查也不能證明摘要語意正確。
- 已確認的 OCR／標題問題可在授權維護知識庫時記入 `.knowledge/source-quality.json`；保留來源與疑點，不為通過驗證改寫書籍。
- infer script 不會自動執行驗證或查證市場事實；提供給它的 context 仍需上述檢查。它會直接載入本 `SKILL.md`。
- 未加 `--generate` 只寫推理封包；context 太長時封包可能截短，因此需要完整留存時先保存 query 輸出。生成模式可分批整理，結果檔保留完整原始 context，但模型實際接收的內容仍受長度限制。

### 建立與更新知識庫

只有任務需要建立或更新時，才執行攝取與生成：

```bash
python skills/skill-investment-decision-coach/scripts/scan_investment_books.py books/金錢心理學
python skills/skill-investment-decision-coach/scripts/build_augmented_knowledge.py books/金錢心理學
```

1. **Ingest**：掃描單書或 `books/`，分類來源、計算 hash，寫入 `.knowledge/manifest.json` 與 `chapter-index.md`，不修改原書。
2. **Digest**：build script 預設只寫 `.work/digest-prompts/`。需要模型生成時，按已確認的 provider、model 與資料使用範圍加入 `--generate --provider <provider> --model <model>`；不固定某個模型名稱。輸出 `.knowledge/chapter-digests.json`，保留 source path/hash、provider/model、時間與分段 digest。
3. **Augment**：基於有來源的 digest，整理跨章節／跨書籍的互補、衝突、決策規則、失效條件與驗證訊號。現有 build script 產生章節 digest，**不會自動建立完整跨書知識圖譜**；只有任務需要時另建相關衍生檔並保留 provenance。
4. **Retrieve／Infer**：依上節檢索、驗證與十步流程回答。

`.knowledge/` 保存可重建的正式衍生資料，`.work/` 保存暫存 prompts、封包與日誌。來源變更時，build 的同 hash 跳過機制可減少重算；跨章節整理的依賴更新仍需檢查，不能宣稱已自動完成。

## 投資方法論庫

只選能改變判斷的互補模型，說明適用條件、盲點及其如何檢查同一個問題；重複觀點合併。以下是研究導引，不是作者逐字引述或對當前標的的背書。模型衝突時，回到事實、因果假設、投資期限與限制，不能用名氣仲裁。

### 可更新的判斷：行動而不假裝確定

把每一個投資結論視為**目前最佳、但可被推翻的模型**。目的不是延後判斷，也不是把「保留彈性」當成不承擔責任；而是在有限資訊下形成足以行動的判斷，並預先定義更新規則。

每次涉及投資判斷時：

1. **說明結論與信心程度**：分開「我認為什麼」與「我有多確定」。信心應反映 Evidence 的品質、直接性、獨立性、時效與檢驗強度，不能由敘事流暢度、持有時間或部位大小決定。
2. **分開 Values 與實證判斷**：長期目標、風險承受與不可妥協的原則屬於 Values；營收、毛利、競爭優勢、合理估值與市場預期則可被 Evidence 推翻。前者不因單一數字改變；後者不能被「定力」保護。
3. **建立最強反方**：在採用 Thesis 前，寫出最能解釋同一事實的替代假說，並列出能區分兩者的觀察。反方不是為了平均取悅所有觀點，而是防止只蒐集支持自己的資料。
4. **預先登記更新條件**：每個主要假設至少列出一個支持訊號、一個反證或 Thesis Breaker、檢查時點，以及觸發後要重估的變數。
5. **仍要做選擇**：不確定不等於不行動。比較等待、研究、維持與增減部位的機會成本後，選擇與 Evidence 強度、下檔與可逆性相稱的行動；新 Evidence 出現時更新，而非把修正等同犯錯。
6. **保留可追溯性**：重要 Claim 依 `Claim → Source + Locator → reader-checkable context → Validation` 記錄；清楚標示原始事實、跨來源整理、自己的推理與條件式行動。

對買賣、持有、配置、估值或重大研究結論，至少輸出：結論／行動、信心程度與原因、關鍵 Evidence、最強反方、可推翻條件與下次檢查點，以及 Evidence 改變後須重估的價值、風險或配置。

### Comparative Advantage｜比較利益

**比較利益**回答的不是「誰絕對最強」，而是：在資源有限時，哪個人、公司、活動或產業在**放棄最佳替代用途的成本最低**，因此最值得取得資源配置。它以 Opportunity Cost 為核心，適用於分工、資本配置與研究時間分配。

- **不要混用三件事**：Comparative Advantage（相對機會成本）不同於 Absolute Advantage（絕對產能／效率），也不同於社會比較、排名或地位帶來的「比較優勢」。
- **公司分析**：先拆到產品、客戶、地區或活動層級；問公司在哪個環節能以最低機會成本維持成本、品質、速度、技術、客戶關係或資本回報的相對優勢。全公司「很厲害」不構成證明。
- **產業與國家分析**：比較利益可解釋分工與長期利潤池的方向，但不能直接推出某國或某產業的所有公司都值得投資。
- **投資人自身配置**：把研究時間與資本集中於能力圈內、可驗證且相對機會成本最低的少數機會；這是 Allocation 原則，不是替高集中度背書。
- **投資結論仍需估值**：企業有比較利益，不代表股票有超額報酬。還要檢查該優勢的持久性、現金流歸屬、價格已反映的預期，以及可替代投資的機會成本。

研究時至少回答：比較的單位是什麼、最佳替代用途是什麼、相對機會成本為何較低、優勢如何轉成每股經濟效益、什麼 Evidence 會推翻這個判斷。不可用國籍、產業標籤或單一歷史成功案例代替比較。

此模型可由《投資中最簡單的事》的五力與產業配置討論，以及《窮查理的普通常識》對李嘉圖比較利益與分工整合的討論交叉理解。它們提供思考框架；對特定公司、產業或價格的當前主張仍須使用可追溯的最新 Evidence。

### 徐新方法論

徐新的框架可整理為三層：

1. **Winner Pattern Study**：先研究主題/產業贏家共通模式，建立「什麼樣的公司會贏」的模板。
2. **Consumer Deep Diving**：穿透財報，直接理解需求、用戶行為、消費者為什麼買，以及三到五年後是否還會買。
3. **Full-Theme Scan / Full-Sector Scan / Turn Every Stone**：不要只研究單一公司；在本 repo 的 taxonomy 中，優先把跨公司敘事、供應鏈、canonical cycle 或投資主題稱為 `theme`，把傳統產業邊界稱為 `sector`。實作時先廣泛掃描主要玩家，再依上方「競爭群組分析」分組；不能把整個 theme 的公司都當成互相競爭。「賽道」只作為口語說法，不作為 skill taxonomy 名稱，先建立森林，再判斷哪棵樹真正突出。

輸出時可壓縮為：

```text
Winner Pattern -> Consumer Insight -> Full-Theme Scan -> Best Candidate -> Valuation
```

核心提醒：投資不是只問「這家公司好不好」，而是問「為什麼是它，而不是另外十九家」。

### Edge 檢查

Edge 是相對市場參與者的資訊、分析、行為、期限或結構優勢。配合上方第二層思考，檢查「我的差異判斷依據何在、是否可驗證、價格是否已反映」；不能把看法不同或資料量大直接當成優勢。

- **Information Edge**：是否有下節所述、可重複的 `company → competitor-groups → theme` 資料取得與更新能力，得到更相關、完整、及時且可驗證的證據。
- **Analytical Edge**：是否能用同一份資料建立較好的因果模型、可比分析與替代解釋，找出可驗證的預期差；它是解讀資訊的能力。
- **Behavioral Edge**：是否有紀律，不被恐懼、貪婪、FOMO 或短期波動帶走。
- **Time-horizon Edge**：是否願意承受短期雜訊，研究三到五年以上的結果。
- **Structural Edge**：資金性質、工具、產業背景、研究流程是否形成優勢。

無法證明 edge 時，標示「尚未證明優勢」，而非直接宣稱「與市場共識相同」；仍可提供研究與配置框架，但不能用未驗證的優勢支持高信心集中下注。

### Information Edge：系統化取得與維護資料

先定義公司與決策問題，再沿 `company → competitor-groups → theme` 擴大查證範圍，最後將比較與主題變化帶回公司判斷。相關 theme 可有多個；這是研究路徑，不是把公司視為只屬於一個 theme 的固定樹狀分類。

| 層次 | 蒐集重點與來源入口 | 回答的問題 |
|---|---|---|
| `company` | 官方財報／IR／法說、產品與部門資料；營收、毛利、EPS、FCF、負債與資本配置 | 公司靠什麼賺錢，哪些變數改變？ |
| `competitor-groups` | canonical 分組與關係證據；主要同業的同口徑財務、產品、客戶、價格與估值資料 | 是公司優勢或共同環境？溢價／折價有何理由？ |
| `theme` | 終端需求、供需／產能、技術替代、供應鏈瓶頸與 cycle；區分實際營收曝險和敘事關聯 | 哪些結構或週期變化會改變公司及同業的成長與利潤？ |

使用現有 repository、connector 或已授權資料來源；先查既有可用資料，缺失或過期才按任務補抓。對關鍵資料保留來源位置、觀察／財報期間、取得日期、單位／口徑、實際或預估、品質與缺口；取得日期新不代表內容期間新。

更新頻率依決策用途安排：財報公布、重大公司事件、同業變化或 theme 訊號觸發相關資料與比較重算。列出優先缺口、補查來源與更新觸發條件即可，除非任務要求，不另外建立爬蟲或排程。依「比較估值前：資料是否足夠？」決定何時可收斂；資料蒐集的成功標準是能支撐或推翻判斷，不是下載數量。

### 方法論比較

當使用者問「還有哪些方法論」時，優先用表格比較「人物/框架來源、核心方法論、最關鍵問題」。可使用以下基礎庫：

| 人物/框架來源 | 核心方法論 | 最關鍵問題 |
|---|---|---|
| 徐新 | Winner Pattern + Consumer Deep Dive + 全主題/全賽道掃描 | 誰會成為主題或產業贏家，為什麼？ |
| Warren Buffett | 能力圈 + 護城河 + Owner Earnings + 安全邊際 | 這是不是能長期複利的好生意？ |
| Charlie Munger | 多元思維模型 + 反向思考 + 激勵機制 + 心理誤判 | 我是不是因為錯誤模型而看錯？ |
| Howard Marks | Second-Level Thinking + 週期 + 風險控制 + 逆向 | 市場預期了什麼，我和市場差在哪？ |
| Philip Fisher | Scuttlebutt + 成長品質 + 長期持有 | 客戶、供應商、員工看到的競爭力如何？ |
| Peter Lynch | 生活觀察 + 成長分類 + 合理估值 | 華爾街還沒完全理解的成長在哪？ |
| Terry Smith | Good Companies, Don't Overpay, Do Nothing | 公司能否長期維持高 ROIC？ |
| Mohnish Pabrai | Cloning + Checklist + 不對稱賭注 | 能否抄最好的作業，且下檔有限？ |
| Ray Dalio | All Weather + Risk Parity + Economic Machine | 不同成長/通膨環境下組合能否活下來？ |
| George Soros | Reflexivity | 價格是否反過來改變基本面？ |
| Stanley Druckenmiller | 流動性 + 宏觀趨勢 + 集中下注 | 最強趨勢與資金方向在哪？ |
| Joel Greenblatt | Magic Formula | 哪些公司同時便宜又好？ |
| Seth Klarman | 安全邊際 + 絕對報酬 | 最差情況會永久損失多少？ |
| Michael Mauboussin | Expectations Investing + Base Rates | 股價已經 price-in 什麼？ |
| Ed Thorp | Kelly Criterion | 即使有 edge，該下注多少？ |
| Nassim Taleb | Barbell + Antifragility | 如何避免一次黑天鵝毀滅？ |
| Jim Simons | Statistical Edge + Systematic Investing | 資料中是否有可重複統計優勢？ |
| ARK / Cathie Wood | Wright's Law + Disruptive Innovation | 成本下降是否創造爆發式新市場？ |
| 劉潤 | 底層邏輯 + 數學/商業模型 + 機率統計 + 博弈論 | 這個商業現象背後真正的變數、結構與約束是什麼？ |
| 萬維鋼 | 系統思維 + 決策品質 + 多觀點/多面向模型 | 這個問題是否被放進正確的系統、回饋迴路與觀察面向裡理解？ |
| Yuval Noah Harari | 歷史尺度 + 敘事/制度/科技變遷 | 這個投資敘事背後的人類協作、制度與長期趨勢是否成立？ |
| 吳軍 | 科技史 + 資訊理論 + 工程/產品方法論 | 技術演進、資訊效率與工程約束如何改變產業結構？ |

### 書本框架對方法論庫的補充

`books/` 中的框架不只提供投資人，也提供投資決策需要的底層模型。回答時要區分「投資人/流派」與「可借用的思維模型來源」：

- 《投資最重要的事》對應 **Howard Marks**：second-level thinking、風險控制、週期、逆向與市場預期。
- 《窮查理的普通常識》對應 **Charlie Munger**，並連到 **Warren Buffett**：多元思維模型、逆向思考、能力圈、心理誤判、檢查清單、少數高品質機會。
- 《底層邏輯》與《底層邏輯2》對應 **劉潤**：變數拆解、機率統計、數學期望、大數定律、博弈論、商業系統與相對思維。
- 《佛畏系統》對應 **萬維鋼**：系統思維、回饋迴路、決策品質與多觀點/多面向理解。
- 《人類大歷史》對應 **Yuval Noah Harari**：長期歷史尺度、共同敘事、制度演化、科技改變社會結構。
- 書中提到 **吳軍** 時，可作為科技史、資訊理論、工程/產品方法論與長期技術演進的輔助框架。

這些書本來源可補足 `Master Investor Methodology` 的前置層：先用底層邏輯與系統思維理解世界、主題/產業，再進入公司、預期、估值、下注與持有。

### 左側、右側與長期主義

- **左側投資**：市場尚未確認反轉時，因價格低於內在價值、安全邊際提高而買入。代表框架：Benjamin Graham、Warren Buffett、Seth Klarman、Howard Marks、Mohnish Pabrai。必須確認是 `Price down` 但 `Intrinsic Value roughly unchanged`，否則可能是 value trap。
- **右側投資**：等價格、趨勢、基本面或資金流確認後跟進。代表框架：William O'Neil、Mark Minervini、Stanley Druckenmiller。
- **混合系統**：可用基本面左側找價值，再用價格/趨勢/週期右側確認 thesis 是否開始被市場驗證。
- **長期主義**：不是持有很久，而是選到能被時間放大的東西。可用 `Quality × Durability × Reinvestment × Time` 作概念檢查，不作數值估值公式。最純長期主義可用 Buffett、Munger、Fisher、Terry Smith、Nick Sleep、Li Lu 作為代表；長期複利派可用 Chuck Akre、Tom Gayner、Thomas Russo、Pabrai 作為代表。徐新也可歸入長期主義，但她的特徵是先找到產業 winner，再長期陪伴 winner 成長。

### 人物索引與分層

方法論庫不要只列一張平面表，也不要把人名數量當成品質；回答時可依問題切換分層，選出互補的 mental models 來檢查同一個投資問題：

- **主題/產業/消費者/競爭**：徐新、Philip Fisher、Peter Lynch。
- **長期複利/優質企業**：Buffett、Munger、Terry Smith、Nick Sleep、Li Lu、Chuck Akre、Tom Gayner、Thomas Russo。
- **市場預期/週期/逆向**：Howard Marks、Seth Klarman、George Soros、Michael Mauboussin。
- **宏觀/流動性/資產配置**：Ray Dalio、Stanley Druckenmiller。
- **量化/下注/風險結構**：Joel Greenblatt、Ed Thorp、Jim Simons、Nassim Taleb。
- **技術顛覆/成本曲線**：ARK / Cathie Wood。
- **左側價值**：Benjamin Graham、Buffett、Klarman、Marks、Pabrai。
- **右側趨勢**：William O'Neil、Mark Minervini、Druckenmiller。
- **書本延伸的思維模型/系統框架**：劉潤、萬維鋼、Yuval Noah Harari、吳軍。這些人不一定是投資流派代表，但可補強商業底層邏輯、系統思維、歷史尺度、科技/資訊理論與決策品質。這裡的 `多元思維模型` 不是狹義的「不同學科模型」，而是用不同觀點、不同面向、不同方法去檢查同一個問題。

### Value Creation、Storage、Compounding

使用者問長期主義如何辨識與儲存價值時，用以下框架：

```text
Identify Value -> Understand Value Creation -> Track Value Storage -> Verify Reinvestment -> Let Time Compound
```

辨識價值至少看：

- ROIC 相對 WACC、ROE 相對股權成本；分別檢查槓桿與會計口徑，不把兩者混成同一標準。
- Reinvestment Runway：仍有足夠高報酬再投資空間。
- Moat：品牌、成本、網路效應、轉換成本、規模經濟等優勢是否持久。
- Free Cash Flow：獲利能否轉成現金。
- Pricing Power：成本上升時是否能漲價且不流失客戶。

價值儲存要追問企業賺到的錢流向哪裡：本業再投資、併購、回購、配息、留現金，或被管理層浪費。真正的 compounder 是能把現在盈餘以高增量 ROIC 重新投入，轉化成更高未來盈餘。

建立 `Value Storage Test` 時問六題：

1. 公司是否真的創造經濟價值，ROIC 是否長期高於 WACC？
2. 高回報是否有護城河保護，競爭者為何不能搶走超額報酬？
3. 還能把多少錢重新投入，TAM、市占、新產品、新市場還有多大？
4. 新增資本回報率是多少，不只看歷史 ROIC，也看 incremental ROIC。
5. 管理層是否懂資本配置，再投資、回購、併購、配息哪個最合理？
6. 價值最後落到誰手上，股東、員工、客戶、供應商還是管理層？

### 80/20（82 法則）、複利與長期主義

三者不是競爭概念，而是不同層次：

- **80/20（82）法則**：找少數真正重要的機會與變數。
- **長期主義**：確認它值得被時間放大。
- **複利法則**：讓時間把小優勢變成巨大結果。

輸出可整理為：

```text
80/20 -> Selection -> Long Term -> Compounding -> Durable Compounder
```

提醒使用者不要把它誤解成「重倉後永遠不賣」。複利成立的前提是增量資本報酬、護城河、管理層資本配置與成長 runway 持續存在。

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
- 每個原則都要回答「日常如何使用」，並保留章節來源、成立假設與失效條件；區分作者主張與教練延伸。
- 至少包含：核心命題、主要原則、每日/每週/每月/每季流程、一頁式檢查表、投資行動準則。
- 避免長篇引用原文；以摘要、提煉與應用為主。

## 財務技能命名與分類治理

此節只在命名／分類任務使用。採用本專案慣例 `skill-<domain>-<object>-<action>`，先判斷主要交付物的語意與資料責任，再看資料形狀；輸入一家公司或輸出多家公司都不足以單獨決定 domain。

| Domain | 主要責任 | 區分要點 |
|---|---|---|
| `company` | 公司自身的基本面、財報、法說、營收與部門權重 | 批次執行公司資料處理不會自動變成 stock |
| `theme` | 主題、供應鏈、競爭分組、跨公司關係與 canonical cycle | 含逐股 competitor analysis，因其主要交付物是市場中的競爭關係 |
| `institutional` | 外部研究者的觀點、評等、目標價、預估與 thesis | 區分第三方觀點與公司原始事實 |
| `stock` | 股票／ETF 的價格、技術指標、籌碼及 watchlist／universe 操作 | 以股票宇宙為範圍的事件行事曆亦屬此層 |
| `investment` | 決策、配置、風險、策略與教練框架 | 例如本 skill |
| `book` | 書籍摘要、概念提煉與知識框架 | 以書本知識為交付物 |

`competitor`／`competitor-groups` 是 **object**；`analysis`／`curate` 是 **action**。依本專案慣例，兩者使用 theme domain，不另創 competitor domain，也不因輸出存成公司 CSV 就改名 company。這是技能責任分類，並非「公司研究不能包含競爭分析」。

相關責任邊界：

- `skill-company-revenue-segment-weights` 提供公司 segment/cycle 占比；`skill-theme-cycle-index` 彙總主題指數；`skill-theme-cycle-coverage` 評估主題覆蓋與資料缺口。依主要結論歸類，不依歷史檔名中的 company 字樣。
- 同一 cycle 可跨市場有時間落差；公司也可涉入多個 cycle。權重描述曝險，不證明彼此是競爭者。
- `skill-stock-investorevent-fetch` 的交付物是股票宇宙事件行事曆；公司法說內容消化則屬 company。不要用「跨公司就是 theme／stock」取代責任判斷。
- `skill-institutional-thesis-research` 處理機構敘事型論述；`skill-institutional-tw-report-research` 處理台灣券商報告中的結構化 rating／target price／EPS 等研究數字。觀點、公司事實與市場交易 flow 必須分層，不因同一標的就合併。
- 不用 `tw`、`taiex`、`my-tw` 另創 domain；地域限制放在 object（例如 `tw-report`），repository 位置不當成業務分類。

category 與 domain 是兩個維度，依主要交付物選擇：

| Category | 主要交付物 |
|---|---|
| `financial-data` | 抓取、清理、同步、轉換原始財務資料 |
| `financial-accounting` | 財報、會計數字、歷史紀錄與揭露比對 |
| `financial-forecasting` | 營收、毛利、獲利、景氣或模型預測 |
| `financial-strategy` | 投資判斷、風險、配置與決策框架 |
| `document` | 書籍、PDF、簡報、逐字稿等文件處理 |

## 完成前檢查

- 回答了使用者實際問題，深度與輸出長度相稱；沒有為填滿模板捏造資料。
- 書中原則、目前事實、整理、推論與行動可區分，重要結論有來源或明確假設。
- 競爭分析交代產品市場與納入／排除理由，不把 theme、cycle 或供應鏈關係當成直接競爭。
- 比較估值已標示資料充分性、溢價／折價理由與結論範圍；不以股價或 EPS 大小取代估值，不以缺資料的排名支持確定行動。
- 第二層洞察有因果解釋、替代假說、市場預期依據與推翻條件；沒有把反共識本身當成 edge。
- 行動有條件、風險、機會成本與重新檢查觸發點；不保證報酬，資料不足時保留不確定性。
