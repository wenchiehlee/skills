# skill-stock-dynamic-valuation-box

台股個股 no-look-ahead 動態 TTM 本益比估值盒（2~5 年時價圖）技能。詳細指令與輸出契約見 [SKILL.md](SKILL.md)。

## 快速開始

```bash
python scripts/render_dynamic_valuation_box.py \
  --symbols 3045 2412 \
  --years 2 \
  --trades-csv data/trades.csv \
  --output-dir output/dynamic_valuation_box
```

## 檔案結構

```
skill-stock-dynamic-valuation-box/
  SKILL.md              # 技能指令與輸出契約（估值盒規則、資料契約）
  metadata.json         # 版本與來源 metadata
  self_update.py         # 通用技能自我更新工具（跟其他skill共用同一份，勿修改）
  scripts/
    render_dynamic_valuation_box.py   # CLI進入點：抓FinMind日線/財報、算動態PE估值盒、疊實際買賣點、輸出PNG+CSV
```

## 版本

- 1.8.0 (2026-09-28)：跟`wenchiehlee-money/My-TW-Coverage`那邊CI獨立做的同一個
  FinMind token修正合併——CI在我推1.7.0之前，自己也發現了同一個402問題並在
  `render_dynamic_valuation_box.py`加了輪替（`57a6e4e2b` "Make company
  valuation chart generation retryable"），同時新增了這次一起收進registry的
  `render_dynamic_valuation_batch.py`（掃`data/enrichment_all/*.json`裡的數字
  代號、跳過已有三個artifact的、失敗名單寫`--failure-log`方便重跑的批次執行
  腳本）。但CI那版檢查的是`FINDMIND_GMAIL_TOKEN1`~`6`——追到`Python-Actions.
  FinMind`那個現行維護中的repo才確認這其實是**舊名字**（`.env.example`跟
  `daily-finmind-status.yml`的GitHub Actions secrets現在都用`FINMIND_TOKEN1`
  ~`6`，`FINDMIND_GMAIL_TOKEN`只剩一個`archived/`底下的舊腳本還在用），所以CI
  那版在唯一有設定實際token的機器上，token池是空的，`itertools.cycle`永遠只轉
  到空字串、每次都退回匿名配額。這版：拿1.7.0的token邏輯（正確的
  `FINMIND_TOKEN1~6`優先順序、402/reach-the-upper-limit時剔除失效token而非
  盲目輪詢、`load_dotenv()`、找不到token時的warning、全部配額用盡時的明確
  `RuntimeError`）取代CI那版的`itertools.cycle`實作；同時保留CI那次一起做的
  YoY除以零防呆（`revenue.replace(0, nan)`再`pct_change`）；`render_dynamic_
  valuation_batch.py`的`--token-env-prefix`預設值同樣從`FINDMIND_GMAIL_TOKEN`
  改成`FINMIND_TOKEN`，range也從`range(1,6)`（少算一組，漏掉TOKEN6）修成
  `range(1,7)`；`indicators.py`的peband vendoring（CI用單一檔案而非完整skill
  vendor的方式解決`skill-stock-ma-rsi-bband-macd-peband`依賴缺失，考量到完整
  vendor會多帶`taishin_sdk`/`yfinance`等不相關依賴，刻意沿用CI這個較輕量的
  做法，不收進這個skill自己的registry管理）維持原狀不動。
- 1.7.0 (2026-09-28)：FinMind token解析補強——實測重繪2357時只設了單一
  `FINMIND_TOKEN`類環境變數，第一筆`TaiwanStockPrice`就打到FinMind「Requests
  reach the upper limit」的402，整個腳本直接掛掉、只留一坨urllib的traceback，
  使用者完全看不出是配額問題還是程式錯誤。這版：(1)補上`load_dotenv()`（optional
  import，沒裝`python-dotenv`就照舊只讀已匯出的環境變數），讓`.env`檔案真的會被
  讀到；(2)token偵測範圍從原本只認`FINMIND_TOKEN`/`FINMIND_API_TOKEN`兩個名字，
  擴大到同時檢查這個codebase裡三種歷史上並存的命名慣例——本skill原本的兩個、
  numbered的`FINMIND_TOKEN1`~`6`、以及`skill-finmind-fetch`那份`token_env.py`用
  的`FINDMIND_GMAIL_TOKEN`/`FINDMIND_GMAIL_TOKEN1`~`6`（注意那邊「FINDMIND」拼法
  跟D/M顛倒，是既有拼字不一致，這裡照抄env變數名稱清單而非改去import那個skill，
  避免多背一個`requests`+`python-dotenv`的重量級fetch模組依賴）；(3)找到的所有
  token全部池化輪替——`_fetch()`遇到402或訊息含「reach the upper limit」/「token
  is illegal」就把當下這個token從池子永久剔除（整個process生命週期內，不會每次
  呼叫重試已知失效的token）、改試下一個，讓單一次執行能撐過個別帳號自己的每日
  配額上限；(4)`main()`一開始如果完全找不到任何token，會印一行warning到stderr
  說明匿名FinMind配額很小可能中途402，但不會直接擋下整個執行（維持向下相容——
  這個skill一直都支援無token模式）；(5)所有token跟匿名管道都失效時，最終的
  `RuntimeError`會明確列出檢查過哪些環境變數名稱，取代原本裸的
  `HTTP Error 402: Payment Required` traceback。用真實2357重繪實測驗證：修正
  後確實能正確偵測到`.env`裡設的6組`FINMIND_TOKEN1`~`6`（原本因為缺
  `load_dotenv()`完全讀不到），但同一時間這6組token加匿名存取全部剛好都已經是
  當下配額用盡狀態（直接對FinMind API逐一測試確認，非本skill臆測）——這是外部
  帳號配額的真實限制，不是這次程式修正要解決的問題。
- 1.6.0 (2026-09-28)：5-panel佈局（price/P/E/EPS/revenue/YoY）的收尾精修，六項來自實際
  輸出圖（2357華碩）目視審查發現的問題：(1) top panel為了容納最遠的forward-EPS目標年
  （如FactSet FY2028E）延伸共用x軸，revenue/YoY兩個panel沒有那麼遠的資料，右側留下一大塊
  無說明的空白——改成用淺灰底色（`axvspan`）標示該區間並加一行「Forward-EPS projection
  window — no revenue data yet」文字，不再讓人誤以為是資料遺失或掉圖。(2) `eps_axis`（現在
  已經不是最底部panel）殘留一行多餘的`set_xlabel("Trading day")`，跟真正最底部`growth_axis`
  的「Month」標籤重複又矛盾，直接移除。(3) YoY成長率panel原本沒有資料不足時的提示，
  跟revenue panel的"data unavailable"文字不對稱——補上對稱的`else`分支。(4) suptitle仍寫死
  「price & dynamic TTM P/E valuation box」，沒反映現在多出的P/E、EPS、revenue、YoY四個
  panel，改成「price, P/E valuation box, EPS & revenue trend」。(5) P/E panel的
  `height_ratios`只有0.8，但圖例塞了4條線（Trailing P/E/P/E mean/Forward P/E/Forward P/E
  mean），字級已經是最小的7pt仍偏擠，調到1.0給多一點高度。(6) revenue/YoY長條寬度原本寫死
  18天，`--years`拉到5年時同樣寬度在更長的x軸上會顯得過寬，改成`18 * 2 / years`隨顯示年數
  反比縮放。用合成假資料直接呼叫`_plot()`在years=2跟5各跑一次驗證六項修改都不報錯、畫面
  正確（未接FinMind，避免測試耗用API token）。
- 1.4.0 (2026-09-20)：forward EPS改成能直接讀Yahoo Finance跟FactSet兩家真實的consensus
  feed原生格式，不用先手動轉成本skill的CSV格式。新增`--yahoo-consensus-csv`（讀
  Yahoo原生的`raw_yahoo_finance_consensus_daily.csv`，欄位stock_code/
  forecast_asof_date/earnings_1y_avg——這欄位本身就是逐日更新的forward EPS時間序
  列，不用另外猜發布日）跟`--factset-report-csv`（讀FactSet原生的
  `raw_factset_detailed_report.csv`，欄位代號/股票代號/MD日期/<年份>EPS平均值——
  FactSet沒有像Yahoo那樣現成的「next FY」欄位，改用每筆報告的MD日期算出
  「年份(MD日期)+1」對應的年度平均值欄位當作forward EPS，跟Yahoo的
  earnings_1y_avg是同一個「下一個完整財年」概念，只是FactSet存成具名年份欄）。
  三種來源（含原本1.3.0的`--forward-eps-csv`手動格式）可以同時給，程式把所有列
  併在一起照as_of_date排序，backward merge自然會選到當下最新已知的那筆估計，不
  管它來自哪個來源。已用真實的`../Yahoo.Finance/data/reports/`資料（2301光寶科）
  驗證兩個轉接器分別跑、合併跑都正確。
- 1.3.0 (2026-09-20)：新增選用的forward EPS疊圖——`--forward-eps-csv`（欄位symbol/
  as_of_date/forward_eps，支援stock_id別名）讓使用者提供每次法人/共識預估EPS更新時
  的「發布日」跟預估值，程式用跟trailing TTM EPS一樣的merge_asof backward手法按
  as_of_date掛到每個交易日，算出forward PE跟同樣的μ±1σ/±2σ滾動估值帶。刻意不做的事：
  這個skill不抓、不算forward EPS本身（FinMind沒有這個dataset），只負責把使用者已經
  拿到手的預估值按「這筆預估在哪一天才算已知」正確接到no-look-ahead框架裡——如果
  誤用預估的「目標財報期別」而非「發布日」去merge，等於讓後續交易日提前看到還沒
  公布的預估值，就違反了整個skill的no-look-ahead前提。圖表上trailing box仍是主要的
  綠/紅區域，forward PE mean跟±1σ用橘色虛線疊在同一張圖，不取代trailing box；下方
  EPS子圖也加一條橘色forward EPS階梯線對照trailing TTM EPS。CSV輸出新增forward_eps/
  forward_pe/forward_pe_mean/forward_pe_std/forward_price_{m2,m1,mean,p1,p2}欄位，
  沒提供`--forward-eps-csv`時全部是NaN、其餘輸出跟舊版完全相同（向下相容）。
- 1.2.0 (2026-09-20)：新增股票股利（無償配股/除權）調整——6669在2026-09-02配發
  約2.98倍股票股利，TaiwanStockPrice的close沒做除權處理，原始序列出現假的單日
  跌66%斷崖，橫跨那個ex-date的滾動PE窗口整個算壞（外層上緣曾經算出7614卻對著
  2140收盤價）。改成用FinMind TaiwanStockDividend抓每次配股的ex-date跟稀釋倍數，
  股價依「交易日」、EPS依「財報所屬期別的available_date」分別調整到同一股本基礎
  再合併算PE（一開始寫錯用同一個「交易日」基準調整兩邊，分子分母同除掉一樣的
  倍數PE比值根本沒變，等於白改，這版才是真的修正）。這是股本結構事件、不是
  SKILL.md規則1避免使用的股利再投資調整，屬於不同性質的修正。
- 1.1.2 (2026-09-20)：修正長期持股（買賣紀錄可回溯到2015~2020年，例如2324/2356/
  3231）畫圖時x軸整個被拉爆的bug——買賣點原本只用代號篩選、沒有跟著`--years`
  顯示窗口過濾日期，只要有一筆很舊的交易，matplotlib共用x軸就會被迫容納它，把該
  顯示的近期價格線擠壓成右側一小條。現在買賣點跟價格線一樣用`display_start`過濾。
- 1.1.1 (2026-09-20)：拿掉標題下面那行「TTM EPS is available...」副標——跟上面的
  主標題（含中文股名後變兩行）貼太近，視覺上幾乎黏在一起；順手把`_plot()`用不到的
  `window`參數也拿掉（原本只有這行副標在用），並把圖表頂部留白從0.90調回0.93。
- 1.1.0 (2026-09-20)：圖表標題改成「代號 中文名稱」（例如「2412 中華電」），透過
  FinMind `TaiwanStockInfo` 查名稱，查不到（下市/剛上市）就退回只顯示代號；同時把
  matplotlib 字型改成優先用系統裝的中文字型（Microsoft JhengHei/YaHei等），原本
  寫死DejaVu Sans沒有CJK字形，中文名稱會直接印成缺字方框。
- 1.0.2 (2026-09-20)：`--window` 預設值從500改成120（最小值），讓估值帶預設就反映
  近期（約半年）的PE狀態、對當前股價位置更敏感，不用每次手動加`--window 120`；
  仍可視需要調大取更長、更穩定但反應較慢的基準。
- 1.0.1 (2026-09-20)：SKILL.md 的 Output 段落補上滾動PE窗口期間的說明——這個期間
  就是 `--window`（預設500個交易日觀察值，最小120），原本只在後面Run段落的參數列表
  提過，Output段落沒講清楚導致誤以為期間是寫死的。純文件澄清，程式邏輯沒改。
- 1.0.0 (2026-09-20)：初版。用未還原收盤價 + 保守申報截止日才可用的名目TTM EPS算滾動PE分佈，
  μ±1σ/±2σ畫成估值盒；`--trades-csv`可疊實際買賣點（symbol/date/side/price/lots，支援
  stock_id/qty別名與買進/賣出中文）。刻意跟MA/RSI等技術指標分層——本技能只管估值layer，
  不算還原價技術指標，也不下買賣建議。
