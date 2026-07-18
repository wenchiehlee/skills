---
name: skill-google-analytics-monitor
description: 使用 google-analytics-cli 產生 GA4 網站監控 Markdown/README 報告；當使用者要求監控網站流量、即時活躍人數、近 7/28 天與近 3 個月趨勢、來源/媒介、熱門 URL 與熱門頁面、事件、異常觀察，或要求從 .env 設定產生 Google Analytics 報告時使用。
---

# Google Analytics Monitor Skill

此技能使用 `google-analytics-cli` 的 `ga` 指令產生 GA4 網站監控 Markdown/README 報告。主要視窗為近 3 個月，並保留近 7 天與近 28 天短期快照，讓報告同時適合日常監控與月度趨勢檢查。

## 必要設定

在執行目錄建立 `.env`，至少包含：

```bash
GOOGLE_ANALYTICS_KEY=123456789
GA_SITE_NAME=example.com
```

建議設定：

```bash
GA_REPORT_MONTHS=3
GA_INCLUDE_SHORT_WINDOWS=7,28
GA_REPORT_OUTPUT=README.md
GA_JSON_DIR=reports/ga-monitor-json
GA_CLI_BIN=ga
GA_REPORT_SHOW_PROPERTY_ID=false
```

若使用 service account，先由使用端環境設定憑證路徑，再執行 `ga auth login --service-account <key.json>`；不要把 JSON key 內容寫入 skill 或報告。

## 標準流程

1. 確認 `ga` 可用：`ga --help`。
2. 確認 `.env` 存在且包含 `GOOGLE_ANALYTICS_KEY`。
3. 若尚未登入，使用 `ga auth login` 或 `ga auth login --service-account <key.json>`。
4. 執行輔助腳本產生 Markdown：

```bash
python ../skills/common/skill-google-analytics-monitor/scripts/generate_ga_monitor_report.py
```

可用參數覆寫 `.env`：

```bash
python ../skills/common/skill-google-analytics-monitor/scripts/generate_ga_monitor_report.py \
  --property-id 123456789 \
  --site-name example.com \
  --months 3 \
  --include-short-windows 7,28 \
  --output reports/ga-monitor-example.md \
  --json-dir reports/ga-monitor-json
```

## 報告內容

Markdown/README 報告必須包含：

| 區塊 | 內容 |
| --- | --- |
| Executive Summary | 即時活躍、3 個月總覽、短期變化與主要異常 |
| Realtime | 目前 active users |
| Short-Term Trend | 近 7 天與近 28 天 sessions/users/views/events |
| 3-Month Trend | 每日流量趨勢與月度彙總 |
| Traffic Sources | 近 3 個月來源/媒介排行 |
| Top Pages | 近 3 個月熱門 URL 與熱門頁面 |
| Events | 近 3 個月事件排行 |
| Anomaly Observations | 最新 7 天 vs 前 7 天、最新 28 天 vs 前 28 天、月對月變化 |
| Raw Command Audit | 執行過的 `ga` 指令與失敗警示 |

## 品質規則

- 使用明確日期區間，不只寫「3 months」。
- 報告開頭必須包含 YAML frontmatter，含 `update_frequency: daily` 與 `產生時間: YYYY-MM-DD HH:MM:SS CST`。
- 區分 realtime 與 historical reports。
- API 或 CLI 失敗時，在報告中列出警示，不可靜默省略。
- 缺資料不可自動視為 0；必須標示 no data 或 command failed。
- 報告預設輸出 Markdown；除非使用者要求，不產生 HTML/PDF。
- 若保存原始 JSON，將路徑寫入報告，方便稽核。
- 預設不得在公開 README 顯示完整 property ID；除非使用者明確設定 `GA_REPORT_SHOW_PROPERTY_ID=true`。

## 常用命令

```bash
ga reports realtime --property-id "$GOOGLE_ANALYTICS_KEY" \
  --metrics activeUsers \
  --output json

ga reports run --property-id "$GOOGLE_ANALYTICS_KEY" \
  --metrics sessions,totalUsers,screenPageViews,eventCount \
  --dimensions date \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --output json

ga reports run --property-id "$GOOGLE_ANALYTICS_KEY" \
  --metrics sessions,totalUsers,screenPageViews,eventCount \
  --dimensions sessionSourceMedium \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --output json
```
