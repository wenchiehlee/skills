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
