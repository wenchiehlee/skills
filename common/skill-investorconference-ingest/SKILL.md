---
name: skill-investorconference-ingest
version: 1.2.1
description: 投資人說明會（法說會）智慧影音與簡報下載與管理 Ingest 模組（支援美股與台股）
---

# InvestorConference Ingest 技能說明

本技能提供法說會影音、簡報、第三方逐字稿與 metadata 的材料蒐集與同步。Ingest 的責任是把可用原始材料放進 repo，研究級字幕校正與 GT 生成由 `skill-investorconference-digest` 負責。

## ⚙️ 核心功能
1. **智慧影音下載 (Smart Ingest)**：自動檢測美股/台股市場，解析 webcast 影音網址或透過 YouTube 尋找，並藉由 `yt-dlp` 下載音檔。
2. **材料蒐集與落檔**：保存音檔、IR PDF/Markdown、第三方逐字稿、Yahoo/AlphaSpread/AlphaMemo 等可用來源。若產生機器字幕，僅視為 `*_FIN.srt` 初稿。
3. **美股 earnings-call 材料支援**：對 DELL、QCOM 等英文字母 ticker，優先蒐集 earnings release、prepared remarks、performance review/deck、financial tables、transcript PDF/HTML、Yahoo/AlphaSpread transcript、SEC 10-Q/10-K 連結（若可得）。
4. **簡報 OCR 與文字層提取**：批次處理各公司 PDF 簡報，必要時透過 Mac-mini 高精度 OCR API 補齊圖表數值。
5. **README、Manifest 與音檔 metadata 自動同步**：維護 `audio_manifest.json`、`audio_durations.json`、`audio_metadata.json` 與 README.md 表格。

> [!IMPORTANT]
> Ingest 不負責產生或判定 `*_GT.srt`。GT 是 digest 前的研究資料校正成果，必須由 `skill-investorconference-digest` 使用 FIN、音檔、IR、Q&A、第三方逐字稿與前後期資料交叉生成或修正。

## 🎧 音檔 checksum / metadata 防呆規則

Ingest 必須把「音檔身份」與「音檔長度」分開管理：

| 檔案 | 角色 | 規則 |
| :--- | :--- | :--- |
| `audio_manifest.json` | stem -> release URL | SRT player 與 README 的音檔來源 |
| `audio_durations.json` | file path -> integer seconds | 只供 README/SRT player 顯示長度；不得用來判定音檔是否相同 |
| `audio_metadata.json` | stem -> checksum/size/duration/status | 音檔身份與 duplicate 判定的可稽核來源 |

每次新增或更新音檔時必須執行以下 gate：

1. 先對下載完成的本地音檔計算 `sha256`、`size_bytes` 與 ffprobe `duration_sec`。
2. 將 `sha256` 與 `audio_metadata.json`、本地音檔及 GitHub release asset digest（若 API 提供）比對。
3. 若 checksum 已存在於不同 stem，必須拒絕登錄或上傳，避免把舊季度音檔掛到新季度。
4. 若 release 中已存在疑似重複音檔，執行 audit 工具重建 metadata，並將錯誤季度標為 `status: duplicate`、`duplicate_of: <canonical_stem>`。
5. `audio_durations.json` 只能視為顯示用快取；即使 duration 不同，也不能覆蓋 checksum 結論。若 checksum 相同但 duration cache 不同，應以重新 ffprobe 的結果更新 duration。

建議稽核指令：

```bash
# 只稽核指定 stem，避免一次下載全部 release 音檔
python skills/skill-investorconference-ingest/scripts/audit_audio_metadata.py \
  --stems 2454_2025_q4 2454_2026_q1 \
  --cache-dir /tmp \
  --update-durations

# CI 或批次檢查可加 fail-on-duplicate
python skills/skill-investorconference-ingest/scripts/audit_audio_metadata.py --fail-on-duplicate
```

> [!CAUTION]
> 若 `audio_metadata.json` 顯示某 stem 為 `duplicate`，該季度的 FIN.srt 很可能也來自錯誤音檔。Ingest 不應關閉資料品質問題；digest skill 必須在 GT/digest 前把音訊錯配列為 Blocker/Major，直到正確音檔或足夠文字來源可支持保守 GT candidate。

### 錯誤/重複音檔的 re-ingest 前置清理

若發現某季度 release audio 與另一季度 checksum 相同，或 FIN 開頭明確屬於其他季度，必須先清掉錯誤狀態再重新 ingest。不可在錯誤 release asset 仍存在時直接重跑 ingest，否則 README、SRT player、Mac-mini FIN 可能繼續吃到舊音檔。

清理順序：

1. 用 GitHub release asset digest 確認重複關係，記錄錯誤 stem、canonical stem、sha256、size。
2. 刪除錯誤季度的 GitHub release audio asset；只刪錯誤 stem，不刪 canonical stem。
3. 移除錯誤 stem 在 `audio_manifest.json` 的 URL。
4. 移除錯誤 stem 在 `audio_durations.json` 的顯示快取。
5. 移除或改正 `audio_metadata.json` 中錯誤 stem；若保留稽核紀錄，必須標 `status: duplicate` 與 `duplicate_of`，不得標 `ok`。
6. 刪除由錯誤音檔產生的 `{stem}_FIN.srt`；若 `{stem}_GT.srt` 是依錯 FIN 生成，也必須刪除。
7. 更新 README，讓錯誤季度的音檔、FIN、GT 欄位回到缺失狀態。
8. commit 清理狀態後，再重新執行 `ingest.py <stock_id> <year> <quarter> --push`。
9. re-ingest 成功後，立刻跑 targeted audit：

```bash
python skills/skill-investorconference-ingest/scripts/audit_audio_metadata.py \
  --stems <wrong_stem> <canonical_or_adjacent_stem> \
  --cache-dir /tmp \
  --update-durations \
  --fail-on-duplicate
```

驗收條件：

* 新音檔 sha256 不得等於任何不同 stem。
* `audio_manifest.json` URL 必須指向新 release asset。
* `audio_metadata.json` 的 stem 必須有 `sha256`、`size_bytes`、`duration_sec`、`status: ok`。
* Mac-mini FIN 只能在音檔通過 checksum gate 後生成。


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
* `scripts/audit_audio_metadata.py`：重新下載 release 音檔、計算 checksum/duration、更新 `audio_metadata.json` 並標示 duplicate。
* `scripts/migrate_audio_to_gh_releases.py`：歷史 GDrive 資源移轉至 GitHub。
* `scripts/fetch_yahoo_transcript.py`：透過瀏覽器抓取 Yahoo Finance 逐字稿的獨立工具。

## 🚀 使用方法
```bash
# 下載指定股票特定季度的音檔與可用材料；若有機器字幕，僅作為 FIN 初稿
python skills/skill-investorconference-ingest/scripts/ingest.py <stock_id> <year> <quarter> [--push]

# 更新 README 表格與持續更新
python skills/skill-investorconference-ingest/scripts/ingest.py --update-readme

# 稽核 release 音檔 checksum 與 duration
python skills/skill-investorconference-ingest/scripts/audit_audio_metadata.py --stems <stem...> --update-durations

# 批次轉換簡報 PDF 檔案
python skills/mac-mini-ocr/scripts/convert_ir_pdfs.py
```
