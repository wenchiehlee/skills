# skill-stock-MA-RSI-BBand-MACD

台股個股/ETF技術指標快照技能（MA/STD/布林通道、RSI(14)、MACD），Fugle API還原股價
為權威來源，yfinance 版本保留供 `--verify` 交叉比對。詳細指令與輸出契約見 [SKILL.md](SKILL.md)。

## 快速開始

```bash
# 直接指定代號
python scripts/run_indicators.py --symbols 0050 0052 2330 --fugle-env-prefix USER1_ --output out.csv

# 從清單CSV讀取，並跟yfinance交叉比對
python scripts/run_indicators.py --list StockID.csv --fugle-env-prefix USER1_ --output out.csv --verify
```

## 檔案結構

```
skill-stock-MA-RSI-BBand-MACD/
  SKILL.md              # 技能指令與輸出契約
  metadata.json         # 版本與來源 metadata
  self_update.py         # 通用技能自我更新工具（跟其他skill共用同一份，勿修改）
  scripts/
    run_indicators.py    # CLI進入點：批次算指標快照、寫CSV、選配--verify交叉比對
    run_backtest.py       # CLI進入點：(0)~(13b)條件分類法歷史回測，多horizon
    backtest.py            # 純邏輯：回測條件偵測+forward報酬/勝率統計
    price_loader.py         # Fugle還原股價（除息+分割回溯調整）+ yfinance交叉來源
    indicators.py            # 純數學：MA/STD/BBand/z-score/RSI/MACD(12,26,9)
```

## 版本

- 1.3.0 (2026-08-10)：新增歷史回測模組 `backtest.py`/`run_backtest.py`——(0)~(13b)條件
  分類法（單日急跌/跌破均線/RSI超賣/z-score偏離/創新高新低），支援多horizon（例如
  60/180/360日）forward報酬/勝率統計。`price_loader.fetch_fugle_adjusted()` 新增明確
  `start_date`/`end_date` 參數（原本只能「回溯N年到今天」，長期回測要能指定任意歷史區間），
  `fetch_fugle_market_adjustment_events()` 自動分段處理Fugle除息/分割端點的3年查詢上限。
  這次把GoogleSheet.Banks `投資決策分層.md` 的回測邏輯收進來時，發現該文件先前的資料完全
  沒做除息回溯還原，藉這次機會一併修正，詳見SKILL.md。
- 1.2.0 (2026-08-10)：`indicators.py` 新增 `calc_rsi_state(close, period)`，回傳
  Wilder RSI遞迴平滑在最後一筆收盤價當下的內部狀態（last_close/avg_gain/avg_loss），
  讓消費端能把RSI做成即時公式（引用「現價+這三個輔助值」），不必每天/每次報價變動都
  重新登入API重算整條序列。GoogleSheet.Banks的`update_zscore_stats.py`已改用這個模式。
- 1.1.0 (2026-08-10)：新增 `--source {fugle,yahoo}` 選擇主要資料來源——沒有Fugle/
  TaishinSDK憑證的consumer repo可以改用 `--source yahoo`（純yfinance，不需要任何憑證），
  代號直接傳yfinance ticker格式；有Fugle憑證的repo維持預設的 `--source fugle` + 選配
  `--verify` 雙來源交叉比對。兩種來源輸出的CSV欄位格式完全一致。
- 1.0.0 (2026-08-10)：自 GoogleSheet.Banks 的 `update_zscore_stats.py` 收錄並泛化——
  拿掉對特定Google Sheet的依賴，改成通用CLI（`--symbols`/`--list` + CSV輸出），
  新增MACD(12,26,9)與明確的布林通道(BBand)輸出，`--verify`交叉比對機制沿用原本已驗證過
  能抓出yfinance還原缺陷（0052分割事件）的方法論。
