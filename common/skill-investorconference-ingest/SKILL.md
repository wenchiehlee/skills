---
name: skill-investorconference-ingest
description: 投資人說明會（法說會）智慧影音與簡報下載與管理 Ingest 模組（支援美股與台股）
---

# InvestorConference Ingest 技能說明

本技能提供法說會影音、簡報、逐字稿與資訊整合的 Ingest 套件。

## ⚙️ 核心功能
1. **智慧影音下載 (Smart Ingest)**：自動檢測美股/台股市場，解析 webcast 影音網址或透過 YouTube 尋找，並藉由 `yt-dlp` 下載音檔。
2. **自動逐字稿生成**：呼叫 Gemini 語音辨識 API 自動將音檔轉為帶有時間戳記之 `.srt` 中英文逐字稿，並清理語音幻覺。
3. **簡報 OCR 與文字層提取**：批次處理各公司 PDF 簡報，必要時透過 Mac-mini 高精度 OCR API 補齊圖表數值。
4. **README 與 Manifest 自動同步**：維護 `audio_manifest.json` 與 `audio_durations.json` 並自動渲染 README.md 表格。

## 📂 檔案清單
* `scripts/ingest.py`：主 Ingest 邏輯。
* `scripts/audio_utils.py`：本地音檔狀態與 manifest 讀寫。
* `scripts/audio_storage_bridge.py`：GitHub Releases 語音上傳與回退邏輯。
* `scripts/migrate_audio_to_gh_releases.py`：歷史 GDrive 資源移轉至 GitHub。
* `scripts/fetch_yahoo_transcript.py`：透過瀏覽器抓取 Yahoo Finance 逐字稿的獨立工具。

## 🚀 使用方法
```bash
# 下載指定股票特定季度的音檔並產生逐字稿
python skills/InvestorConference-ingest/scripts/ingest.py <stock_id> <year> <quarter> [--push]

# 更新 README 表格與持續更新
python skills/InvestorConference-ingest/scripts/ingest.py --update-readme

# 批次轉換簡報 PDF 檔案
python skills/InvestorConference-ingest/scripts/convert_ir_pdfs.py
```
