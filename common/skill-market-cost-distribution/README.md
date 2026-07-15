# skill-market-cost-distribution

台股市場籌碼持股成本分佈模擬技能。詳細指令與輸出契約見 [SKILL.md](SKILL.md)。

## 快速開始

```bash
# 離線重畫觀察名單（小時 K 已有快取時）
python scripts/run_market_cost.py --list StockID_TWSE_TPEX.csv \
  --data-dir <MarketCostDistribution>/data --output-dir <MarketCostDistribution>/output --offline

# 單檔（缺快取時會自動登入台新 API 下載）
python scripts/run_market_cost.py --symbol 2330 --data-dir ... --output-dir ...
```

## 檔案結構

```
skill-market-cost-distribution/
  SKILL.md            # 技能指令與輸出契約
  metadata.json       # 版本與來源 metadata
  scripts/
    run_market_cost.py  # CLI 進入點（批量/單檔/離線）
    data_loader.py      # Yahoo/GoodInfo CSV 載入與對齊
    simulator.py        # 雙池衰減成本模擬器
    metrics.py          # 分佈統計 + 統一可信度公式 evaluate_trust
    visualizer.py       # 雙欄 PNG 繪製
```

## 版本

- 1.0.1 (2026-07-15)：加入 self_update.py（下游部署副本可與登錄庫同步）。
- 1.0.0 (2026-07-15)：自 MarketCostDistribution 收錄。統一可信度公式（上市年資/股權鎖定/換手率/資料新鮮度），支援 0000 加權指數（IX0001）、離線快取模式。
