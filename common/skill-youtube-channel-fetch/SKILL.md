---
name: skill-youtube-channel-fetch
description: 從 YouTube 財經頻道下載最新影片，優先嘗試官方逐字稿（手動字幕存成單獨的 GT.srt、不寫 FIN.srt；自動字幕直接當 FIN.srt）；沒有的才下載音訊、發佈為本 repo 的 GitHub Release 附件，並寫入 audio_manifest.json 供 skill-mlx-api-client-whisper 觸發轉錄。另提供 refine 子指令，針對只有 GT.srt、尚未經過 whisper 的 stem 補觸發 pipeline 的 refine_fin_srt。
---

# YouTube 頻道音訊擷取技能 (skill-youtube-channel-fetch)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.4.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-youtube-channel-fetch`） |
| 維護者 | wenchiehlee |
| 對應下游 | `skill-mlx-api-client-whisper`（消費本技能寫入的 `audio_manifest.json`，及本技能 `refine` 直接呼叫的 `open_fin_request`） |

## 這技能做什麼

`skill-mlx-api-client-whisper` 只負責「manifest 裡已經有 audio_url 的 stem」開 issue 觸發轉錄——
它不負責從 YouTube 頻道抓新影片。本技能補上這一段：

1. 用 `yt-dlp` 列出頻道影片，預設「最新 N 支」。**只有在傳入不帶 `/videos`／`/streams`
   後綴的裸頻道網址時，才會合併 `/videos` + `/streams` 兩個 tab**（由新到舊排序——像每日
   直播存檔這類頻道，日常內容大多發佈在 `/streams`，只查 `/videos` 會漏掉）；若網址本身已
   明確帶 `/videos` 或 `/streams` 後綴，就只查那一個 tab（例如目前 `channels.json` 裡
   `yutinghaofinance` 就是固定指到 `.../streams`，只掃 streams tab，不會合併 `/videos`）。
   也可以改成「日期區間」模式（見下方方式 E），抓某段期間內的全部影片
2. 對每支尚未出現在 manifest、也還沒有本地 `FIN.srt` 或 `GT.srt` 的影片，**先用
   `youtube-transcript-api` 查詢 YouTube 官方逐字稿**，依 `DEFAULT_TRANSCRIPT_LANGUAGES`
   語言優先序嘗試：`zh-TW, zh-Hant, zh, zh-Hans, zh-CN, en`。依字幕來源分兩種處理：
   - **YouTube 自動語音辨識**（`is_generated=True`，品質跟 whisper 自己的輸出差不多）
     → 直接轉成本 repo 的 `FIN.srt` 格式寫入 `data/{channel}/{stem}_FIN.srt`，這支影片
     完全不進音訊/manifest/whisper 流程。不值得再花一次 `refine_fin_srt` 成本。
   - **創作者手動上傳字幕**（`is_generated=False`，品質接近真人校正，可視為 ground truth）
     → 只寫成 `data/{channel}/{stem}_GT.srt`，**不寫** `FIN.srt`；`GT.srt` 沒有對應
     `FIN.srt` 本身就是完整、有效的結束狀態——下游步驟（例如
     `skill-youtube-channel-srt-keyframe-extract` 或每日排程）在找不到 `FIN.srt` 時
     會直接改用 `GT.srt` 當來源逐字稿，不需要等待或補一份重複內容的 `FIN.srt`。
     `FIN.srt` 只保留給「pipeline 真的產生過、經過評分」的逐字稿。之後如果想要一份
     格式跟其他 FIN.srt 一致、經過 CER 評分的版本，可用 `refine` 子指令，針對性地補
     下載音訊並觸發 Mac-mini pipeline 的 `refine_fin_srt`（跳過最貴的多組實驗轉錄
     步驟，但仍需 audio_url）。
   - **兩者皆無**（字幕被關閉，或只有不相關語言）→ 才繼續走原本流程：下載音訊（m4a）
3. 把音訊發佈成本 repo（`WHISPER_SOURCE_REPO`）的 GitHub Release 附件
   （tag = `audio-{stem}`），因為 Mac-mini pipeline 是用
   `gh release download` 拉音訊，`audio_url` 只是備援
4. 把 `{stem: browser_download_url}` 寫回 `audio_manifest.json`

寫完 manifest 後，接著呼叫既有的
`skill-mlx-api-client-whisper/scripts/whisper_issue_client.py sync` 即可依 manifest
開 issue 觸發轉錄（或本技能加 `--sync` 直接串接）——這一步只會處理「完全沒有官方逐字稿」
的影片；手動字幕的 refine 走法二獨立的 `refine` 子指令。

> 若某些頻道就是希望永遠走完整 whisper 流程，用 `fetch ... --no-transcript` 跳過整個
> 官方逐字稿檢查。

## ⚙️ 前置環境配置

### 1. 安裝依賴
```bash
pip install requests python-dotenv youtube-transcript-api
```
另需系統已安裝 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) CLI（`pip install yt-dlp` 或對應套件管理器），
以及 [Node.js](https://nodejs.org/)（`node` 需在 PATH 上）——`yt-dlp` 現在需要 JS runtime
才能解出 YouTube 的簽章，本技能所有呼叫都帶 `--js-runtimes node`；沒有 node 會導致部分
影片（尤其是直播 VOD）下載直接失敗（`403 Forbidden`）。

### 2. 設定環境變數（`.env`）
```env
WHISPER_SOURCE_REPO=wenchiehlee-money/YoutubeAudio.Fetch   # 本 repo（音訊/GT 的家）
REPO_FILE_SYNC_WENCHIEHLEE_MONEY=<PAT，對 WHISPER_SOURCE_REPO 需要 Contents: Read and write>
```
> 變數名沿用 `skill-mlx-api-client-whisper` 的 `REPO_FILE_SYNC_<OWNER>_<...>` 命名慣例，
> 只是這裡對應的是**來源 repo**（`WHISPER_SOURCE_REPO`）而非目標 repo。兩者是**不同範圍**
> 的 PAT——`skill-mlx-api-client-whisper` 用的 token 只需要 target repo 的 Issues 權限；
> 本技能要在**本 repo**建立 Release 並上傳附件，因此需要 Contents 讀寫權限，不能共用同一把 token。
> 若沒有對應的 `REPO_FILE_SYNC_*` 變數，會依序 fallback 讀取 `YOUTUBE_FETCH_TOKEN`、`GH_TOKEN`。

## 🚀 使用方式

### 方式 A：抓最新 5 支影片音訊
```bash
python scripts/channel_fetch.py fetch https://www.youtube.com/@fubonsec --limit 5
```

### 方式 B：抓完直接觸發轉錄 pipeline
```bash
python scripts/channel_fetch.py fetch https://www.youtube.com/@fubonsec --limit 5 --sync
```
`--sync` 會在寫完 manifest 後，載入同層 `skill-mlx-api-client-whisper` 並呼叫
`WhisperIssueClient().sync_manifest(...)`——因此兩個技能需部署在同一個 `skills/` 目錄下
（如同本 repo 現況）。

### 方式 C：跳過官方逐字稿檢查，永遠走音訊+whisper
```bash
python scripts/channel_fetch.py fetch https://www.youtube.com/@fubonsec --limit 5 --no-transcript
```

### 方式 D：手動字幕 GT.srt 補 refine（下載音訊＋觸發 refine_fin_srt）
```bash
python scripts/channel_fetch.py refine
# 或只針對特定 stem：
python scripts/channel_fetch.py refine --stem yutinghaofinance_v7TpiWK5DTQ
```
會掃描 `data/*/*_GT.srt`，找出**有 `GT.srt` 但還沒有對應 `FIN.srt`**（尚未經 whisper
pipeline 處理）的 stem，逐一下載音訊、發佈 Release、更新 manifest，並呼叫
`WhisperIssueClient().open_fin_request(stem, audio_url, task_type="refine_fin_srt")`。
Mac-mini pipeline 完成後會在同一路徑寫入真正的 `FIN.srt`，之後這個 stem 就不會再被
`refine` 掃到（`fin_path.exists()` 已經為真）。

### 方式 E：抓某段日期區間內的全部影片（而非「最新 N 支」）
```bash
python scripts/channel_fetch.py fetch https://www.youtube.com/@yutinghaofinance \
    --date-after 2026-08-01 --date-before 2026-08-07
```
`--date-after`/`--date-before` 可只給一個（開放區間）；`--flat-playlist` 列表本身不帶日期，
所以會逐一查詢候選影片的實際上傳時間來過濾（`ChannelFetcher.DATE_RANGE_CANDIDATE_POOL`
是每個 tab 掃描的安全上限）。給了日期區間時 `--limit` 預設關閉（回傳區間內全部影片），
除非另外明確指定。

### 方式 F：每日自動排程
`.github/workflows/daily-channel-fetch.yml` 每天對 repo 根目錄 `channels.json` 列出的每個
頻道跑 `fetch --limit 5 --sync`；要追蹤新頻道，編輯 `channels.json` 加一行 URL 即可。細節
與所需的 GitHub Actions Secrets 見本 repo 根目錄 README.md 的「自動化（每日排程）」一節。

### 方式 G：作為模組整合進自己的排程腳本
```python
from scripts.channel_fetch import ChannelFetcher

fetcher = ChannelFetcher()  # 讀 .env 裡的 WHISPER_SOURCE_REPO / YOUTUBE_FETCH_TOKEN
fetcher.fetch_channel("https://www.youtube.com/@fubonsec", limit=5)
```

## Stem 命名慣例

`stem = {channel_slug}_{video_id}`，`channel_slug` 由頻道 handle／標題正規化而來
（僅留英數字，其餘轉為 `-`，小寫），`video_id` 為 yt-dlp 回傳的固定 11 碼 YouTube ID——
與 `skill-mlx-api-client-whisper` 的 `STEM_PATTERNS["youtube"]` 解析規則對稱。

## 🔄 版本管理與更新
- 唯一可信來源為 skills 登錄庫中的 `common/skill-youtube-channel-fetch`
- 版本採語意化版本，記錄於 `metadata.json`
- 檢查並更新到登錄庫最新版本：
  ```bash
  python self_update.py
  ```
