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
    run_indicators.py    # CLI進入點：批次算指標、寫CSV、選配--verify交叉比對
    price_loader.py       # Fugle還原股價（除息+分割回溯調整）+ yfinance交叉來源
    indicators.py          # 純數學：MA/STD/BBand/z-score/RSI(14)/MACD(12,26,9)
```

## 版本

- 1.0.0 (2026-08-10)：自 GoogleSheet.Banks 的 `update_zscore_stats.py` 收錄並泛化——
  拿掉對特定Google Sheet的依賴，改成通用CLI（`--symbols`/`--list` + CSV輸出），
  新增MACD(12,26,9)與明確的布林通道(BBand)輸出，`--verify`交叉比對機制沿用原本已驗證過
  能抓出yfinance還原缺陷（0052分割事件）的方法論。
