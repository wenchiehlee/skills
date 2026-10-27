---
name: skill-google-analytics-monitor
description: 使用 Google Analytics Data API (原生 REST 或 google-analytics-cli) 產生 GA4 網站監控 Markdown/README 報告，支援全站與特定路徑 (Path Filter) 觀測；當使用者要求監控網站流量、即時活躍人數、近 7/28 天與近 3 個月趨勢、來源/媒介、熱門 URL 與熱門頁面、事件、異常觀察，或要求從 .env / Service Account 產生 Google Analytics 報告時使用。
---

# Google Analytics Monitor Skill

此技能使用 **Google Analytics Data API (原生 REST Engine 或 `google-analytics-cli`)** 產生 GA4 網站監控 Markdown/README 報告。支援全站全景或特定端點路徑（Path Filter，如 `/mkdocs-life/`、`/mkdocs-investment/`）過濾。主要分析視窗為近 3 個月，並保留近 7 天與近 28 天短期快照，讓報告同時適合日常監控與月度趨勢檢查。

## 必要設定

在執行目錄建立 `.env`，至少包含：

```bash
GOOGLE_ANALYTICS_KEY=463673189
GA_SITE_NAME=Analytics-Deck
GA4_SERVICE_ACCOUNT_KEY=service_account_ga4.json
```

可選路徑過濾設定（針對多端點共用 GA4 資源）：

```bash
GA_FILTER_PATH=/mkdocs-life/
```

建議選用設定：

```bash
GA_REPORT_MONTHS=3
GA_INCLUDE_SHORT_WINDOWS=7,28
GA_REPORT_OUTPUT=README.md
GA_JSON_DIR=reports/ga-monitor-json
GA_REPORT_SHOW_PROPERTY_ID=false
```

## 標準流程

1. 確認環境變數或 `.env` 包含 `GOOGLE_ANALYTICS_KEY` 與 Service Account 金鑰（`GA4_SERVICE_ACCOUNT_KEY` 或 `GA_SERVICE_ACCOUNT_JSON`）。
2. 執行產生腳本：

```bash
python skills/common/skill-google-analytics-monitor/scripts/generate_ga_monitor_report.py
```

或指定參數執行：

```bash
python skills/common/skill-google-analytics-monitor/scripts/generate_ga_monitor_report.py \
  --property-id 463673189 \
  --site-name "mkdocs-life" \
  --filter-path "/mkdocs-life/" \
  --months 3 \
  --include-short-windows 7,28 \
  --output reports/ga-monitor-mkdocs-life.md \
  --json-dir reports/ga-monitor-json
```

## 雙引擎執行機制 (Dual Execution Engine)

- **優先引擎 (Native REST Engine)**：只要偵測到 `GA4_SERVICE_ACCOUNT_KEY`、`GA_SERVICE_ACCOUNT_JSON` 或目錄下存在金鑰檔案，自動透過 Google Analytics Data API v1beta 執行原生 HTTPS 查詢，**零外部 CLI 依賴、即時獲取即時人數與全歷史報表**。
- **相容引擎 (Legacy CLI Engine)**：若未提供 Service Account，自動退回使用 `google-analytics-cli` 的 `ga` 指令。

## 報告內容

Markdown/README 報告包含：

| 區塊 | 內容 |
| --- | --- |
| Executive Summary | 即時活躍人數、3 個月總覽、短期變化與主要異常 |
| Realtime | 目前 active users (即時在線讀者) |
| Short-Term Trend | 近 7 天與近 28 天 sessions/users/views/events |
| 3-Month Trend | 每日流量趨勢與月度彙總 |
| Traffic Sources | 近 3 個月來源/媒介排行 |
| Top Pages | 近 3 個月熱門 URL 與熱門頁面 |
| Events | 近 3 個月事件排行 |
| Anomaly Observations | 最新 7 天 vs 前 7 天、最新 28 天 vs 前 28 天、月對月變化 (30%+ 警示) |
| Raw Command Audit | 執行過的 API / CLI 呼叫與失敗警示 |
