---
name: skill-youtube-channel-srt-keyframe-extract
description: 分析 FIN.srt/GT.srt 逐字稿，用 LLM 找出提及圖表／簡報／數字等視覺重點的時間點，下載對應影片並擷取該時間點的畫面存成帶時間碼的 PNG，索引 md 每張截圖都附實際逐字稿片段（可關鍵字搜尋）與 LLM 話題推測。
---

# 逐字稿關鍵畫面擷取技能 (skill-youtube-channel-srt-keyframe-extract)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.1.0（詳見 `metadata.json`） |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-youtube-channel-srt-keyframe-extract`） |
| 維護者 | wenchiehlee |
| 上游依賴 | `skill-mlx-api-client-whisper` 產出的 `FIN.srt`（或人工校正過的 `GT.srt`） |

## 這技能做什麼

1. 讀取 `whisper` pipeline 已完成的 `FIN.srt`（逐句含時間碼）
2. 透過共用的 `llm` 套件（`../llm`，`LLMClient.generate_json`，
   provider 備援鏈 codex → gemini → mlx）分析逐字稿內容，
   找出「講者開始一個新話題／新數字／切換到新公司或新圖表」的時間點與理由——
   財經口述影片畫面常隨句子開頭切換，不需要句子裡明講「看這張圖」才算候選；
   純語意判斷，不用關鍵字比對，但會排除明顯只是延續同一段話的句子
3. 用 `yt-dlp` 下載原始影片（僅暫存，用完即刪，音訊已經由 whisper pipeline 另外取得）
4. 用 `ffmpeg` 在每個時間點擷取一張畫面；用 8x8 average hash 跟前一張**保留下來**的畫面比
   對，Hamming distance ≤ 6（滿分 64）視為畫面沒真的切換（LLM 猜的話題邊界不一定對應到
   實際換頁），直接刪掉該張、不計入輸出——避免同一張投影片因為講者多講幾句話被連續截好
   幾張幾乎一樣的圖
5. 去重後存成 `data/{channel}/{stem}_keyframes/{stem}_{HHMMSS}.png`，並產生一份
   `data/{channel}/{stem}_keyframes.md` 索引，每個保留的時間碼對照四樣東西：縮圖連結、
   **該時間區段（到下一個保留時間點為止）的實際逐字稿片段**（逐字、可關鍵字搜尋——例如
   在多支影片的逐字稿裡搜關鍵字，找到談到的時間點後直接對到對應截圖）、以及 LLM 給的話題
   推測。srt 來源也是可點擊連結。方便瀏覽或做跨影片交叉比對，不用重新呼叫 LLM 就能查閱

## ⚠️ 與 `skill-mlx-api-client-whisper` 的關係

whisper pipeline 只下載/處理**音訊**；本技能是它的下游，需要**畫面**，因此會
另外用 `yt-dlp` 抓一份影片（暫存於系統 temp 目錄，擷取完 PNG 後自動刪除，
不落地保存原始影片檔）。兩者互不影響——`FIN.srt` 是唯一輸入依賴。

## ⚙️ 前置環境配置

### 1. 安裝依賴
```bash
pip install python-dotenv Pillow
# 共用 LLM 客戶端（登錄庫 wenchiehlee/llm 的 sibling checkout）：
uv add --editable "../llm"
# 或在 requirements.txt 中加入一行：-e ../llm
```
（`Pillow` 用於截圖的 average-hash 去重比對。）
另需系統已安裝 [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)、[`ffmpeg`](https://ffmpeg.org/)
與 [Node.js](https://nodejs.org/)（`node` 需在 PATH 上，`download_video()` 呼叫 `yt-dlp`
時固定帶 `--js-runtimes node`，解出 YouTube 簽章用）。

> ⚠️ **截圖解析度異常偏低（例如只有 640x360）或下載直接 403 時，先檢查 `yt-dlp --version`。**
> YouTube 常改格式偵測邏輯，`yt-dlp` 版本太舊（例如 >90 天沒更新）會導致偵測不到
> 1080p 等高解析度串流，只能抓到過時的 `18`（640x360）合併格式，甚至讓某些影片
> （尤其是直播 VOD）直接下載失敗，即使 `download_video()` 的格式選擇器
> （`bestvideo[height<=1080]+...`）跟 `--js-runtimes node` 本身都沒有問題。
> 用 `pip install -U yt-dlp` 更新到最新版即可解決；可用 `yt-dlp -F <video_url>`
> 確認實際可用的最高解析度。

### 2. 設定環境變數（`.env`）
本技能不直接呼叫任何 LLM API，而是透過共用的 `llm` 套件（`LLMClient`，
provider 備援鏈預設為 `codex → gemini → mlx`）。依你實際要用的 provider，
設定對應的環境變數即可（詳見 `../llm/README.md`）：
```env
# 例：走 Gemini（金鑰輪轉）
GEMINI_API_KEY=<你的 Gemini API key>
# 例：走 Codex-API-Server（NAS 端 codex-cli / gemini-cli 橋接）
CODEX_API_URL=<伺服器網址>
CODEX_API_KEY=<驗證金鑰>
# 例：走本機 MLX 推論
MLX_API_URL=<MLX 伺服器網址>
MLX_SERVER_API_KEY=<驗證金鑰>
```
> 不需要在本 repo 重複設定 `ANTHROPIC_API_KEY`——LLM 呼叫全部交給 `llm` 套件統一管理。

## 🚀 使用方式

### CLI
```bash
python scripts/keyframe_extract.py extract some-channel_dQw4w9WgXcQ \
    --srt data/some-channel/some-channel_dQw4w9WgXcQ_FIN.srt \
    --video-url https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

### 作為模組
```python
from scripts.keyframe_extract import KeyframeExtractor

KeyframeExtractor().extract(
    stem="some-channel_dQw4w9WgXcQ",
    srt_path="data/some-channel/some-channel_dQw4w9WgXcQ_FIN.srt",
    video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
)
```

`video_url` 需自行提供（重建自 stem 的 `video_id`：
`https://www.youtube.com/watch?v={video_id}` 即可，`video_id` 是 stem 尾端固定 11 碼）。

## 輸出

若逐字稿中沒有找到值得截圖的視覺重點時刻，不會下載影片，直接回傳空清單，但仍會產生
`{stem}_keyframes.md`（截圖數為 0）——確保每日排程的「還沒有 `_keyframes.md`」判斷條件
會被滿足，該支影片才不會被永遠排除在 README 內容索引之外、也不會每天重複嘗試。
去重後每個保留的時刻各存一張 PNG，檔名帶時間碼（`{stem}_{HHMMSS}.png`），方便對照原始
逐字稿的時間軸；同時在 `{stem}_keyframes/` 旁邊產生 `{stem}_keyframes.md`，用表格列出
每張截圖的時間碼、縮圖、該時間區段的實際逐字稿片段（可關鍵字搜尋）與 LLM 話題推測，
作為該影片的關鍵畫面索引。

## 🔄 版本管理與更新
- 唯一可信來源為 skills 登錄庫中的 `common/skill-youtube-channel-srt-keyframe-extract`
- 版本採語意化版本，記錄於 `metadata.json`
- 檢查並更新到登錄庫最新版本：
  ```bash
  python self_update.py
  ```
