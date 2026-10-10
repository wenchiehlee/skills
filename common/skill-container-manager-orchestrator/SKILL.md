---
name: skill-container-manager-orchestrator
description: 跨平台容器管理與遠端協調技能。以 Synology NAS Container Manager 為首要核心，結合 wenchiehlee.quickconnect.to-Container.Manager 配置與 GitOps 自動化，擴展至 Mac mini、樹莓派等跨平台設備的容器遠端監控、同步、部署、網路通道協調與維護。
---

# 跨平台容器管理與遠端協調者 (Container Manager Orchestrator)

本技能提供跨多平台（首要平台為 Synology NAS Container Manager，並擴展至 Mac mini、Raspberry Pi 等設備）的容器生命週期管理、遠端協調規範、GitOps 同步機制與健康度監控。

---

## 任務入口與工作流程

| 使用者任務 | 工作入口 | 核心動作與交付物 |
|---|---|---|
| **查看容器即時狀態** | 容器狀態監控 → 節點檢查 | 讀取 `docker.csv` / `README.md` 狀態表，分析 Running/Exited 容器、記憶體負載與 Port |
| **容器配置雙向同步 (GitOps)** | 配置同步工作流 (`sync-folder.py`) | 比對 NAS 本地 `/docker/` 與 Repo 的 `compose.yaml`，提交變更並更新 badge |
| **新服務部署或滾動更新** | 部署工作流 (`deploy.yml` / Watchtower) | 建立服務目錄、編寫 `compose.yaml`、派發 Actions runner 或 P2P 直連重啟 |
| **遠端通道與網路協調** | 網路通道矩陣 → P2P / Runner 判定 | 選擇合適通道（Tailscale 網狀 P2P 或 GitHub Self-Hosted Runner）執行指令 |
| **反向代理與 Port 衝突解決** | 網路與安全埠配置規範 | 避開系統保留埠、設定 MiWiFi 雙層 NAT 轉發、維護 `http.ddns-ssl.conf` |
| **容器異常診斷與重啟** | 排錯指引與修復 SOP | 檢查容器 Log、確認 PAT Token 授權、解決 Port 佔用或記憶體超載問題 |

---

## 遠端協調與網路通道規範 (Connectivity & Network Channel Matrix)

跨平台遠端管理依賴兩大核心通道：**P2P（Tailscale Mesh VPN）** 與 **Runner（GitHub Actions Self-Hosted Runner）**。不同平台之網路環境與通道支援如下：

| 平台節點 | 角色與主要服務 | P2P 支援 (Tailscale) | Runner 支援 (GitHub Actions) | 遠端管理執行方式 |
| :--- | :--- | :---: | :---: | :--- |
| **Synology NAS 1621+**<br>*(Platform 1: 首要平台)* | Container Manager 主機<br>(Home Assistant, Chromium, Runners 等) | **✅ 支援**<br>`newton.tail28f10.ts.net`<br>(SSH / 5001 / 反代埠) | **✅ 支援**<br>運行 3 個容器化 Runners<br>(`GITHUB-RUNNER` 等) | **雙軌並行**：<br>1. 即時偵錯採 Tailscale SSH P2P 直連。<br>2. 自動化部署與同步採 GitHub Actions Runner (GitOps)，不受雙層 NAT 與防火牆限制。 |
| **Mac mini**<br>*(Platform 2: 遠端運算節點)* | 外部獨立站點，專用 AI 推論<br>(mlx-server, VNC, 終端) | **✅ 支援**<br>`mac-mini.tail28f10.ts.net`<br>(SSH:22, VNC:5900, API) | **❌ 無**<br>(目前未掛載 Runner) | **P2P 專屬直連**：<br>完全透過 Tailscale 網狀網路進行 SSH / VNC 連線或 API 呼叫，無需通過家用網路轉發。 |
| **Raspberry Pi 5 (Andy)**<br>*(Platform 3: Linux Lab)* | 家用自動化、雙網卡測試<br>(eth0: 192.168.1.102, wlan0) | **⚠️ 區域網路直連**<br>(若加入 Tailscale 則支援 P2P) | **❌ 無**<br>(目前未掛載 Runner) | **LAN P2P / 跳板直連**：<br>家用內網直接 SSH，或由 Synology NAS 作為 SSH 跳板進行管理。 |
| **llm-cli-api-server**<br>*(獨立容器節點)* | 容器內部獨立執行 `tailscaled`<br>(LLM API 端點, 直連 SSH) | **✅ 支援**<br>`llm-cli-api.tail28f10.ts.net`<br>(SSH:22, API:5001) | **透過 NAS Runner 管理** | **容器原生 P2P**：<br>容器自身即為 Tailscale 節點，SSH 與 API 直通容器內部，不佔用 NAS 主機 22 埠。 |

### 通道選擇決策準則
1. **何時使用 GitHub Runner？**
   - 跨機器的排程備份與同步任務（如每日 `sync-folder.py`）。
   - 由 Git Commit 觸發的自動部署（GitOps 流程）。
   - 位於 NAT / 防火牆深處、無法建立外網連線，但可對外訪問 GitHub 的節點。
2. **何時使用 Tailscale P2P 直連？**
   - 互動式排錯（SSH 進入容器或主機除錯）。
   - 即時串流或大流量資料（如 VNC 桌面、Immich 相簿傳輸、MLX 本地推論 API）。
   - 不適合公開暴露到公網的私有管理介面（如 DSM 5001、Home Assistant 內部端點）。

---

## 即時容器狀態監控架構 (Docker Status Monitoring)

本體系與兄弟專案 `wenchiehlee.quickconnect.to-Container.Manager` 深度聯動，形成自動化的容器狀態閉環：

```text
[NAS Runtime /docker]
       │
       ▼ (docker ps / docker stats)
  docker.csv  ───────►  UpdateReadme.py  ───────►  README.md (DOCKER_STATUS 區塊)
       │
       ▼ (CountCSVLine.py)
  *-docker.json  ───────►  Shields.io Badge (動態容器數量徽章)
```

### 1. 狀態資料讀取途徑
- **詳細清單**：參閱 `wenchiehlee.quickconnect.to-Container.Manager/docker.csv`（包含名稱、映像檔、連接埠映射、狀態時間）。
- **運算負載**：參閱 `wenchiehlee.quickconnect.to-Container.Manager/README.md` 的 `<!-- DOCKER_STATUS_START -->` 區塊（包含每個容器的即時記憶體佔用與總消耗）。
- **線上徽章**：`https://raw.githubusercontent.com/ZhongZheng782/GoPublic/refs/heads/main/wenchiehlee.quickconnect.to-Container.Manager-docker.json`。

### 2. 當前 Synology NAS 容器運行基準線 (Snapshot Baseline)
- **整體負載**：常態約 **10 個 Running** 容器，記憶體使用量約 **2.8 ~ 3.0 GiB**。
- **核心常駐服務**：
  1. `llm-cli-api-server`（約 850 MiB，LLM API + 獨立 Tailscale）
  2. `CHROMIUM`（約 680 MiB，遠端無頭/圖形瀏覽器，Port 3020/3021/9222）
  3. `homeassistant`（約 610 MiB，家庭自動化核心）
  4. `GITHUB-RUNNER` / `RUNNER1` / `RUNNER-WENCHIEHLEE-V4`（合計約 660 MiB，3 槽 CI/CD 執行節點）
  5. `travel-app`（約 45 MiB，Web 應用，Port 3333）
  6. `watchtower`（約 16 MiB，自動映像檔更新巡檢）
  7. `timetree-exporter` / `snapshot-google-tv`（各約 25~30 MiB，輔助服務）
- **按需 / 離線服務**：
  - `immich` 叢集、`influxdb`、`putty`、`guacamole`（目前為 Exited，按需啟動）。

---

## 多平台目錄與路徑規範

```text
Synology NAS:      /volume1/docker/<service>/compose.yaml  (實際掛載運行路徑)
Repo GitOps:       
  ├─ compose/<service>/compose.yaml   (【期望狀態】使用者唯一編輯與提交來源)
  └─ Running/<service>/compose.yaml   (【運行確認】部署生效後自動回寫之現況快照)
Mac mini:          ~/services/<service>/  或  ~/Library/LaunchAgents/ (launchd plist)
Raspberry Pi 5:    /home/pi/docker/<service>/compose.yaml
```

- **全面告別 NAS GUI 手動修改**：不再透過 DSM Container Manager 介面編輯，所有服務變更一律由 `compose/<service>/compose.yaml` 透過 Git Commit / Push 驅動。
- **統一使用 `compose.yaml`**：新服務優先採用 Docker Compose 規範之 `compose.yaml`，避免 legacy 之 `docker-compose.yml`。
- **自託管 Runner 隔離規範**：`github-runner*` 目錄因包含主機 Token 與本地通訊端，必須在 `sync-folder.py` 的排除清單（`--exclude`）中，切勿將機密同步回公開儲存庫。

---

## 核心操作 SOP (Operational Runbooks)

### SOP 1: GitOps 自動部署與容器重啟 (Push-to-Deploy)
**此為首要日常操作流程**：
1. **修改或新增配置**：在本地或 Git 編輯 `compose/<service>/compose.yaml`。
2. **Git Commit & Push**：推送到 `main` 分支。
3. **自動執行 (`deploy-on-change.yml`)**：
   - GitHub Actions Self-Hosted Runner 自動偵測變更的服務。
   - 自動將配置同步至 NAS `/docker/<service>/compose.yaml`。
   - 執行 `docker compose pull && docker compose up -d --remove-orphans` 重啟服務。
   - 將最新配置同步覆寫至 `Running/<service>/compose.yaml` 作為實體狀態存證。
   - 自動更新 `docker.csv`、Shields.io 徽章與 `README.md`。

### SOP 2: 手動或緊急部署 (Manual / Emergency Deploy)
1. **透過 GitHub Actions 手動派發：**
   - 前往 `wenchiehlee.quickconnect.to-Container.Manager` 的 Actions 頁面。
   - 觸發 `deploy.yml`（Workflow Dispatch），輸入 `service_name`（例如 `immich`、`chatpad`）。
   - Runner 會從 `compose/<service>/` 部署至 NAS `/docker/<service>/` 並重啟。
2. **透過 Tailscale P2P SSH 手動除錯部署：**
   ```bash
   ssh wjlee@newton.tail28f10.ts.net
   cd /volume1/docker/<service>
   sudo docker compose pull
   sudo docker compose up -d --remove-orphans
   ```

### SOP 3: 排程狀態巡檢與備份 (`actions.yml`)
- 每日凌晨 01:00 UTC 由排程自動執行：
  1. 巡檢 Watchtower 滾動更新。
  2. 執行 `sync-folder.py /docker Running` 將 NAS 實體狀態備份至 `Running/`（不覆蓋 `compose/`）。
  3. 蒐集 `docker ps` 狀態寫入 `docker.csv`。
  4. 呼叫 `UpdateReadme.py` 更新監控數據並自動 Commit。

### SOP 4: Docker 與 DDNS 映射架構與連動工作流 (Docker & DDNS Mapping)

#### 完整網路流量轉發鏈路 (End-to-End Traffic Flow)
```text
[外部使用者 / 瀏覽器]
       │
       ▼ https://<service>.wenchiehlee.synology.me:8443
[CHT 中華電信數據機 (192.168.1.2)]
       │ (DMZ 轉發至 MiWiFi WAN: 192.168.1.101)
       ▼
[小米路由器 MiWiFi-D01 (192.168.31.1)]
       │ (Port Forwarding: 8080/8443 轉發至 NAS: 192.168.31.101)
       ▼
[Synology NAS Nginx (監聽 8080 / 8443 SSL)]
       │ (讀取 /etc/nginx/conf.d/http.ddns-ssl.conf，依 Server Name 路由)
       ▼
[本機 Docker 暴露連接埠 (localhost:<Backend_Port>)]
       │ (Docker -p <Backend_Port>:<Container_Port>)
       ▼
[容器內部應用服務]
```

#### Docker 容器與 DDNS 反向代理對齊現況 (Mapping Status Matrix)
當前 DDNS 表格中共有 16 筆規則，與本機 Docker 容器運行狀態的對應關係如下：

| DDNS 服務子網域 | DDNS 外部存取網址 (:8080 / :8443) | 轉發本機埠 | 對應 Docker 容器 | 當前 Docker 狀態 | 存取預期結果 |
| :--- | :--- | :---: | :--- | :---: | :--- |
| **travel** | `travel.wenchiehlee.synology.me` | 3333 | `travel-app` | **✅ Up** | 正常存取 Web 應用 |
| **api** | `api.wenchiehlee.synology.me` | 5055 | `llm-cli-api-server` | **✅ Up** | 正常存取 LLM API |
| **vnc** | `vnc.wenchiehlee.synology.me` | 3021 | `CHROMIUM` | **✅ Up** | 正常存取 KasmVNC 瀏覽器 |
| **ha** | `ha.wenchiehlee.synology.me` | 8123 | `homeassistant` | **✅ Up** | 正常存取 Home Assistant |
| **immich** | `immich.wenchiehlee.synology.me` | 2283 | `immich_server` | ❌ Exited (5d) | **502 Bad Gateway** |
| **influxdb** | `influxdb.wenchiehlee.synology.me` | 8086 | `INFLUXDB` | ❌ Exited (5d) | **502 Bad Gateway** |
| **putty** | `putty.wenchiehlee.synology.me` | 5800 | `PUTTY` | ❌ Exited (5d) | **502 Bad Gateway** |
| **guac** | `guac.wenchiehlee.synology.me` | 8082 | `guacamole` | ❌ Exited (11d) | **502 Bad Gateway** |
| **n8n** | `n8n.wenchiehlee.synology.me` | 5678 | `N8N` | ⚠️ Created | **502 Bad Gateway** |
| **pdf** | `pdf.wenchiehlee.synology.me` | 8484 | `STIRLING-PDF` | ❌ Exited (13m) | **502 Bad Gateway** |
| **sist2** | `sist2.wenchiehlee.synology.me` | 4090 | `sist2` | ❌ Exited | **502 Bad Gateway** |
| **sist2-admin** | `sist2-admin.wenchiehlee.synology.me` | 8080 | `SIST2-ADMIN` | ❌ Exited (10m) | **埠衝突/502**（8080 被 Nginx 佔用） |
| **chatpad** | `chatpad.wenchiehlee.synology.me` | 8081 | `chatpad` | ❌ 未啟動 | **502 Bad Gateway** |
| **ollama** | `ollama.wenchiehlee.synology.me` | 8271 | `ollama` | ❌ 未啟動 | **502 Bad Gateway** |
| **linebot** | `linebot.wenchiehlee.synology.me` | 7788 | `linebot` | ❌ 未啟動 | **502 Bad Gateway** |
| **mac-mini** | `mac-mini.wenchiehlee.synology.me` | 5901 | `mac-mini` (遠端) | ⚠️ 外部節點 | **連線逾時**（已移至外部站點） |

#### 新增 Docker 容器至 DDNS 的標準閉環步驟 (4-Step Onboarding SOP)
1. **定義 Compose 宿主機連接埠**：在 `compose.yaml` 中指定本機映射埠（例如 `13021:3000`），避免使用 8080/8443 或 DSM 5000/5001。
2. **在 DSM 註冊反向代理**：在 DSM 控制台「登入入口 > 進階 > 反向代理伺服器」新增規則，將 `<service>.wenchiehlee.synology.me` 導向 `localhost:<Port>`。此動作會將設定寫入 `/usr/syno/etc/www/ReverseProxy.json`。
3. **重新生成 Nginx 設定**：觸發 `.github/workflows/sync-nginx-conf.yml`，將 `ReverseProxy.json` 轉譯為 `/etc/nginx/conf.d/http.ddns-ssl.conf` 並平滑重載 Nginx (`kill -HUP $NGINX_PID`)。
4. **同步文檔表格**：觸發 `.github/workflows/sync-ddns-table.yml`，自動更新 `README.md` 的 DDNS 表格。

#### DDNS 與 Docker 映射關鍵陷阱與規避方式
1. **8080 連接埠衝突**：
   - 由於 CHT 封鎖 80/443 入站，NAS 的自訂 Nginx 將 **8080** 作為 DDNS 的 HTTP 接收埠。
   - **禁止** 任何 Docker 容器將宿主機 Port 綁定在 `8080`（例如 `sist2-admin` 或 `watchtower` 監聽 8080 會引發 Port 衝突）。容器應映射至其他獨立埠（如 `18080`）。
2. **502 Bad Gateway 預防**：
   - DDNS 表格中的子網域若長期未運行容器，會對外曝露無效的反向代理入口。應善用 `docker.csv` 比對，將長期 Exited 的服務從 `ReverseProxy.json` 歸檔或標註。
3. **遠端節點 (Mac mini) DDNS 脫節**：
   - Mac mini 移至外部站點後，`127.0.0.1:5901` 已無實體服務。若欲保留 DDNS 存取，需將 DSM 反向代理的 Destination Host 改為 Mac mini 的 Tailscale IP（例如 `100.x.x.x:5901`），或全面改由 Tailscale 直連。


---

## 排錯指引 (Troubleshooting)

1. **GitHub Runner 啟動失敗 (404/403 Token 錯誤)**：
   - **檢查**：確認 `compose.yaml` 中的 `ORG_NAME` 是否正確（組織名稱大小寫敏感，例如 `WJLEE1020`）。
   - **權限**：GitHub 組織強制要求 Fine-grained PAT，需具備 Organization 層級之 `Self-hosted runners: Read and write` 權限。
2. **連接埠衝突 (`bind: address already in use`)**：
   - 使用 `sudo netstat -tulpn | grep <port>` 檢查佔用 PID。
   - 若為 DSM 內建服務佔用，修改 Compose 的 Host Port（例如將 `8080:80` 改為 `18080:80`），並同步更新反向代理設定。
3. **記憶體過載與 OOM 崩潰**：
   - 查閱 `docker.csv` 狀態，若狀態為 `Exited (137)` 代表容器因 Out-Of-Memory (OOM) 被系統終結。
   - 在 `compose.yaml` 中替高負載容器（如 Chromium、Elasticsearch、LLM 服務）加上資源限制：
     ```yaml
     deploy:
       resources:
         limits:
           memory: 1024M
     ```
