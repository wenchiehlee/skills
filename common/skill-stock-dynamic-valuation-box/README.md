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

- 1.0.0 (2026-09-20)：初版。用未還原收盤價 + 保守申報截止日才可用的名目TTM EPS算滾動PE分佈，
  μ±1σ/±2σ畫成估值盒；`--trades-csv`可疊實際買賣點（symbol/date/side/price/lots，支援
  stock_id/qty別名與買進/賣出中文）。刻意跟MA/RSI等技術指標分層——本技能只管估值layer，
  不算還原價技術指標，也不下買賣建議。
