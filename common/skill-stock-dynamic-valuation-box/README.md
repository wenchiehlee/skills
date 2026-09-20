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
