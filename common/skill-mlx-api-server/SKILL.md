---
name: skill-mlx-api-server
description: 在 Mac-mini (Apple Silicon M4) 本機執行的 AI 推理服務，提供 Baidu Unlimited-OCR 文件轉錄（/ocr）與 MLX LLM 推理（/exec，Qwen3.5/Gemma4），以 Flask/Waitress 常駐服務形式運行。
---

# Mac-mini MLX API Server 技能 (mlx-api-server)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.1.1（詳見 `metadata.json`） |
| 來源 | https://github.com/wenchiehlee/Mac-mini/tree/main/skills/skill-mlx-api-server/scripts |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-mlx-api-server`） |
| 維護者 | wenchiehlee |
| 執行位置 | **Mac-mini 本機**（Apple Silicon M4，24 GB Unified Memory） |
| 對應 Caller Skill | `common/skill-mac-mini-ocr`（在外部機器呼叫此服務） |

此技能封裝了運行於 Mac-mini 上的 AI 推理伺服器，提供兩大核心服務：
1. **`POST /ocr`** — Baidu Unlimited-OCR 文件轉錄，將 PDF 或圖片轉為 Markdown
2. **`POST /exec`** — MLX 本地 LLM 推理，支援 Qwen3.5-9B 與 Gemma-4 模型

服務透過 Tailscale VPN 對外提供，由 `launchd` (`com.mlx.apiserver`) 常駐管理，GitHub Actions 每 6 小時自動健康檢查並於異常時自動恢復。

> ⚠️ **Whisper 語音轉錄不是本服務的端點。** `mlx-api-server-whisper/whisper_poc.py` 是獨立腳本，由 `run-pipeline.yml`（`runs-on: [self-hosted, macOS]`）在 Mac-mini 上以 self-hosted GitHub Actions runner **本機直接執行**，不經過 `/exec`、不受 `auth.py` / `MLX_ALLOWED_MODELS` 限制，也**不佔用**這裡的 `threading.Semaphore(MLX_MAX_CONCURRENT)` 併發額度。它只是共用同一台 Mac-mini 與同一組 Amplitude 埋點（`app_name=whisper-transcription(-stage)`），因此在 `mlx-api-server.md` 的統計表（`model=whisper-large-v3`）裡會混雜出現——**不代表 whisper 可以透過本 API server 呼叫**。
>
> 觸發方式是 InvestorConference repo 偵測到缺少 `FIN.srt` 時，在 Mac-mini repo 開一張帶 `generate-FIN` label 與 YAML metadata（`task_type/stem/audio_url` 等）的 issue，`run-pipeline.yml` 監聽 `issues: types: [labeled]` 接手執行「轉錄（多組 exp）→ postprocess → CER 比對 → 挑最佳版本 → git commit/push → sync 回 InvestorConference」整條有狀態流程。維持此設計的理由：音訊檔案本來就在 Mac-mini 本機（runner 直接讀 `../InvestorConference/{stock_id}/{stem}.m4a`，見專案記憶 `project_audio_paths`），且流程本身涉及多步驟編排與跨 repo git 讀寫，不適合改成單一無狀態 HTTP endpoint（會需要重造非同步 job 佇列、大檔案上傳、以及 GitHub Actions 已經免費提供的觸發/併發/日誌機制）。

## 📦 技能結構說明

```text
skill-mlx-api-server/
├── SKILL.md               # 技能描述與操作指引（本檔案）
├── metadata.json          # 機器可讀 metadata（名稱、版本、來源），供版本檢查使用
├── self_update.py         # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    ├── server.py          # Flask/Waitress API 伺服器主程式（路由 /exec /ocr /health）
    ├── auth.py            # X-API-Key 認證裝飾器（hmac.compare_digest 防時序攻擊）
    ├── config.py          # 設定載入（讀取 .env，含必填欄位驗證）
    ├── executor.py        # MLX 執行引擎（subprocess 管理、Semaphore 並發控制）
    ├── ocr_run.py         # Baidu Unlimited-OCR 子程序（PyTorch + MPS 加速）
    ├── requirements.txt   # Python 依賴清單（含已知相容性限制說明）
    ├── bench_params.py    # 效能基準測試工具（kv-bits / max-kv-size 對照）
    └── test_qwen3_thinking.py  # Qwen3 enable_thinking=False 迴歸測試
```

> 本技能是「真正的程式碼來源」（不像 `skill-mlx-api-server-whisper` 只留文件）：`scripts/*.py` 是唯一版本，`deploy-mlx-api.yml`／`health-mlx-api.yml`／`bench-params.yml`／`test-qwen3-thinking.yml` 都直接從這裡讀取，不再有 `mlx-api-server/*.py` 這份舊路徑的副本。

## 🏗️ 架構概覽

```
[外部機器 — Windows / GitHub Actions / Mac]
        ↓  skill-mac-mini-ocr (Caller)
        ↓  HTTP POST /ocr 或 /exec（X-API-Key header）
[mac-mini.tail28f10.ts.net:5001]  ← Tailscale VPN
        ↓
[Flask/Waitress server.py :5001]  ← com.mlx.apiserver (launchd 常駐)
        ↓  認證（auth.py）+ 設定（config.py）
        ├── /exec → executor.run()
        │           ├── mlx_lm generate（Qwen3.5，enable_thinking=False）
        │           └── mlx_vlm generate（Gemma4，VLM）
        └── /ocr  → executor.run_ocr() → subprocess ocr_run.py
                    └── baidu/Unlimited-OCR（PyTorch + MPS）
```

**網路：**
| 項目 | 值 |
|------|----|
| MagicDNS | `mac-mini.tail28f10.ts.net` |
| Tailscale IP | `100.108.116.38` |
| 監聽埠 | `5001`（Waitress/Flask） |

## 🤖 可用模型

| 別名 | HuggingFace 模型 | 框架 | 速度 | Peak Memory |
|------|-----------------|------|------|-------------|
| `mlx-qwen3`, `qwen3-mlx` | `mlx-community/Qwen3.5-9B-MLX-4bit` | `mlx_lm` | ~21 tok/s | ~8 GB |
| `mlx-gemma4` | `mlx-community/gemma-4-e4b-it-8bit` | `mlx_vlm` | ~24 tok/s | 9.0 GB |

> **記憶體規則：** MLX peak memory ≈ 磁碟大小 × 1.05–1.1。24 GB 機器上最多同時載入 ~20 GB 模型。

### 新增模型

1. 在 `executor.py` 的 `MODEL_MAP` 新增別名：
   ```python
   MODEL_MAP = {
       "mlx-qwen3": "mlx-community/Qwen3.5-9B-MLX-4bit",
       "my-new-model": "mlx-community/SomeModel-4bit",  # ← 新增
   }
   ```
2. 若為 VLM，加入 `_VLM_REPOS`；若為 thinking model，加入 `_NOTHINK_REPOS`。
3. 更新 `MLX_ALLOWED_MODELS` 環境變數（或 GitHub Vars）。

## 📊 AI Model Usage 統計

`skill-mlx-api-server` 會自行產生 AI 結果，因此 server 端必須直接送出 normalized `llm_call`，不能只依賴呼叫端：

| Endpoint | `service` | `stage` | `provider` | `model` | `model_repo` |
|----------|-----------|---------|------------|---------|--------------|
| `/exec` default | `mlx-api-server` | `exec` | `mlx` | `mlx-qwen3` | `mlx-community/Qwen3.5-9B-MLX-4bit` |
| `/exec` `model=mlx-gemma4` | `mlx-api-server` | `exec` | `mlx` | `mlx-gemma4` | `mlx-community/gemma-4-e4b-it-8bit` |
| `/ocr` | `mlx-api-server` | `ocr` | `baidu-ocr` | `baidu/Unlimited-OCR` | `baidu/Unlimited-OCR` |

呼叫端應傳 `X-App-Name`，server 端用它填入 `app_name`；沒有提供時 `/exec` fallback 為 `MLX-Exec`，`/ocr` fallback 為 `Baidu-OCR`。跨服務 README 應使用 `app_name × model` last-7-days 來回答單一應用的模型使用來源。

## ⚙️ 環境變數規格

| 變數名 | 必填 | 預設值 | 說明 |
|--------|------|--------|------|
| `MLX_SERVER_API_KEY` | ✅ | — | API 金鑰（≥32 chars），生成：`python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `MLX_SERVER_HOST` | 可選 | `127.0.0.1` | 監聽位址（`0.0.0.0` 表示對所有介面開放） |
| `MLX_SERVER_PORT` | 可選 | `5001` | 監聽埠 |
| `MLX_ALLOWED_MODELS` | 可選 | `mlx-qwen3,mlx-gemma4` | 允許的模型別名，逗號分隔 |
| `MLX_TIMEOUT` | 可選 | `180` | subprocess timeout 秒數（部署時設為 `900`） |
| `MLX_MAX_CONCURRENT` | 可選 | `3` | 最大並發請求數（`threading.Semaphore`） |
| `MLX_MAX_PROMPT_LENGTH` | 可選 | `16000` | prompt 最大字元數 |
| `AMPLITUDE_API_KEY` | 可選 | — | Amplitude 埋點 API Key（省略則不送事件） |

`.env` 範例（`~/mlx-api/.env`，**務必 chmod 600**）：
```env
MLX_SERVER_API_KEY=<your-key-≥32-chars>
MLX_SERVER_HOST=0.0.0.0
MLX_SERVER_PORT=5001
MLX_ALLOWED_MODELS=mlx-qwen3,mlx-gemma4,qwen3-mlx
MLX_TIMEOUT=900
MLX_MAX_CONCURRENT=3
AMPLITUDE_API_KEY=<optional>
```

## 🚀 部署流程

### 首次部署（對應 `deploy-mlx-api.yml`）

```bash
# 1. 建立 Python venv（使用 Homebrew Python 3.11）
/opt/homebrew/bin/python3.11 -m venv ~/mlx-api/venv
source ~/mlx-api/venv/bin/activate

# 2. 安裝依賴
#    ⚠️ transformers 必須 <5.0.0（baidu/Unlimited-OCR 尚不支援 transformers 5.x）
pip install --upgrade pip
pip install -r scripts/requirements.txt
pip install mlx-lm "transformers<5.0.0" huggingface_hub sentencepiece

# 3. 部署腳本到運行目錄
mkdir -p ~/mlx-api
cp scripts/*.py ~/mlx-api/
cp scripts/requirements.txt ~/mlx-api/

# 4. 建立 .env（chmod 600 保護）
cat > ~/mlx-api/.env << EOF
MLX_SERVER_API_KEY=<your-key>
MLX_SERVER_HOST=0.0.0.0
MLX_SERVER_PORT=5001
MLX_ALLOWED_MODELS=mlx-qwen3,mlx-gemma4,qwen3-mlx
MLX_TIMEOUT=900
MLX_MAX_CONCURRENT=3
AMPLITUDE_API_KEY=<optional>
EOF
chmod 600 ~/mlx-api/.env
```

### launchd 常駐服務（`com.mlx.apiserver`）

寫入 `~/Library/LaunchAgents/com.mlx.apiserver.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.mlx.apiserver</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/<user>/mlx-api/venv/bin/python</string>
    <string>/Users/<user>/mlx-api/server.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/<user>/mlx-api</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/Users/<user>/mlx-api/server.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/<user>/mlx-api/server-error.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
```

載入與重啟：
```bash
# 首次載入
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mlx.apiserver.plist

# 更新後重啟
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.mlx.apiserver.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mlx.apiserver.plist
```

### 自動化部署

推送到 `main` 分支（觸及 `skills/skill-mlx-api-server/scripts/**`）會自動觸發 `deploy-mlx-api.yml`，完成上述所有步驟。

## 🔒 安全模型

```
Layer 1 (Transport)   — Tailscale VPN（WireGuard 加密，僅 VPN 內可訪問）
Layer 2 (AuthN)       — X-API-Key header，hmac.compare_digest 防時序攻擊（auth.py）
Layer 3 (Input)       — prompt ≤ 16,000 chars，model allowlist 驗證（config.py + server.py）
Layer 4 (Process)     — subprocess list form（防 shell injection），非 root 執行（executor.py）
Layer 5 (Concurrency) — threading.Semaphore(3)，最多 3 個並發請求（executor.py）
```

## ⚡ Qwen3 思考鏈控制（重要）

> **已知問題已修復：** Qwen3.5 預設啟用 chain-of-thought，會使簡單請求從 ~7s 膨脹至 200s+。

**修復方式**（`executor.py` 實作，勿改動）：

```python
# 使用 Python API tokenizer.apply_chat_template(..., enable_thinking=False)
# 而非 CLI --no-thinking 旗標（CLI 版本不穩定）
script = (
    "from mlx_lm import load, generate;"
    "m,t=load(sys.argv[1]);"
    "msgs=[{'role':'user','content':sys.argv[2]}];"
    "txt=t.apply_chat_template(msgs,tokenize=False,"
    "add_generation_prompt=True,enable_thinking=False);"
    "r=generate(m,t,prompt=txt,max_tokens=int(sys.argv[3]),verbose=False);"
    "print(r)"
)
cmd = [sys.executable, "-c", script, target_model, prompt, "2048"]
```

**效果：**
| 方式 | 短財務 prompt 耗時 |
|------|-------------------|
| 預設（thinking on） | 200s+ |
| `enable_thinking=False` | **7–20s** ✅ |

## 📊 監控與統計

### 健康檢查（`health-mlx-api.yml`，每 6 小時自動執行）

```bash
# 本地
curl -sf http://127.0.0.1:5001/health
# → {"status": "ok"}

# 透過 Tailscale MagicDNS
curl -sf http://mac-mini.tail28f10.ts.net:5001/health

# 透過 Tailscale IP
curl -sf http://100.108.116.38:5001/health
```

健康檢查失敗時，Workflow 自動執行：重新部署腳本 → 重啟 launchd 服務 → 驗證恢復。

### 本地統計（`stats.jsonl`）

每次 API 呼叫自動追加至 `~/mlx-api/stats.jsonl`：
```json
{"time": "2026-08-04 23:00:00 CST", "model": "baidu/Unlimited-OCR", "prompt_preview": "OCR File: report.pdf…", "prompt_len": 20, "output_len": 4521, "elapsed_s": 95.8}
```

### Amplitude 埋點（`server.py`）

OCR 呼叫透過 `_send_amplitude_event_async()` 非同步送出 `llm_call` 事件：
- `model`: 模型名稱（如 `"baidu/Unlimited-OCR"`）
- `duration_sec`: 處理秒數
- `app_name`: 來自 `X-App-Name` request header（Caller 應設定此 header 以區分應用）

> `mlx-api-server.md` 統計表中的 `whisper-large-v3` / `whisper-transcription(-stage)` 是 `mlx-api-server-whisper/whisper_poc.py`（self-hosted runner，見上方警示）自行送出的 Amplitude 事件，與本 server 的 `/exec`、`/ocr` 呼叫無關，僅因共用同一 Amplitude project 而出現在同一份統計中。

## 🔌 API 參考

### `POST /exec` — LLM 推理

**Request：**
```json
{
  "prompt": "台積電2024Q4 EPS 多少？",
  "model": "mlx-qwen3"
}
```
`model` 為選填，預設 `mlx-qwen3`。

**Response：**
```json
{
  "output": "台積電2024Q4 EPS 為 32.3 元。\n==========\nPrompt: 21 tokens, 85.8 tokens-per-sec\nGeneration: 159 tokens, 21.3 tokens-per-sec\nPeak memory: 5.195 GB"
}
```

**錯誤碼：**
| HTTP | 原因 |
|------|------|
| `400` | prompt 超長 / model 不在 allowlist |
| `401` | API Key 錯誤或缺漏 |
| `503` | 伺服器忙碌（已達 `MAX_CONCURRENT` 上限） |
| `504` | 執行超時（超過 `MLX_TIMEOUT` 秒） |

### `POST /ocr` — 文件 OCR

**Request（multipart/form-data）：**
- `file`：PDF 或圖片（PNG/JPG）
- `dpi`（選填）：PDF 渲染解析度，預設 `200`
- 建議設定 header：`X-App-Name: <your-app-name>`（Amplitude 追蹤用）

**Response：**
```json
{
  "markdown": "# 文件標題\n\n轉錄內容..."
}
```

### `GET /health` — 健康檢查

無需認證，直接回傳：
```json
{"status": "ok"}
```

## 🛠️ 效能調參參考（`bench_params.py`）

實測結果（Qwen3.5-9B，短財務 prompt 49 chars）：

| Config | Duration | Gen tok/s | Peak mem | 結論 |
|--------|----------|-----------|----------|------|
| baseline | 14.2s | 21.022 | 5.250 GB | — |
| `--kv-bits 4` | 12.7s | 20.995 | 5.250 GB | duration -1.5s，tok/s 不變 |
| `--max-kv-size 1024` | 12.7s | 21.025 | 5.250 GB | duration -1.5s，tok/s 不變 |

**結論：短 prompt 場景下 kv-bits / max-kv-size 幾乎無效。** 執行 benchmark：
```bash
cd ~/mlx-api
source venv/bin/activate
python bench_params.py
```

## 🔄 版本管理與更新

- 唯一可信來源為 skills 登錄庫中的 `common/skill-mlx-api-server`
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json`
- 從登錄庫更新到最新版本：
  ```bash
  python self_update.py
  ```
- 修改此技能時，請先更新登錄庫版本號，再部署到 Mac-mini

## 🐛 常見問題排除

### 服務未啟動
```bash
# 查看 launchd 狀態
launchctl list | grep mlx

# 查看最近日誌
tail -50 ~/mlx-api/server.log
tail -50 ~/mlx-api/server-error.log
```

### 模型尚未下載
`executor.py` 的 `_is_model_ready()` 會在推理前檢查 HuggingFace cache，若模型未下載會回傳 `503`。手動下載：
```bash
source ~/mlx-api/venv/bin/activate
python -c "from mlx_lm import load; load('mlx-community/Qwen3.5-9B-MLX-4bit')"
```

### OOM（記憶體不足）
`mlx-community/gemma-4-31b-it-4bit`（~20 GB）在 24 GB 機器上會 OOM。
已確認可用模型：`gemma-4-e4b-it-8bit`（9.0 GB）+ `Qwen3.5-9B-MLX-4bit`（~8 GB）同時載入 ≤ 20 GB。

### `transformers` 版本衝突
```bash
# baidu/Unlimited-OCR 不支援 transformers 5.x，必須鎖定
pip install "transformers<5.0.0"
```
