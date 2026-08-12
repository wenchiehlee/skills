---
name: skill-youtube-channel-fetch
description: 從 YouTube 財經頻道下載最新影片的音訊，發佈為本 repo 的 GitHub Release 附件，並寫入 audio_manifest.json，供 skill-mlx-api-client-whisper 觸發轉錄。
---

# YouTube 頻道音訊擷取技能 (skill-youtube-channel-fetch)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-youtube-channel-fetch`） |
| 維護者 | wenchiehlee |
| 對應下游 | `skill-mlx-api-client-whisper`（消費本技能寫入的 `audio_manifest.json`） |

## 這技能做什麼

`skill-mlx-api-client-whisper` 只負責「manifest 裡已經有 audio_url 的 stem」開 issue 觸發轉錄——
它不負責從 YouTube 頻道抓新影片。本技能補上這一段：

1. 用 `yt-dlp` 列出頻道最新 N 支影片（`/videos` tab，預設由新到舊排序）
2. 對每支尚未出現在 manifest、也還沒有本地 `FIN.srt` 的影片，下載音訊（m4a）
3. 把音訊發佈成本 repo（`WHISPER_SOURCE_REPO`）的 GitHub Release 附件
   （tag = `audio-{stem}`），因為 Mac-mini pipeline 是用
   `gh release download` 拉音訊，`audio_url` 只是備援
4. 把 `{stem: browser_download_url}` 寫回 `audio_manifest.json`

寫完 manifest 後，接著呼叫既有的
`skill-mlx-api-client-whisper/scripts/whisper_issue_client.py sync` 即可依 manifest
開 issue 觸發轉錄（或本技能加 `--sync` 直接串接）。

## ⚙️ 前置環境配置

### 1. 安裝依賴
```bash
pip install requests python-dotenv
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

### 方式 C：作為模組整合進自己的排程腳本
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
