---
name: skill-synology-nas-config-ssh
description: 透過 SSH 進行 Synology NAS (DSM) 系統層配置與自動化維護技能。涵蓋 Nginx 反向代理設定 (http.ddns-ssl.conf) 安全編輯、DSM 原生 WebAPI 調用 (DDNS/QuickConnect/ReverseProxy)、Docker 容器生命週期檢測與 Tailscale Funnel 背景運行維護。
---

# Synology NAS SSH 配置與維護 (Synology NAS Config via SSH)

本技能提供透過 SSH 金鑰認證（Port 22 或 Tailscale SSH）遠端登入 Synology NAS（DSM），直接對系統底層進行 Nginx 自訂反向代理維護、調用 DSM 原生 `synowebapi`、檢測 Container Manager 容器運作狀況與維護 Tailscale Funnel 背景通道的標準作業規範。

---

## 任務入口與工作流程

| 使用者任務 | 工作入口 | 核心動作與交付物 |
|---|---|---|
| **Nginx 反代安全編修** | 反代配置管理 (`syno_ssh_manager.py`) | 自動建立備份（`.bak_<timestamp>`）、修改 `http.ddns-ssl.conf`、執行 `nginx -t` 語法驗證並平滑重載 (`nginx -s reload`) |
| **查詢 DSM 原生服務狀態** | DSM WebAPI CLI 調用 | 調用 `/usr/syno/bin/synowebapi` 提取 DDNS (`SYNO.Core.DDNS.Record`)、QuickConnect 與 Reverse Proxy 原生規則清單 |
| **底層容器狀態與日誌檢驗** | Docker CLI 運作診斷 | 執行 `/usr/local/bin/docker ps -a` 檢測容器健康度、連接埠映射衝突與重啟異常服務 |
| **Tailscale Funnel 狀態同步** | Funnel 通道診斷 | 執行 `/var/packages/Tailscale/target/bin/tailscale funnel status` 驗證公網暴露端點 (80/8443) 健康度 |
| **公網動態 IP 漂移比對** | DDNS 外部 IP 校驗 | 由 NAS 主動向外查詢公網 IP (`checkip.synology.com`)，對比 DDNS 紀錄與外部連接埠連通性 |

---

## 遠端連線與安全規範

### 1. 通道與認證優先級
1. **區域網路直接 SSH (LAN Direct)**：
   - 目標主機：`192.168.31.101`（Port 22）
   - 使用者：`wjlee`
   - 金鑰位置：`~/.ssh/id_ed25519_wenchiehlee`
2. **Tailscale 網狀 P2P 直連 (Tailscale Mesh)**：
   - 目標主機：`newton.tail28f10.ts.net` 或 `100.110.72.104`（Port 22）
   - 適合外部遠端環境或跳板作業。

### 2. Nginx 反代配置防護規範 (Atomic & Safe Editing)
所有對 `/etc/nginx/conf.d/http.ddns-ssl.conf` 的變更，**必須強制遵循以下防護 SOP**：
1. **變更前強制備份**：
   ```bash
   sudo cp /etc/nginx/conf.d/http.ddns-ssl.conf /etc/nginx/conf.d/http.ddns-ssl.conf.bak_$(date +%Y%m%d%H%M%S)
   ```
2. **語法校驗 (Syntax Check)**：
   ```bash
   sudo nginx -t
   ```
   *注意：若回傳非 0 或 Syntax Error，嚴禁執行 reload，必須立即還原備份。*
3. **平滑重載 (Graceful Reload)**：
   ```bash
   sudo nginx -s reload
   ```

---

## 核心系統命令速查手冊

### 1. DSM 原生 WebAPI (`/usr/syno/bin/synowebapi`)
```bash
# 取得 DDNS 紀錄與當前公網 IP
sudo /usr/syno/bin/synowebapi --exec api=SYNO.Core.DDNS.Record method=list version=1

# 取得 QuickConnect 狀態與網址
sudo /usr/syno/bin/synowebapi --exec api=SYNO.Core.QuickConnect method=get version=1

# 取得 DSM 控制台反向代理規則清單
sudo /usr/syno/bin/synowebapi --exec api=SYNO.Core.AppPortal.ReverseProxy method=list version=1
```

### 2. Docker 原生管理 (`/usr/local/bin/docker`)
```bash
# 列出所有容器運行狀況與連接埠
sudo /usr/local/bin/docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

# 查看特定容器最新 50 行日誌
sudo /usr/local/bin/docker logs --tail 50 <CONTAINER_NAME>
```

### 3. Tailscale Funnel 維護
```bash
# 檢查 Funnel 啟用狀態與轉發規則
sudo /var/packages/Tailscale/target/bin/tailscale funnel status
```

---

## 自動化管理工具 (`scripts/syno_ssh_manager.py`)

本技能提供全自動化 CLI 工具 `scripts/syno_ssh_manager.py`，支援遠端診斷與自動化操作：

```bash
# 1. 檢測 NAS 連線與底層系統概況
python scripts/syno_ssh_manager.py status

# 2. 列出當前所有反代規則與對應容器
python scripts/syno_ssh_manager.py list-proxies

# 3. 測試 Nginx 配置語法並平滑重載
python scripts/syno_ssh_manager.py reload-nginx
```
