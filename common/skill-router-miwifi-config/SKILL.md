---
name: skill-router-miwifi-config
description: 小米路由器 (MiWiFi / 192.168.31.1) 網路閘道配置與維護技能。涵蓋端口轉發 (Port Forwarding: 8080/8443)、靜態 DHCP 租約綁定、Double NAT 穿透、HTTP ALG 避讓以及網關健康度探測。
---

# 小米路由器閘道配置與維護 (Router MiWiFi Config)

本技能提供家用核心網關小米路由器（MiWiFi-D01，預設 LAN: `192.168.31.1`，上層 WAN: `192.168.1.101`）的網路轉發規則、靜態 IP 分配、Double NAT 解決架構與連通性維護規範。

---

## 任務入口與工作流程

| 使用者任務 | 工作入口 | 核心動作與交付物 |
|---|---|---|
| **新增/檢查 Port Forwarding** | 連接埠轉發管理 (`scripts/miwifi_probe.py`) | 檢查與設定 TCP 8080/8443 轉發至 NAS (`192.168.31.101`)，排查轉發失效 |
| **DHCP 靜態租約管理** | 區域網路靜態 IP 綁定 | 確保 NAS、樹莓派、Mac mini 等關鍵伺服器之 MAC 綁定固定 IP |
| **避開 HTTP ALG 攔截** | 協定與安全繞過指引 | 解決 MiWiFi 對 8080 之 HTTPS 流量攔截，確保外網 HTTPS 一致走 8443 埠 |
| **閘道連通度與健康度探測** | 網關狀態診斷 (`miwifi_probe.py`) | 檢測 Web 介面 (Port 80)、上游連通度與外部公網連通狀態 |
| **無頭瀏覽器自動化配置 (CDP)** | Chromium Docker + CDP (`miwifi_cdp.py`) | 透過 NAS 上執行的 Chromium 容器 (Port 9222) 經由 CDP 遠端自動化操控路由器 Web、登入與截圖 |

---

## 核心網路架構與角色定位

在雙層 NAT 架構中，MiWiFi 擔任承上啟下的核心第二層網關：

```text
[外部網際網路 (Internet)]
       │
       ▼ (公網動態 IP，如 61.228.57.220)
[DSL-6740C 數據機 (192.168.1.2)]
       │ (DMZ 全部轉發至 192.168.1.101)
       ▼
[MiWiFi-D01 路由器 (WAN: 192.168.1.101 ｜ LAN: 192.168.31.1)]
       │
       ├─► NAS 1621+ (192.168.31.101:8443/8080) ─── Port Forwarding 目標
       ├─► Raspberry Pi 5 (192.168.31.93 wlan0)
       ├─► Mac mini (192.168.31.82)
       └─► 家用 PC / 工作站 (192.168.31.92)
```

---

## 核心配置指引

### 1. 連接埠轉發 (Port Forwarding) 規範
- **路徑**：進入後台 `http://192.168.31.1` → **高級設置** → **連接埠轉發 (Port Forwarding)**。
- **必要規則**：
  1. **TCP 8443 (HTTPS DDNS)**：
     - 名稱：`NAS-DDNS-HTTPS`
     - 協定：`TCP`
     - 外部連接埠：`8443`
     - 內部 IP：`192.168.31.101`
     - 內部連接埠：`8443`
  2. **TCP 8080 (HTTP DDNS / 備援)**：
     - 名稱：`NAS-DDNS-HTTP`
     - 協定：`TCP`
     - 外部連接埠：`8080`
     - 內部 IP：`192.168.31.101`
     - 內部連接埠：`8080`

### 2. MiWiFi HTTP ALG 攔截特性與對策
- **現象**：小米路由器內建之 Application Layer Gateway (ALG) 會對 8080 端口進行 HTTP 內容過濾。若在 8080 端口傳輸 SSL/TLS (HTTPS) 握手包，路由器可能將其攔截或丟棄。
- **標準對策**：
  - **DDNS HTTPS 存取一律使用 `8443`**（`https://*.wenchiehlee.synology.me:8443`）。
  - Port 8080 僅保留供 HTTP 純文字或舊版相容連線使用。

### 3. DHCP 靜態 IP 綁定清單
- **路徑**：`常用設置` → `區域網設置` → `DHCP 靜態 IP 分配`。
- **保留配發表**：
  - `192.168.31.101`：Synology NAS 1621+（主服務與 Docker 主機）
  - `192.168.31.93`：Raspberry Pi 5 (wlan0)
  - `192.168.31.82`：Mac mini
  - `192.168.31.92`：工作站 PC

---

## 自動化診斷與 CDP 操控工具

### 1. 輕量連通性探測工具 (`scripts/miwifi_probe.py`)
```bash
# 執行網關狀態與 NAS 轉發端口探測
python scripts/miwifi_probe.py
```

### 2. Chromium Docker + CDP 瀏覽器自動化 (`scripts/miwifi_cdp.py`)
比照 `Python-Actions.GoodInfo.Analyzer` 之純記憶體/遠端無頭瀏覽器架構，直接掛接 NAS 上運行的 `CHROMIUM` 容器 (Port 9222) 之 Chrome DevTools Protocol (CDP)：

```bash
# 檢查 MiWiFi Web 首頁狀態與當前網址
python scripts/miwifi_cdp.py inspect

# 保存 MiWiFi 當前畫面截圖
python scripts/miwifi_cdp.py screenshot --screenshot miwifi.png

# 自動化登入並檢驗連接埠轉發
python scripts/miwifi_cdp.py login --password <ROUTER_PASSWORD>
```
- **端點自動探索順序**：`$CHROMIUM_CDP_URL` → `192.168.31.101:9222` → `100.110.72.104:9222` → `127.0.0.1:9222`。
- **免本地安裝肥大瀏覽器**：完全複用 NAS 現有 `CHROMIUM` 容器資源，零硬碟額外 I/O。
