---
name: skill-youtube-podcast-feed
description: Build, validate, and maintain manifest-driven podcast RSS feeds for YouTube audio archives, including correct audio enclosure headers, Podcasting 2.0 WebVTT transcripts, real-time player lyrics, per-channel and combined feeds, and GitHub Pages artifacts.
---

# YouTube Podcast Feed

把 YouTube 音訊 archive 的 manifest、影片 metadata、逐字稿與 keyframe 資料，穩定轉成可被 Apple Podcasts、Overcast 與其他 podcast app 訂閱的 RSS feed。預設繁體中文；回答先給結果，再說明必要的資料來源與驗證。

## 任務入口

| 使用者任務 | 工作入口 | 主要交付物 |
|---|---|---|
| 產生單一頻道 feed | `generate_podcast_feed.py <channel>` | `docs/<channel>/feed.xml`、對應 VTT |
| 產生全頻道 feed | `generate_podcast_feed.py --all` | `docs/feed.xml`、對應 VTT |
| 查錯或修復 feed | 先檢查 manifest、metadata、audio URL、transcript | 可解析 RSS、可取得音訊與 VTT |
| 維護 podcast feed workflow | 保留本文件的不變條件，再更新 consumer repo script | 可重現的生成與驗證流程 |
| 啟用即時歌詞／逐字稿 | 使用 episode 的 WebVTT track 與 `cuechange` | 播放、跳轉、暫停都與目前 cue 同步 |
| 部署 VTT 與 feed | 執行 generator，再由 GitHub Actions commit `docs/`；GitHub Pages 提供 HTTPS 靜態檔 | feed、VTT 與 URL 同步可取得 |
| 部署技能 | 更新 `metadata.json` 版本，再執行 `self_update.py --deploy-all` 或同步 registry 副本 | registry 與 consumer 副本一致 |

## 核心資料流

```text
audio_manifest.json + data/.video_metadata.json
        ↓
episode selection and metadata normalization
        ↓
audio enclosure + image + Podcasting 2.0 transcript
        ↓
docs/<channel>/feed.xml and docs/<channel>/transcripts/*.vtt
        ↓
GitHub Pages / Cloudflare Worker / podcast app
```

只收錄 `audio_manifest.json` 中已經有音訊 URL 的 episode。不要因為有 YouTube 影片、keyframe 或字幕，就在沒有 release audio 的情況下新增 RSS item。

## 不變條件

- 音訊 enclosure 使用 Cloudflare Worker URL；Worker 對 GitHub Release bytes 補上 `Content-Type: audio/mp4`、移除附件下載 disposition，並保留 Range request。
- RSS 必須包含 `xmlns:itunes`、`xmlns:podcast` 與 `xmlns:atom`；每一集的 `<guid>` 使用穩定 stem 且 `isPermaLink="false"`。
- 有 transcript 時，`<podcast:transcript>` 指向穩定 HTTPS `.vtt`，並包含 `type="text/vtt"`、`rel="captions"`、`language="zh"` 與 `lang="zh-TW"`。不要把 pseudo-SRT 直接宣告成 VTT。
- repository 的 `*_FIN.srt`／`*_GT.srt` 是 pseudo-SRT：cue 形如 `(MM:SS.mmm) text`，MM 可超過 59。轉檔時要正確處理長分鐘數、依下一 cue 結束，最後一 cue 使用合理 fallback duration。
- 每次生成要可重複執行；VTT 與 feed 內容只由目前 manifest、metadata、字幕與遠端音訊 HEAD 結果決定。
- `Content-Length` HEAD 失敗時使用 `0`，不要因為單一遠端檢查失敗而阻止整份 feed 生成。
- combined feed 的標題以 `【頻道名稱】` 標示來源，並在 item 保留頻道 author／image，避免單一訂閱失去來源辨識。
- 不把 RSS feed 的產生誤稱為 podcast hosting；音檔仍存於 GitHub Release，Pages 只提供 feed、VTT 與靜態資產。
- 外部訂閱的 enclosure、transcript 與 feed self-link 必須是穩定 HTTPS URL；GUID 必須跨 feed 更新保持不變。
- 本 repo 目前產出 sentence-level VTT；只有輸入含有 word timestamps 時，才可宣稱 word-level lyrics，不得由 LLM 臆測字詞時間。

## 生成與檢查

在 consumer repository root 執行：

```bash
python scripts/generate_podcast_feed.py fubonsec
python scripts/generate_podcast_feed.py --all
python skills/skill-youtube-podcast-feed/scripts/validate_podcast_feed.py docs/fubonsec/feed.xml
```

生成前確認：

1. `audio_manifest.json` 可解析，stem 仍符合 `channel_<11-char-video-id>` 慣例。
2. `data/.video_metadata.json` 缺少項目時，沿用既有 metadata fetch/cache 流程，不把暫時缺資料寫成錯誤日期；無日期時排序只能視為 fallback。
3. 每個有字幕的 item 都會在 `docs/<channel>/transcripts/<stem>.vtt` 產生可讀檔案。
4. `docs/<channel>/feed.xml` 是 well-formed XML，enclosure、transcript、guid 與 self link 都存在且指向正確 episode。
5. 生成完成後，將 `docs/`（包含 feed XML 與 transcripts/*.vtt）納入部署 commit；GitHub Pages 必須能以 HTTPS 取得同一路徑。
6. 只在使用者要求或部署流程明確包含時，才 commit／push registry 或其他 consumer repo；不要把生成的音檔或秘密推送進 repository。

## 驗證重點

驗證不能只檢查 XML 能否 parse，還要檢查：

- 每個 enclosure URL 可由 Worker 路徑解析出 stem；
- transcript URL 的 `.vtt` 檔案存在，且以 `WEBVTT` 開頭；
- 播放器為每集提供 `.vtt` track 與 live lyrics region，並在 `cuechange` 時更新文字；
- cue timestamp 單調遞增、end 大於 start；
- feed 中沒有重複 guid；
- feed item 數量與輸入 manifest 中該 channel 的 audio-backed episode 數量一致（合併 feed 則是所有 channel 總和）。

## 版本與同步

這個 skill 的可信來源是 registry 中的 `common/skill-youtube-podcast-feed`。生成器與 GitHub Actions 都必須把 VTT 寫入並部署到 `docs/<channel>/transcripts/`，不能只把 URL 寫進 RSS 而遺漏檔案。consumer repo 的 `skills/skill-youtube-podcast-feed` 是部署副本；改動後同步 `metadata.json` 所列 files 並遞增 semantic version。若 registry repository 有未提交的使用者變更，先保留，不用 reset 或覆蓋。

