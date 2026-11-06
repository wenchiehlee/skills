---
name: skill-amplitude-monitor
description: 使用 Amplitude 官方 REST API 產生產品行為分析與監控 Markdown/README 報告，涵蓋活躍用戶趨勢 (DAU/WAU/MAU)、事件分佈 (Top Events)、留存率 (Retention) 與漏斗流失 (Funnels)，支援 100% 獨立本機執行（透過 API/Secret Key Basic Auth，不依賴 OAuth 或 Claude）。
---

# Amplitude Monitor Skill (產品行為分析與數據監控技能)

此技能專門用來監控與分析 Amplitude 組織內的產品行為數據。透過 Amplitude 官方 REST API（採用 `AMPLITUDE_API_KEY` 與 `AMPLITUDE_SECRET_KEY` 的 HTTP Basic 認證），能 **100% 獨立於本機執行**，完全不需依賴 Claude、Cursor 或 OAuth 2.0 瀏覽器跳轉。

---

## 適用場景

- 需要定期追蹤產品或專案的活躍用戶趨勢（DAU / WAU / MAU、Stickiness 比率）。
- 需要比對日對日 (DoD) 與週對週 (WoW) 的用戶成長與流失情況。
- 需要審查目前專案已定義的自訂事件清單 (Taxonomy Events) 與屬性規劃。
- 需要在 Analytics-Deck 或專案儀表板中產生自動化 Markdown 監控報表。
- 整合於 Antigravity (AGY) 或 `mcp-cli` 自動化工作流程中。

---

## 依賴需求

- Python 3.9+（使用內建標準函式庫 `urllib`，免額外安裝 pip 套件）。
- 工作區環境變數（可存放在 `.env`）：
  - `AMPLITUDE_API_KEY`：專案 API Key（例如 `312ce3f59ae...`）。
  - `AMPLITUDE_SECRET_KEY`：專案 Secret Key（在 Amplitude 網頁端 Settings > Projects > 點選專案取得）。
  - `AMPLITUDE_PROJECT_NAME`：（可選）專案名稱，預設為 `wenchiehlee`。

---

## 核心腳本與指令

技能核心腳本位於：`scripts/generate_amplitude_monitor_report.py`。

### 1. 產生標準 Markdown 監控報表
```bash
python scripts/generate_amplitude_monitor_report.py --days 28 --output reports/amplitude_monitor.md
```

### 2. 產出結構化 JSON 資料（適合下游管道介接）
```bash
python scripts/generate_amplitude_monitor_report.py --days 14 --json
```

### 3. 指定專案名稱與自訂 .env 檔案
```bash
python scripts/generate_amplitude_monitor_report.py --project-name "Amplitude" --env-file ".env"
```

---

## 參數說明

| 參數 | 型態 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `--days` | 整數 | `28` | 觀測的時間窗口天數（例如 7、14、28、90 天）。 |
| `--project-name` | 字串 | 從環境變數讀取 | 指定要產生報表的專案名稱。 |
| `--output`, `-o` | 路徑 | `None` (stdout) | 指定產出的報告檔案路徑（如 `reports/amplitude.md`）。 |
| `--json` | 布林開關 | `False` | 輸出純 JSON 格式而非 Markdown。 |
| `--env-file` | 路徑 | 自動搜尋 | 手動指定含有 API Key 與 Secret Key 的 `.env` 路徑。 |

---

## 報告內容規範

產出的 Markdown 報告具備以下規格：
1. **YAML Frontmatter**：包含 `title`、`project`、`generated_at`、`latest_dau`、`dod_growth`、`wow_growth`、`status` 等結構化元數據。
2. **Key Metrics 摘要卡**：標註最新活躍人數與短期/中期變動百分比。
3. **歷史走勢圖表**：使用文字直條圖（Text Bar）視覺化每日趨勢。
4. **Taxonomy 事件清單**：列出目前專案的關鍵追蹤事件。
5. **行動建議與異常告警**：針對週下滑或未分類事件提供自動化建議。

---

## 與 MCP-CLI 的搭配運作

此技能與 [mcp-cli](file:///C:/Users/WJLEE/SynologyDrive/NAS/github.com/mcp-cli/README.md) 相輔相成：
- `mcp-cli` 掛載 `amplitude-docs` 負責即時檢索官方文檔與 API 規範。
- `skill-amplitude-monitor` 負責拉取與彙整實際產品指標，形成完整的監控閉環。
