---
name: skill-llm-api-server
description: 在 Synology NAS Docker 容器中運行的 LLM CLI 與 MCP 橋接伺服器，將 OpenAI codex-cli（ChatGPT Pro）、Google Antigravity CLI（agy）與 OpenAI Secure MCP Tunnel 封裝為 HTTP API 與安全通道，提供 /exec、/gemini/exec、/gemini/models、/tunnel/status 端點，供 llm 客戶端與 ChatGPT 遠端呼叫。
---

# LLM CLI API Server 技能 (skill-llm-api-server)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.3.0（詳見 `metadata.json`） |
| 來源 | https://github.com/ZhongZheng782/Llm-Cli-APIServer |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-llm-api-server`） |
| 維護者 | wenchiehlee |
| 執行位置 | **Synology NAS**（Docker 容器 + self-hosted GitHub Actions runner） |
| 對應 Caller Skill | `common/skill-llm-api-client`（`llm` 函式庫的 `CodexProvider`）與 ChatGPT MCP Connectors |

此技能封裝了運行於 Synology NAS Docker 容器中的 LLM CLI 橋接伺服器，將需要瀏覽器/訂閱授權登入的 CLI 工具與 MCP 服務轉為可遠端呼叫的 HTTP API 與主動出站通道：
1. **`POST /exec`** — 呼叫 `codex-cli`，使用 ChatGPT Pro 訂閱權限執行推理
2. **`POST /gemini/exec`** — 呼叫 `agy`（Google Antigravity CLI，取代舊 gemini-cli），支援多模型與 `effort` 思考層級
3. **`GET /gemini/models`** — 查詢 `agy` 目前支援的模型列表（Gemini 3.8 Flash、Claude、GPT-OSS）與思考等級
4. **`POST /smart/exec`** — 伺服器端智慧路由（Draft & Judge），在 NAS 內部完成「自我反思」評審，避免往返延遲
5. **OpenAI Secure MCP Tunnel (`tunnel-client`)** — 主動向 OpenAI Control Plane 建立出站連線，讓 ChatGPT 網頁版/App 直接免開 Port/IP 存取 NAS 工作區 tools

## 📦 技能結構說明

```text
skill-llm-api-server/
├── SKILL.md               # 技能描述與操作指引（本檔案）
├── metadata.json          # 機器可讀 metadata（名稱、版本、來源），供版本檢查使用
├── self_update.py         # 從 skills 登錄庫檢查並更新此技能的工具
└── scripts/
    ├── main.py             # Flask/Waitress API 伺服器主程式（/exec /gemini/exec /smart/exec /codex/status /gemini/status）
    ├── check_codex_cli.py  # Codex 路徑 smoke test（打真實已部署的 API，需網路）
    ├── check_gemini_cli.py # Gemini 路徑 smoke test（打真實已部署的 API，需網路）
    ├── test_codex.py       # pytest：以 Flask test client + mock subprocess 測試 main.py 的 Codex 端點
    ├── test_gemini.py      # pytest：以 Flask test client + mock subprocess 測試 main.py 的 Gemini 端點
    ├── Renew-GeminiAuth.ps1 # Windows：重新產生 Gemini OAuth 認證並上傳
    └── renew-gemini-auth.sh # macOS/Linux：同上
```

### `check_*.py` 與 `test_*.py` 的差異

`check_codex_cli.py` / `check_gemini_cli.py` 是**線上 smoke test**，會對已部署的 API（內建 Codex server endpoints）發出真實 HTTP 請求，用於部署後驗證。`test_codex.py` / `test_gemini.py` 是**離線 pytest 單元測試**，用 `unittest.mock` 攔截 `subprocess.run`，直接測試 `main.py` 的路由邏輯（`_check_api_key`、timeout、非 0 exit code 等），不需要網路或真實 CLI：
```bash
cd scripts
pip install pytest
pytest test_codex.py test_gemini.py -v
```

### 此技能「擁有」什麼，「不擁有」什麼

`scripts/*` 是應用程式碼的**唯一版本**（`main.py` 及其直接測試/工具）——不再有 `Llm-Cli-APIServer` 根目錄下的舊路徑副本。

Docker/部署相關檔案（`Dockerfile`、`docker-compose.yml`、`entrypoint.sh`、`.env.example`、`.github/workflows/deploy-synology-nas.yml`）**刻意不納入此技能**，仍留在消費端 repo（`Llm-Cli-APIServer`）的根目錄——這些檔案定義的是「Docker 建置環境已就緒」這個前提假設本身（`docker compose build` 的 build context 就是 repo root），此技能只負責在這個前提之上跑起來的應用程式碼。兩者的耦合點只有一行：`entrypoint.sh` 用相對路徑 `skills/skill-llm-api-server/scripts/main.py` 啟動本技能的 `main.py`（因為 `Dockerfile` 的 `COPY . .` 已經把整個 repo，包含 `skills/`，複製進 image）。

若要新增其他消費端 repo，前提是該 repo 也已具備等價的 Docker/entrypoint 骨架，並手動加上這一行路徑指向。

## 🏗️ 架構概覽

```
[外部呼叫端 — llm 函式庫 (skill-llm-api-client) / GitHub Actions / 本機 CLI]
        ↓  HTTP POST /exec, /gemini/exec, /smart/exec（X-API-Key header）
[api.wenchiehlee.synology.me:8443]  ← Cloudflare / Synology reverse proxy
        ↓
[Docker container :5001]  ← Flask/Waitress main.py
        ├── /exec           → subprocess ["codex", "exec", "--skip-git-repo-check", "--yolo", (--model <model>,) prompt]
        ├── /gemini/exec    → subprocess ["agy", "-p", prompt, (--model <model>,)] (OAuth, 支援 effort)
        ├── /gemini/models  → 回傳 agy 目前支援之可用模型清單與思考層級 (low, medium, high)
        ├── /smart/exec     → Draft (draft_cli) → Judge (judge_cli) → ServerRoutingManager（晉升狀態存 routing.json）
        └── /tunnel/status  → 監控 OpenAI Secure Tunnel 背景程序與健康狀態

[ChatGPT 網頁版 / ChatGPT App / OpenAI Responses API]
        ↓ (透過 OpenAI Control Plane 安全通道，無需外網 IP、無需 Port Forwarding)
[tunnel-client : outbound WebSocket]  ← OpenAI 官方通道客戶端（start-openai-tunnel.sh 背景守護）
        ↓ stdio
[local_workspace_mcp]  ← 本地 MCP 伺服器（掛載 /app 工作區，提供 ChatGPT 檔案與終端機工具）
```

**網路：**
| 項目 | 值 | 說明 |
|------|----|------|
| 外網 HTTPS (WAN) | `https://api.wenchiehlee.synology.me:8443` | 供外部 client/GitHub Actions 呼叫 |
| 內網 Tailscale（容器直連，推薦） | `http://llm-cli-api.tail28f10.ts.net:5001` | 私網端對端加密直連 |
| 內網 Tailscale（NAS 轉發） | `http://newton.tail28f10.ts.net:5055` | 經 NAS host port 轉發 |
| 容器內部埠 | `5001`（Waitress/Flask），對外映射 `5055` | API 伺服器監聽埠 |
| OpenAI Secure MCP Tunnel | `tunnel_6ac1b9e0779c819190ebb87b8e1570e6` | ChatGPT 專用主動出站通道（免開 Port） |

## ⚙️ 環境變數規格

| 變數名 | 必填 | 預設值 | 說明 |
|--------|------|--------|------|
| `SSH_ROOT_PASSWORD` | ✅ | — | 容器 SSH root 密碼，`entrypoint.sh` 啟動時注入 |
| `CODEX_API_KEY` | 可選 | — | 保護 `/exec`、`/gemini/exec`、`/smart/exec` 的 `X-API-Key` header 值；留空則不驗證 |
| `CODEX_TIMEOUT` | 可選 | `120` | `codex exec` subprocess timeout（秒） |
| `GEMINI_TIMEOUT` | 可選 | `120` | `agy` subprocess timeout（秒） |
| `ROUTING_FILE` | 可選 | `/app/data/routing.json` | Smart Routing 晉升狀態持久化路徑 |
| `OPENAI_TUNNEL_ID` | 可選 | — | OpenAI Secure Tunnel ID（格式如 `tunnel_...`），供 ChatGPT 辨識通道 |
| `OPENAI_TUNNEL_RUNTIME_KEY` | 可選 | — | OpenAI Platform 建立之 Runtime API Key，供 `tunnel-client` 登入 Control Plane |
| `UPTIMEROBOT_API_KEY` | 可選 | — | 外部監測用（非程式碼直接使用） |

`.env` 範例：
```env
SSH_ROOT_PASSWORD=your_ssh_root_password_here
CODEX_API_KEY=your_server_api_key_here
CODEX_TIMEOUT=120
GEMINI_TIMEOUT=120
OPENAI_TUNNEL_ID=tunnel_6ac1b9e0779c819190ebb87b8e1570e6
OPENAI_TUNNEL_RUNTIME_KEY=sk-tunnel-rt-xxxxxx
UPTIMEROBOT_API_KEY=your_uptimerobot_api_key_here
```

## 📏 Prompt 長度設定

`/exec`、`/gemini/exec` 與 `/smart/exec` 支援可配置的 server-side prompt 字元 guard：

| 變數 | 預設 | 說明 |
|------|------|------|
| `CODEX_MAX_PROMPT_LENGTH` | `60000` | Codex prompt 上限；部署 workflow 固定傳入 60000 |
| `GEMINI_MAX_PROMPT_LENGTH` | `60000` | Gemini prompt 上限；部署 workflow 固定傳入 60000 |

超過 60000 字元時，請求會回傳 HTTP `413`，不會啟動 CLI；Codex CLI、gateway 或模型本身仍可能有更小的 context window 限制。

## 🚀 部署流程

推送到 `main` 分支會自動觸發 `.github/workflows/deploy-synology-nas.yml`，在 self-hosted runner 上建置並啟動容器（Docker 混合環境：Python 3.11-slim + Node.js 20 + `@openai/codex` + `@google/gemini-cli` + `bubblewrap`）。

### 首次授權（一次性）

1. 開啟 GitHub Repository 的 **Actions** 分頁，查看部署任務日誌
2. 日誌中會出現 `https://auth.openai.com/activate` 連結與 8 位元代碼
3. 在瀏覽器開啟該連結並輸入代碼完成授權
4. 授權成功後，認證資訊自動存放於 NAS `/volume1/docker/llm-cli-api-server/config`
5. 此後所有自動部署皆維持登入狀態，無需再次授權

### Gemini OAuth 重新授權

Gemini CLI 的 OAuth token 需要瀏覽器互動登入，無法在無頭 CI 環境完成，需在有瀏覽器的機器上執行 `scripts/renew-gemini-auth.sh`（macOS/Linux）或 `scripts/Renew-GeminiAuth.ps1`（Windows），登入後上傳 `~/.gemini/` 到容器的 `gemini-auth` volume。

## 🔒 安全模型

```
Layer 1 (Transport)   — HTTPS (Cloudflare/Synology reverse proxy)，內網可走 Tailscale VPN
Layer 2 (AuthN)       — X-API-Key header 驗證（_check_api_key，未設定 CODEX_API_KEY 則不驗證）
Layer 3 (Env 隔離)    — subprocess 執行時剔除 CODEX_API_KEY，避免污染 codex-cli 的 OAuth 憑證
Layer 4 (Sandbox)     — bubblewrap（chmod u+s /usr/bin/bwrap），容器啟動時自動 smoke test
Layer 5 (Timeout)     — CODEX_TIMEOUT / GEMINI_TIMEOUT 限制 subprocess 最長執行時間，逾時回傳 504
```

## 🔌 API 參考

### `POST /exec` — Codex（ChatGPT Pro）推理

需 Header `X-API-Key`（若未設定 `CODEX_API_KEY` 則不需要）。與 `llm` 函式庫的 `CodexProvider` 相容。

```bash
curl -X POST https://api.wenchiehlee.synology.me:8443/exec \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"prompt": "請幫我寫一個 Python 的 hello world 程式", "model": "gpt-5-codex"}'
```
`model` 選填；省略時沿用 `codex` CLI 自身預設值，帶了才會在指令加上 `--model <model>`。
回應：`{"output": "print('Hello, World!')"}`

### `POST /gemini/exec` — Gemini (AGY CLI) 推理

呼叫 NAS 容器內的 `agy`（Google Antigravity CLI），支援最新多模型選擇與 `effort` 思考層級調節：

```bash
curl -X POST https://api.wenchiehlee.synology.me:8443/gemini/exec \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"prompt": "分析這份財報重點", "model": "Gemini 3.8 Flash (High)", "effort": "high", "json_mode": false}'
```

- `model`：支援官方顯示名稱或別名（如 `gemini-3.8-flash`、`Gemini 3.8 Flash (Medium)`、`Claude Sonnet 4.6 (Thinking)`、`GPT-OSS 120B (Medium)`）。
- `effort`：可選 `low` / `medium` / `high`，伺服器會自動融合至模型選擇。
- 錯誤分類：若額度耗盡回傳 HTTP `429` 且 `error_type: "quota_exceeded"`。

### `GET /gemini/models` — 查詢 AGY 可用模型清單

回傳目前容器內 `agy` CLI 支援的模型名稱與思考層級：

```bash
curl https://api.wenchiehlee.synology.me:8443/gemini/models
```

回應範例：
```json
{
  "available_efforts": ["low", "medium", "high"],
  "available_models": [
    "Gemini 3.8 Flash (High)", "Gemini 3.8 Flash (Medium)", "Gemini 3.8 Flash (Low)",
    "Gemini 3.7 Flash (High)", "Gemini 3.7 Flash (Medium)", "Gemini 3.7 Flash (Low)",
    "Gemini 3.6 Flash (High)", "Gemini 3.6 Flash (Medium)", "Gemini 3.6 Flash (Low)",
    "Gemini 3.1 Pro (High)", "Gemini 3.1 Pro (Low)",
    "Claude Sonnet 4.6 (Thinking)", "Claude Opus 4.6 (Thinking)",
    "GPT-OSS 120B (Medium)"
  ],
  "current_default": "Gemini 3.8 Flash (Medium)"
}
```

### `GET /tunnel/status`、`GET /tunnel/doctor`、`POST /tunnel/restart` — OpenAI Secure Tunnel

OpenAI 官方通道客戶端（`tunnel-client`）在 NAS 背景運行，為 ChatGPT 提供安全連線：

1. **`GET /tunnel/status`** — 檢查通道狀態：
   ```json
   {
     "configured": true,
     "running": true,
     "supervisor_running": true,
     "tunnel_id": "tunnel_6ac1b9e0779c819190ebb87b8e1570e6",
     "health_url": "http://127.0.0.1:42906",
     "health_status": "ok"
   }
   ```
2. **`GET /tunnel/doctor`** — 執行通道健康檢查診斷（`tunnel-client doctor`）。
3. **`POST /tunnel/restart`** — 重新啟動通道背景守護行程（需 `X-API-Key`）。

#### 💡 ChatGPT Connector 設定須知
- **不需要填寫任何 IP 或 Port**：ChatGPT 透過 OpenAI 雲端 Control Plane 轉發，無需開放防火牆或對外 Port。
- 於 [ChatGPT 設定 -> Connectors](https://chatgpt.com/#settings/Connectors) 中選擇 **Secure MCP Tunnel** 並填入您的 Tunnel ID：
  `tunnel_6ac1b9e0779c819190ebb87b8e1570e6`。
- 只要 `/tunnel/status` 顯示 `running: true` 且 `health_status: "ok"`，ChatGPT 即可隨時使用 NAS 容器工作區的檔案管理與指令執行工具。

### `POST /smart/exec` — 伺服器端智慧路由

Request：`{"task_name": "...", "prompt": "...", "draft_cli": "gemini", "judge_cli": "gemini", "model": "", "json_mode": false}`

回應（成功晉升）：`{"output": "...", "smart_status": "promoted", "provider": "gemini"}`
回應（評審失敗）：`{"output": "...", "smart_status": "judging_fail", "provider": "gemini"}`
回應（錯誤，結構化診斷）：
```json
{
  "smart_status": "error",
  "fallback_reason": "auth_failure",
  "failed_stage": "draft",
  "provider": "gemini",
  "error": "gemini exited 1: 401 Unauthorized"
}
```
`fallback_reason` 分類：`timeout` / `auth_failure` / `quota_exceeded` / `cli_not_found` / `nonzero_exit` / `unknown_error`。

### `GET /`、`GET /codex/status`、`GET /gemini/status` — 健康檢查

- `GET /` → `{"status": "ready", "service": "LLM CLI API Server"}`（無需認證）
- `GET /codex/status` → `{"codex_cli": "installed", "version": "codex-cli 0.160.0"}`
- `GET /gemini/status` → `{"auth_mode": "oauth", "gemini_cli": "installed", "tool": "agy", "version": "1.2.16"}`

## 📊 AI Model Usage 統計契約

所有 AI 相關 skill 應用同一組 Amplitude `llm_call` 欄位，才能在 README 與跨 repo 報表中一致回答「哪個 app 最近使用哪個模型」：

| 欄位 | 意義 | 範例 |
|------|------|------|
| `service` | 實際承載服務或 skill | `llm-cli-api-server`, `mlx-api-server`, `mlx-api-server-whisper` |
| `stage` | 多階段 pipeline 的階段；單階段可省略或填 `exec` | `exec`, `ocr`, `transcription`, `merge`, `judge` |
| `provider` | 執行 backend 或 provider 類型 | `codex`, `gemini`, `mlx`, `mlx-whisper`, `faster-whisper` |
| `model` | 報表聚合用模型名稱 | `chatgpt-pro`, `gemini-2.5-flash`, `baidu/Unlimited-OCR`, `mlx-qwen3`, `whisper-large-v3` |
| `model_repo` | 精確權重/API model source；cloud provider 可留空 | `mlx-community/Qwen3.5-9B-MLX-4bit`, `mlx-community/whisper-large-v3-mlx` |
| `app_name` | 呼叫端應用名稱 | `GoogleAlertManager`, `CompanyInfo`, `whisper-merge-fix` |
| `duration_sec` | 端到端耗時秒數 | `12.34` |
| `success` | 呼叫是否成功 | `true` / `false` |
| `error_type` | 失敗分類；成功時可省略 | `timeout`, `auth_error`, `rate_limit`, `provider_error` |

統計報表至少要保留三種視角：

1. `model` total：回答整體模型使用量。
2. `app_name` total：回答哪些應用在使用服務。
3. `app_name × model` last-7-days：回答特定應用最近實際用哪個模型，例如 `GoogleAlertManager` 最近 7 天由 `chatgpt-pro` 或 `gemini-2.5-flash` 產生。

`skill-llm-api-client` 是一般 LLM 呼叫的主要埋點位置，應以 `LLMClient(app_name=...)` 設定 `app_name`，並由 provider 回填 `provider`、`model`、`model_repo`。伺服器端 skill 若自行產生 AI 結果（例如 MLX `/exec`、OCR、Whisper pipeline），也必須直接送出相同 schema 的 `llm_call`，避免只留下 local stats 而無法進入全域 AI model usage 統計。

## 🐛 常見問題排除

### 504 Gateway Timeout
`/exec` 以 `CODEX_TIMEOUT` 限制 `codex exec` 最長執行時間（預設 120 秒）。逾時時 response body 含 `{"error": "codex timed out after 120s"}`。優先檢查 container log 是否有 `CLI timeout` 字樣，以判斷 timeout 是發生在 API server 內還是外層 gateway（Synology reverse proxy / nginx / Cloudflare）：
```bash
docker logs llm-cli-api-server --since "2026-05-12T11:43:00Z"
```

### Codex apply_patch / bubblewrap 失敗
```text
bwrap: Creating new namespace failed, likely because the kernel does not support user namespaces.
```
檢查：
```bash
bwrap --version
sysctl kernel.unprivileged_userns_clone
sysctl user.max_user_namespaces
```
修法：
```bash
sudo sysctl -w kernel.unprivileged_userns_clone=1
sudo sysctl -w user.max_user_namespaces=15000
sudo chmod u+s "$(command -v bwrap)"
```

## 🔄 版本管理與更新

- 唯一可信來源為 skills 登錄庫中的 `common/skill-llm-api-server`
- 版本採語意化版本（`MAJOR.MINOR.PATCH`），記錄於 `metadata.json`
- 從登錄庫更新到最新版本：
  ```bash
  python self_update.py
  ```
- 修改此技能時，請先更新登錄庫版本號，再部署到 Llm-Cli-APIServer repo
