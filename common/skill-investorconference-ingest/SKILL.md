---
name: skill-investorconference-ingest
description: 投資人說明會（法說會）智慧影音與簡報下載與管理 Ingest 模組（支援美股與台股）
---

# InvestorConference Ingest 技能說明

本技能提供法說會影音、簡報、第三方逐字稿與 metadata 的材料蒐集與同步。Ingest 的責任是把可用原始材料放進 repo，研究級字幕校正與 GT 生成由 `skill-investorconference-digest` 負責。

## ⚙️ 核心功能
1. **智慧影音下載 (Smart Ingest)**：自動檢測美股/台股市場，解析 webcast 影音網址或透過 YouTube 尋找，並藉由 `yt-dlp` 下載音檔。
2. **材料蒐集與落檔**：保存音檔、IR PDF/Markdown、第三方逐字稿、Yahoo/AlphaSpread/AlphaMemo 等可用來源。若產生機器字幕，僅視為 `*_FIN.srt` 初稿。
3. **美股 earnings-call 材料支援**：對 DELL、QCOM 等英文字母 ticker，優先蒐集 earnings release、prepared remarks、performance review/deck、financial tables、transcript PDF/HTML、Yahoo/AlphaSpread transcript、SEC 10-Q/10-K 連結（若可得）。
4. **簡報 OCR 與文字層提取**：批次處理各公司 PDF 簡報，必要時透過 Mac-mini 高精度 OCR API 補齊圖表數值。
5. **README 與 Manifest 自動同步**：維護 `audio_manifest.json`、`audio_durations.json` 與 README.md 表格。

> [!IMPORTANT]
> Ingest 不負責產生或判定 `*_GT.srt`。GT 是 digest 前的研究資料校正成果，必須由 `skill-investorconference-digest` 使用 FIN、音檔、IR、Q&A、第三方逐字稿與前後期資料交叉生成或修正。


## 🇺🇸 美股材料蒐集規則

當 `stock_id` 為英文字母 ticker（如 `DELL`, `QCOM`）或 metadata 顯示為美股時，Ingest 仍只負責材料蒐集，不負責投資分析或 GT 判定。應盡量落檔或記錄以下來源：

| 材料 | 建議檔名 | 用途 |
| :--- | :--- | :--- |
| Earnings call audio | `{Ticker}_{Year}_q{N}.m4a` | FIN/GT 字幕時間軸來源 |
| FIN subtitle | `{Ticker}_{Year}_q{N}_FIN.srt` | 機器轉錄初稿 |
| Earnings release / report | `{Ticker}_{Year}_q{N}_report_en.pdf/md` | GAAP 財務數字第一來源 |
| Performance review / deck | `{Ticker}_{Year}_q{N}_performance_review.pdf/md` 或 `_ir_en` | 管理層簡報、guidance、segment 資訊 |
| Financial tables | `{Ticker}_{Year}_q{N}_financial_tables.pdf/md` | GAAP/non-GAAP reconciliation、現金流、資產負債表 |
| Third-party transcript | `{Ticker}_{Year}_q{N}_yahoo_transcript.md` / `_alphaspread_transcript.md` | speaker、Q&A、英文術語校正補充 |
| SEC filing link/file | `{Ticker}_{Year}_q{N}_10q.md` 或 metadata link | 10-Q/10-K 交叉驗證（若可得） |

> [!CAUTION]
> 美股第三方 transcript 只能作補充來源。若 Yahoo/AlphaSpread 與公司 IR、earnings release 或 SEC filing 衝突，digest 應以公司文件與可驗證音訊為準。

## 📂 檔案清單
* `scripts/ingest.py`：主 Ingest 邏輯。
* `scripts/audio_utils.py`：本地音檔狀態與 manifest 讀寫。
* `scripts/audio_storage_bridge.py`：GitHub Releases 語音上傳與回退邏輯。
* `scripts/migrate_audio_to_gh_releases.py`：歷史 GDrive 資源移轉至 GitHub。
* `scripts/fetch_yahoo_transcript.py`：透過瀏覽器抓取 Yahoo Finance 逐字稿的獨立工具。

## 🚀 使用方法
```bash
# 下載指定股票特定季度的音檔與可用材料；若有機器字幕，僅作為 FIN 初稿
python skills/skill-investorconference-ingest/scripts/ingest.py <stock_id> <year> <quarter> [--push]

# 更新 README 表格與持續更新
python skills/skill-investorconference-ingest/scripts/ingest.py --update-readme

# 批次轉換簡報 PDF 檔案
python skills/mac-mini-ocr/scripts/convert_ir_pdfs.py
```
