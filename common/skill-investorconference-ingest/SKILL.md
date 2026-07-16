---
name: skill-investorconference-ingest
version: 1.2.5
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

### 公司 IR / MOPS 來源選擇與日期窗口檢查

Ingest 不得只信任 MOPS 查詢結果的第一個影音檔。部分公司或 MOPS 查詢會回傳該公司最新法說影音，即使目標是前一季度。

### 來源層級與衝突處理

Ingest 必須把來源分成兩層，且不得讓二級來源覆蓋一級來源的季度、日期、檔案類型或公司正式材料判定。

| 層級 | 來源 | 可用用途 | 限制 |
| :--- | :--- | :--- | :--- |
| 一級來源 | 公司 IR 官網、公司正式 replay/webcast、公司正式 PDF、MOPS/TWSE 官方公告、SEC filing（美股） | 決定季度、日期、檔案類型、是否為正式公司材料；落檔與 README metadata 的主依據 | 若一級來源彼此衝突，必須保留衝突紀錄並降信心，不得靜默覆蓋 |
| 二級來源 | FinmoConf、AlphaSpread、Yahoo Finance transcript、AlphaMemo、第三方法說會索引或摘要平台 | 發現資料、補逐字稿、補 speaker/Q&A、交叉驗證、產生候選來源清單 | 不得覆蓋一級來源的季度/日期/檔案類型；不得單獨作為官方音檔或官方簡報判定 |

若一級與二級來源衝突，例如第三方索引把公司官方 `2026 Q2` 法說會標成 `2026Q3`：

1. README、manifest、metadata 必須以一級來源為準。
2. 二級來源只可記錄為 discovery/reference URL。
3. 在 `audio_metadata.json`、sidecar metadata、issue draft 或 ingest log 中記錄 mismatch，包含來源 URL、二級來源標籤、官方判定與處理結果。
4. 不得因二級來源存在而跳過官方頁面、官方 PDF、官方 replay 或 MOPS/TWSE 的核對。

來源優先順序：

1. 已知的 quarter-specific 官方公司 IR / seminar / replay URL。
2. 公司 IR seminar 頁中與目標季度名稱及會議日期一致的影音檔。
3. MOPS video/PDF，但必須通過會議日期窗口檢查。
4. 其他搜尋或 fallback。

日期窗口規則：

* `Q4` 法說會通常落在下一年度 `01` 至 `04` 月。
* `Q1` 法說會通常落在同年度 `04` 至 `06` 月。
* `Q2` 法說會通常落在同年度 `07` 至 `09` 月。
* `Q3` 法說會通常落在同年度 `10` 至 `12` 月。

若 MOPS 回傳影音或 PDF 檔名日期不在目標窗口，必須拒絕該 asset，不得下載、不得更新 manifest，也不得產 FIN。若公司 IR 頁列出更精確的目標季度影音，應將其加入 quarter-specific direct source，讓後續 re-ingest 可重現。

驗證時不得用固定 45 或 60 分鐘作為正確音檔門檻；部分官方法說 replay 可能只有十幾分鐘。長度檢查只用來拒絕明顯空檔或截斷檔，正確性仍以官方來源、目標季度名稱、會議日期窗口與 checksum 去重為主。

### Playwright browser-download fallback

許多公司 IR 站、webcast 平台或新版官方頁面會使用 Cloudflare、JavaScript challenge、registration flow、動態連結或防 hotlink 機制。若 `curl`、`requests`、`yt-dlp` 或 MOPS fallback 取得的是 HTML challenge、登入頁、空檔或錯誤 content-type，不可直接判定材料不存在；必須改用 Playwright/Chromium 以真瀏覽器 context 下載。

使用規則：

1. 先以 Playwright 開啟一級來源頁面作為 `warmup-url`，取得 cookie、session 與動態頁面狀態。
2. 用同一個 browser context request 下載 PDF、音檔或 webcast material URL，並帶入官方頁 `Referer`。
3. 下載後必須驗證 HTTP status、`content-type`、檔案大小與 magic bytes，例如 PDF 必須以 `%PDF` 開頭，m4a/mp4 前段必須含 `ftyp`。
4. 若 browser download 成功，應以本地官方檔案更新 README；若只取得外部 registration form，不得產生音檔、FIN 或 GT。
5. 若需要提交姓名/email 才能取得 replay 或 webcast，必須先取得使用者明確同意與使用者提供的資料；不得使用假個資自動送出公司表單。
6. 使用者提供的姓名、email、公司、職稱等表單欄位必須存放在 ignored `.env` 或執行環境變數中；不得寫入 tracked script、README、metadata、issue、commit message 或 log artifact。執行前需用 `git check-ignore -v .env` 或等效方式確認不會被提交。
7. 若 Playwright 只能取得 PDF 但不能取得 audio/replay，仍應落檔 PDF/MD，並在 sidecar metadata 記錄 audio 缺口。
8. 若 webcast backend 只回傳 live playlist，但 playlist 回 404/403/HTML、player 已切到 `wordCardType=picture` 或結束圖、或 `/live` 端點沒有媒體內容，不得建立 `.m4a`、FIN 或 GT；必須在 sidecar 記錄已測試的 playlist、player fallback、HTTP status、content-type 與結論。

可重用下載工具：

```bash
python skills/skill-investorconference-ingest/scripts/download_with_playwright.py \
  --warmup-url https://investor.tsmc.com/chinese/quarterly-results/2026/q2 \
  --kind pdf \
  --download data/2330/2330_2026_q2_ir.pdf=https://.../2Q26%20Presentation%20%28C%29.pdf
```

> [!IMPORTANT]
> browser-download fallback 是 ingest 的一級材料取得流程，不是 digest 的推論流程。成功取得的檔案仍必須通過 checksum/magic-byte/content-type gate，並產生 Markdown sidecar 供 digest 使用。

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
* `scripts/download_with_playwright.py`：以 Playwright/Chromium browser context 下載受 Cloudflare、JS challenge 或 hotlink 防護影響的官方 PDF/影音材料，並驗證 content-type 與 magic bytes。

## 🚀 使用方法
```bash
# 下載指定股票特定季度的音檔與可用材料；若有機器字幕，僅作為 FIN 初稿
python skills/skill-investorconference-ingest/scripts/ingest.py <stock_id> <year> <quarter> [--push]

# 更新 README 表格與持續更新
python skills/skill-investorconference-ingest/scripts/ingest.py --update-readme

# 稽核 release 音檔 checksum 與 duration
python skills/skill-investorconference-ingest/scripts/audit_audio_metadata.py --stems <stem...> --update-durations

# 使用 Playwright browser context 下載受保護官方材料
python skills/skill-investorconference-ingest/scripts/download_with_playwright.py \
  --warmup-url <official_page_url> \
  --kind pdf \
  --download <local_path.pdf>=<official_pdf_url>

# 批次轉換簡報 PDF 檔案
python skills/mac-mini-ocr/scripts/convert_ir_pdfs.py
```
