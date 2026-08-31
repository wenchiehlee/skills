---
name: skill-llm-api-server
description: 在 Synology NAS Docker 容器中運行的 LLM CLI 橋接伺服器，將 OpenAI codex-cli（ChatGPT Pro 訂閱）與 Google gemini-cli 封裝為 Flask/Waitress HTTP API，提供 /exec、/gemini/exec、/smart/exec 端點，供 llm 函式庫（skill-llm-api-client）遠端呼叫。
---

# LLM CLI API Server 技能 (skill-llm-api-server)

| 項目 | 內容 |
| :--- | :--- |
| 版本 | 1.1.1（詳見 `metadata.json`） |
| 來源 | https://github.com/ZhongZheng782/Llm-Cli-APIServer |
| 登錄庫 | https://github.com/wenchiehlee/skills （`common/skill-llm-api-server`） |
| 維護者 | wenchiehlee |
| 執行位置 | **Synology NAS**（Docker 容器 + self-hosted GitHub Actions runner） |
| 對應 Caller Skill | `common/skill-llm-api-client`（`llm` 函式庫的 `CodexProvider`） |

此技能封裝了運行於 Synology NAS Docker 容器中的 LLM CLI 橋接伺服器，將需要瀏覽器/訂閱授權登入的 CLI 工具轉為可遠端呼叫的 HTTP API：
1. **`POST /exec`** — 呼叫 `codex-cli`，使用 ChatGPT Pro 訂閱權限執行推理
2. **`POST /gemini/exec`** — 呼叫 `gemini-cli`，適用於 IP 受限或需集中管理金鑰的場景
3. **`POST /smart/exec`** — 伺服器端智慧路由（Draft & Judge），在 NAS 內部完成「自我反思」評審，避免往返延遲

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

`check_codex_cli.py` / `check_gemini_cli.py` 是**線上 smoke test**，會對已部署的 API（`CODEX_API_URL`）發出真實 HTTP 請求，用於部署後驗證。`test_codex.py` / `test_gemini.py` 是**離線 pytest 單元測試**，用 `unittest.mock` 攔截 `subprocess.run`，直接測試 `main.py` 的路由邏輯（`_check_api_key`、timeout、非 0 exit code 等），不需要網路或真實 CLI：
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
[外部機器 — llm 函式庫 (skill-llm-api-client) / GitHub Actions]
        ↓  HTTP POST /exec, /gemini/exec, /smart/exec（X-API-Key header）
[api.wenchiehlee.synology.me:8443]  ← Cloudflare / Synology reverse proxy
        ↓
[Docker container :5001]  ← Flask/Waitress main.py
        ├── /exec         → subprocess ["codex", "exec", "--skip-git-repo-check", "--yolo", prompt]
        ├── /gemini/exec  → subprocess ["gemini", "--skip-trust", "-p", prompt]
        └── /smart/exec   → Draft (draft_cli) → Judge (judge_cli) → ServerRoutingManager（晉升狀態存 routing.json）
```

**網路：**
| 項目 | 值 |
|------|----|
| 外網 HTTPS (WAN) | `https://api.wenchiehlee.synology.me:8443` |
| 內網 Tailscale | `http://newton.tail28f10.ts.net:5055` |
| 容器內部埠 | `5001`（Waitress/Flask），對外映射 `5055` |

## ⚙️ 環境變數規格

| 變數名 | 必填 | 預設值 | 說明 |
|--------|------|--------|------|
| `SSH_ROOT_PASSWORD` | ✅ | — | 容器 SSH root 密碼，`entrypoint.sh` 啟動時注入 |
| `CODEX_API_KEY` | 可選 | — | 保護 `/exec`、`/gemini/exec`、`/smart/exec` 的 `X-API-Key` header 值；留空則不驗證 |
| `CODEX_TIMEOUT` | 可選 | `120` | `codex exec` subprocess timeout（秒） |
| `GEMINI_TIMEOUT` | 可選 | `120` | `gemini` subprocess timeout（秒） |
| `ROUTING_FILE` | 可選 | `/app/data/routing.json` | Smart Routing 晉升狀態持久化路徑 |
| `UPTIMEROBOT_API_KEY` | 可選 | — | 外部監測用（非程式碼直接使用） |

`.env` 範例：
```env
SSH_ROOT_PASSWORD=your_ssh_root_password_here
CODEX_API_KEY=your_server_api_key_here
CODEX_TIMEOUT=120
GEMINI_TIMEOUT=120
UPTIMEROBOT_API_KEY=your_uptimerobot_api_key_here
```

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
  -d '{"prompt": "請幫我寫一個 Python 的 hello world 程式"}'
```
回應：`{"output": "print('Hello, World!')"}`

### `POST /gemini/exec` — Gemini 推理

```bash
curl -X POST https://api.wenchiehlee.synology.me:8443/gemini/exec \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"prompt": "...", "model": "gemini-2.5-flash", "json_mode": false}'
```

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
`fallback_reason` 分類：`timeout` / `auth_failure` / `cli_not_found` / `nonzero_exit` / `unknown_error`。

### `GET /`、`GET /codex/status`、`GET /gemini/status` — 健康檢查

`GET /` → `{"status": "ready", "service": "LLM CLI API Server"}`（無需認證）

## 📊 AI Model Usage 統計契約

所有 AI 相關 skill 應用同一組 Amplitude `llm_call` 欄位，才能在 README 與跨 repo 報表中一致回答「哪個 app 最近使用哪個模型」：

| 欄位 | 意義 | 範例 |
|------|------|------|
| `service` | 實際承載服務或 skill | `llm-api-client`, `llm-cli-api-server`, `mlx-api-server`, `mlx-api-server-whisper` |
| `stage` | 多階段 pipeline 的階段；單階段填 `generate` 或 `exec` | `generate`, `exec`, `ocr`, `transcription`, `merge`, `judge` |
| `provider` | 執行 backend 或 provider 類型 | `codex`, `gemini`, `mlx`, `baidu-ocr`, `mlx-whisper`, `faster-whisper` |
| `model` | 報表聚合用模型名稱 | `chatgpt-pro`, `gemini-2.5-flash`, `baidu/Unlimited-OCR`, `mlx-qwen3`, `whisper-large-v3` |
| `model_repo` | 精確權重/API model source；cloud provider 可留空 | `mlx-community/Qwen3.5-9B-MLX-4bit`, `mlx-community/whisper-large-v3-mlx` |
| `app_name` | 呼叫端應用名稱 | `GoogleAlertManager`, `CompanyInfo`, `whisper-merge-fix` |
| `duration_sec` | 端到端耗時秒數 | `12.34` |
| `success` | 呼叫是否成功 | `true` / `false` |
| `error_type` | 失敗分類；成功時可省略 | `timeout`, `auth_error`, `rate_limit`, `provider_error` |

統計報表至少保留三種視角：`model` total、`app_name` total、`app_name × model` last-7-days。第三種是回答 `GoogleAlertManager` 最近實際由哪個模型產生內容的必要視角。

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
