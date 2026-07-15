---
name: skill-market-cost-distribution
description: 台股市場籌碼持股成本分佈模擬 — 台新 Nova API 小時 K 搭配 Yahoo 日 K 暖機的雙池衰減模型，輸出一致格式的 PNG 圖與 CSV 分佈檔，附統一的模型可信度與資料新鮮度標籤。
---

# Market Cost Distribution Skill

以「雙池衰減模型（Double-Pool Dynamic）」模擬台股個股的市場持股成本分佈：
核心池（大戶，低換手衰減）與活躍池（散戶，高換手衰減）依週別股權分散度動態校準，
成交量以自由流通股本換算換手率，除權息事件動態調整成本價位。

資料解析度採混和策略：

1. **暖機段**：Yahoo 日 K（還原權值，最長回溯 10 年）建立長期籌碼底部。
2. **高解析段**：台新 Nova API 小時 K（2023-05-23 起）無路徑歧義地更新分佈。
3. 兩段銜接時以 `小時K起始價 / 日K結束價` 縮放，消除還原權值與市價的尺度差。

## 命令說明

| 命令格式 | 功能說明 |
|---------|--------|
| `python <SKILL_DIR>/scripts/run_market_cost.py --list <名單.csv> --data-dir <資料根目錄> --output-dir <輸出目錄>` | 批量處理名單內全部股票 |
| `python <SKILL_DIR>/scripts/run_market_cost.py --symbol 2330 2317 --data-dir ... --output-dir ...` | 處理指定股票 |
| 加上 `--offline` | 強制離線：只用小時 K 快取，不登入台新 API |

- 名單 CSV 需含 `代號,名稱` 兩欄（如 `StockID_TWSE_TPEX.csv`）。
- `0000`（台灣加權指數）自動改用 `IX0001` 下載，換手率以「成交金額 ÷ 總市值(75 兆)」代理。
- 小時 K 會快取於 `<data-dir>/Taishin.Intraday/<代號>_intraday_60m.csv`（可用 `--intraday-dir` 覆寫）；
  全部命中快取時**完全離線**執行，不需要憑證。

## 使用範例

```bash
python skills/common/skill-market-cost-distribution/scripts/run_market_cost.py \
  --list  C:/Users/WJLEE/SynologyDrive/NAS/github.com/MarketCostDistribution/StockID_TWSE_TPEX.csv \
  --data-dir  C:/Users/WJLEE/SynologyDrive/NAS/github.com/MarketCostDistribution/data \
  --output-dir C:/Users/WJLEE/SynologyDrive/NAS/github.com/MarketCostDistribution/output \
  --offline
```

## 輸入資料依賴

| 資料 | 路徑（相對 `--data-dir`） | 用途 |
|------|------|------|
| Yahoo 日 K | `Yahoo.Finance/raw_yahoo_finance_daily_price.csv` | 暖機段價格與成交量（股） |
| 股本 | `Python-Actions.GoodInfo.Analyzer/cleaned_performance.csv` | 換手率分母 |
| 除權息 | `Python-Actions.GoodInfo.Analyzer/cleaned_dividend_schedule.csv` | 小時 K 段成本價位調整 |
| 股權分散 | `Python-Actions.GoodInfo.Analyzer/raw_equity_class_his.csv` | 雙池比例週別校準 |
| 台新憑證 | `--env-file` 指定之 `.env`（FUGLE_USER1_*） | 僅在快取缺漏時下載小時 K |

## 輸出契約（保證一致）

**PNG** `<output>/<代號>_cost_distribution_taishin.png`：左欄歷史收盤價 + 平均成本/POC 參考線與摘要框（含模型可信度、資料截至日）；右欄成本分佈橫向直方圖（綠=獲利、紅=套牢）。

**CSV** `<output>/csv/<代號>_cost_distribution_taishin.csv`：

| 欄位 | 說明 |
|------|------|
| `price` | 成本價位 bin 中心 |
| `weight` | 該價位籌碼佔比（總和為 1） |
| `trust_level` | 模型可信度標籤（見下） |
| `data_as_of` | 最後一根小時 K 日期（YYYY-MM-DD） |
| `staleness_days` | 執行當下距 `data_as_of` 的天數 |

**報告** `<output>/taishin_observation_validation_report.md`：總覽表 + 全部圖 + 失敗清單。

## 模型可信度公式（單一來源：`scripts/metrics.py` 之 `CostMetrics.evaluate_trust`）

判定優先序（PNG、CSV、報告三處保證一致）：

1. **指數** → `參考 (指數)`：換手率為成交值/總市值代理，僅供參考。
2. **上市歷史 < 1000 個交易日**（約 4 年）→ `極低 - 新上市歷史過短`：暖機不足，長期籌碼底部無法定錨。
3. **重股權鎖定**（2412 中華電、3045 台灣大）→ `中低 - 股權鎖定重`。
4. **日均自由流通換手率**：≥0.40% `極高`、≥0.25% `高`、≥0.12% `中`、其餘 `低`。
5. **資料新鮮度**：距最後一根 K 線 >5 天（含假日緩衝）降一級並標註；>30 天直接標 `過期 (Stale)`。

## 已知限制

- 台新小時 K 最早僅到 2023-05-23；未涵蓋盤後定價與零股（約佔日量 0.1~0.4%）。
- 指數（0000）無日 K 暖機、無真實持有人結構，分佈僅為 VWAP 沉澱參考。
- 需要 `taishin_sdk` 套件與有效憑證才能下載新資料；離線模式僅限快取命中。
- 中文圖表字型使用 `Microsoft JhengHei`，非 Windows 環境需另行設定。
