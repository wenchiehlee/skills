---
name: mlx-api-server-whisper
description: Mac-mini 上以 self-hosted GitHub Actions runner 執行的語音轉錄 pipeline（whisper 轉錄 → LLM postprocess → CER 校驗 → GT 校正迴圈），透過 issue 驅動、支援多種音訊來源（法說會、YouTube 財經影片…）。
---

# Mac-mini Whisper Pipeline 技能 (mlx-api-server-whisper)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.0.0（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee/Mac-mini/tree/main/Whisper-API-Server |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-mlx-api-server-whisper`） |
| 維護者 | wenchiehlee |
| 執行位置 | **Mac-mini 本機**，以 self-hosted GitHub Actions runner 身分執行 `run-pipeline.yml` |
| 對應 Caller Skill | `common/skill-mlx-api-client-whisper`（在音訊來源 repo 開 issue 觸發此 pipeline） |

## ⚠️ 與 `skill-mlx-api-server` 的關係（先讀這段）

這個技能**不是**常駐 HTTP API（沒有 `POST /whisper` 端點）。`skill-mlx-api-server`（Flask/Waitress，`/exec` `/ocr`）與這裡是**兩套完全獨立的執行模型**：

| | `skill-mlx-api-server` | `skill-mlx-api-server-whisper`（本技能） |
|---|---|---|
| 觸發 | 任何機器直接 `POST /exec`、`/ocr`，同步等 response | 來源 repo 開 GitHub issue（`generate-FIN` label），self-hosted runner 監聽 `issues: labeled` 事件 |
| 部署方式 | `deploy-mlx-api.yml` 把 `scripts/*.py` 複製到 `~/mlx-api/`，`launchd` 常駐 | 無獨立部署；runner 每次執行時 `actions/checkout` 整個 Mac-mini repo，直接跑 repo 內的 `Whisper-API-Server/*.py` |
| 執行時間 | 數秒~數分鐘，同步回應 | 單一 stem 完整跑完約 1–1.5 小時（多實驗轉錄＋postprocess＋CER），非同步、以 git commit 產出結果 |
| 併發控制 | `threading.Semaphore(MLX_MAX_CONCURRENT)` | GitHub Actions `concurrency: group` per issue/stem，單一 self-hosted runner 序列執行 |

原因見 [[project_fin_srt_pipeline]] 與 `skill-mlx-api-server` SKILL.md 裡的警示段落：這是一條有狀態、多步驟、跨 repo 讀寫的 pipeline，塞進單一無狀態 HTTP endpoint 需要重新發明 GitHub Actions 已經免費提供的觸發/併發/日誌機制，不值得。

## 🏗️ Pipeline 架構

```
[來源 repo：InvestorConference 或 YoutubeAudio.Fetch 等]
        ↓  開 issue（generate-FIN label + YAML metadata）
[Mac-mini repo：run-pipeline.yml, runs-on: self-hosted macOS]
        ↓  1. 拉音訊（gh release download，來自 source_repo）
        ↓  2. 拉最新 GT.srt（來自 source_repo，即時拉取，不做雙向同步）
        ↓  3. 多組實驗轉錄（whisper_poc.py，mlx-whisper / faster-whisper）
        ↓  4. postprocess.py --step best（rescue 多 exp 投票 + fix 字典修正）
        ↓  5. verify_cer.py（CER/WER 對 GT 評分，挑最佳版本 promote 成 FIN.srt）
        ↓  6. git commit/push 回 Mac-mini repo
        ↓  7. sync-gt-srt action：GT/FIN 推回 source_repo
```

## 📨 Issue Metadata Schema（v2，支援多來源）

```yaml
task_type: "generate_fin_srt"        # 或 "refine_fin_srt"（GT 在來源 repo 被人工修正後，重跑 CER/postprocess）
source_repo: "wenchiehlee-money/InvestorConference"   # 音訊/GT 所在 repo（owner/name）
source_type: "investor_conference"   # "investor_conference" | "youtube" —— 決定 stem 解析規則
stem: "2357_2025_q3"                 # 見下方 stem 規則
audio_url: "https://..."             # 選填，release asset 找不到時的備援下載來源
expected_fin_srt_path: "data/2357/2357_2025_q3_FIN.srt"
stock_id: "2357"                     # 選填：用來對應 company-configs/{stock_id}/whisper.yaml
```

> `source_repo`/`source_type` 未帶時預設為 `wenchiehlee-money/InvestorConference` / `investor_conference`，既有 IR issue **不需要改**就能繼續運作。

### Stem 規則（`source_type` 決定用哪一種）

| `source_type` | Stem 格式 | 解析出的 `group_id`（音訊/GT 存放資料夾） | 範例 |
|---|---|---|---|
| `investor_conference` | `{stock_id}_{year}_q{quarter}` | `stock_id` | `2357_2025_q3` |
| `youtube` | `{channel}_{video_id}` | `channel` | `some-channel_dQw4w9WgXcQ` |

YouTube `video_id` 固定 11 碼（`[A-Za-z0-9_-]{11}`），regex 用這點從 stem 尾端消解「channel 名稱裡也可能有底線」的歧義，不需要額外分隔符。

### 音訊/GT 目錄慣例（通用，不分來源）

```
../{basename(source_repo)}/{group_id}/{stem}.{m4a|mp3|wav}      # 音訊（gh release download）
../{basename(source_repo)}/{group_id}/{stem}_GT.srt             # GT（gh api contents，即時拉取）
```

## 🎓 語音辨識調校迴圈（company-configs + GT）

**這不是模型權重訓練**，而是「prompt 錨定 + 確定性修正字典 + CER 驅動選版」的組合：

1. **`company-configs/{stock_id}/whisper.yaml`**（選填）——`executives`/`products`/`terms`/`example_sentences` 灌進 whisper 的 `initial_prompt` 錨定人名/產品名/語境；`corrections`/`english_corrections` 是 `postprocess.py` 讀取的確定性字串取代字典（如 `廣打→廣達`）。
   - **`stock_id` 未帶時 fallback 到全域 `Whisper-API-Server/whisper.yaml`**（已驗證路徑，QCOM 沒有 company config 時就是這樣運作）——YouTube 影片若未指定 `stock_id`，一樣安全運作。
   - 若 YouTube 影片明確討論特定個股（例如評論台積電），直接在 issue metadata 填對應 `stock_id`，即可沿用該公司既有的 company-configs。
2. **GT.srt 是唯一真相來源**：每次 pipeline 執行都從 `source_repo` 即時拉最新 GT（pull-on-demand，見 [[feedback_refine_gt_via_issue]]），餵給 `verify_cer.py` 算 CER，CER 最低的版本 promote 成 `FIN.srt`。
3. **`generate_fin_srt` vs `refine_fin_srt`**：前者從音訊全新轉錄；後者用於 GT 在來源端被人工修正後，重新跑 CER 評分/postprocess（通常搭配 `skip_transcribe: true`，跳過最耗時的轉錄步驟，兩者程式邏輯上目前完全一致，只差在呼叫端如何設定 metadata）。
4. **設計原則（人工把關，非自動化）**：語境相依的修正（例如某次特例誤植）只留在 GT，不會自動被寫進 `company-configs` 的 `corrections` 字典；只有可泛化的系統性 ASR 錯誤才由人工判斷後手動 promote 進 config。**目前沒有、也不打算做自動從 GT 學習 corrections 字典的機制。**

## 📦 技能結構說明

```text
skill-mlx-api-server-whisper/
├── SKILL.md               # 本檔案
├── metadata.json
└── self_update.py
```

本技能刻意**不複製** `Whisper-API-Server/*.py` 到 skill 資料夾——pipeline 腳本的唯一來源是 Mac-mini repo 本身（self-hosted runner 執行時已經 checkout 整個 repo，沒有額外部署步驟）。本技能封裝的是**跨來源通用的 metadata schema、stem 規則、目錄慣例與調校原則**，實際腳本異動請直接改 `Whisper-API-Server/` 與 `.github/workflows/run-pipeline.yml`。

## 🔄 版本管理與更新

- 唯一可信來源為 skills 登錄庫中的 `common/skill-mlx-api-server-whisper`
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json`
- 從登錄庫更新到最新版本：
  ```bash
  python self_update.py
  ```
- 修改此技能時，請先更新登錄庫版本號，再同步到 Mac-mini
