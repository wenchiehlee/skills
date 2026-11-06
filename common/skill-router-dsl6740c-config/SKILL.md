---
name: skill-router-dsl6740c-config
description: 中華電信 D-Link DSL-6740C 數據機/路由器 (192.168.1.2) 配置與維護技能。涵蓋 DMZ 轉發至次級路由器 (192.168.1.101)、PPPoE 公網 IP 監控、ISP 80/443 入站封鎖規避、直連設備維護 (如樹莓派 eth0) 與 Web 管理介面探測。
---

# 中華電信 DSL-6740C 數據機配置與維護 (Router DSL-6740C Config)

本技能提供中華電信 VDSL2 數據機／路由器（D-Link DSL-6740C，預設 LAN IP: `192.168.1.2`）的網路拓撲配置、DMZ 穿透、PPPoE 動態公網 IP 追蹤、ISP 住宅端連接埠限制應對與直連設備維護指引。

---

## 任務入口與工作流程

| 使用者任務 | 工作入口 | 核心動作與交付物 |
|---|---|---|
| **DMZ 主機設定與驗證** | DMZ 轉發管理 (`scripts/dsl6740c_probe.py`) | 確認將數據機 DMZ 全量指向次級路由器 MiWiFi WAN (`192.168.1.101`) |
| **公網動態 IP 追蹤** | PPPoE WAN IP 監控 | 檢測 CHT 動態 IP 漂移（如由 `61.228.35.108` 變為 `61.228.57.220`），同步 DDNS |
| **ISP 住宅連接埠限制處置** | 80/443 入站封鎖繞過 | 明確 CHT 住宅線路封鎖 80/443 之限制，指導 DDNS 走 8443 / 8080 自訂轉發 |
| **直連設備網路維護** | LAN 實體介面指引 | 維護直連數據機 LAN 埠之設備（如 Raspberry Pi 5 `eth0: 192.168.1.102`） |
| **數據機連通性探測** | Web 介面診斷 (`dsl6740c_probe.py`) | 檢測 Web 管理介面 (Port 80) 回應性與上游閘道健康度 |
| **無頭瀏覽器自動化配置 (CDP)** | Chromium Docker + CDP (`dsl6740c_cdp.py`) | 透過 NAS 上運行的 Chromium 容器 (Port 9222) 經由 CDP 遠端自動化操控數據機 Web、登入與 DMZ 設置 |

---

## 核心架構與 DMZ 轉發原則

DSL-6740C 是對外的第一層 NAT 閘道。為避免多層 NAT 導致的連接埠映射衝突，採用 **DMZ 直通** 策略：

```text
[外部網際網路 (Internet)]
       │
       ▼ (CHT 動態公網 IP，如 61.228.57.220)
[DSL-6740C 數據機 (192.168.1.2)]
       │
       ├─► [DMZ 全量轉發] ──► MiWiFi WAN (192.168.1.101) ──► NAS (192.168.31.101)
       └─► [直連 LAN 埠]  ──► Raspberry Pi 5 eth0 (192.168.1.102)
```

---

## 核心配置指引

### 1. 登入管理
- **網址**：`http://192.168.1.2`
- **預設管理者帳密規則**：
  - 帳號：`cht`
  - 密碼規則：`740C` + `MAC 地址後 4 碼`（大寫）或 `6740c` + `MAC 地址後 4 碼`（小寫）。
  - *注意：若更換過韌體或設定，以現場密碼為準。*

### 2. DMZ (Demilitarized Zone) 設置
- **功能目的**：將外部所有入站請求（除數據機自身服務外）無條件轉發至小米路由器的 WAN 介面，免去在數據機上一筆筆設定虛擬伺服器的繁瑣步驟。
- **設定參數**：
  - DMZ 狀態：`Enable`
  - DMZ Host IP Address：`192.168.1.101`（MiWiFi WAN IP）

### 3. ISP (中華電信) 住宅端限制
- **Port 80 / 443 入站封鎖**：
  - CHT 住宅光世代預設封鎖外部直接存取 TCP 80 與 TCP 443。
  - **因應方案**：對外 DDNS 統一改用 **TCP 8443 (HTTPS)** 與 **TCP 8080 (HTTP)**。

### 4. 直連設備 (Raspberry Pi 5) 雙網卡維護
- 樹莓派 `eth0` 介面直連 DSL-6740C（分配 `192.168.1.102`），用於：
  - 獨立於內網路由器進行外網線路測試。
  - 擔任區域網路跳板機。

---

## 自動化診斷與 CDP 操控工具

### 1. 輕量連通性探測工具 (`scripts/dsl6740c_probe.py`)
```bash
# 執行數據機 Web 介面探測與 DMZ 目標連通度檢測
python scripts/dsl6740c_probe.py
```

### 2. Chromium Docker + CDP 瀏覽器自動化 (`scripts/dsl6740c_cdp.py`)
比照 `Python-Actions.GoodInfo.Analyzer` 之架構，直接連線至 NAS 上運行的 `CHROMIUM` 容器 (Port 9222) 之 Chrome DevTools Protocol (CDP)：

```bash
# 檢查 DSL-6740C 首頁與登入表單狀態
python scripts/dsl6740c_cdp.py inspect

# 保存 DSL-6740C 首頁畫面截圖
python scripts/dsl6740c_cdp.py screenshot --screenshot dsl6740c.png

# 自動化登入並檢驗 DMZ 狀態
python scripts/dsl6740c_cdp.py login --username cht --password <MODEM_PASSWORD>
```

> [!IMPORTANT]
> **NAS 存取 192.168.1.2 路由必要條件**：  
> 若 NAS 上的 Docker 橋接網卡（如 `192.168.0.0/20`）遮蔽了數據機網段，請先在 NAS 執行：
> ```bash
> sudo ip route add 192.168.1.2/32 via 192.168.31.1 dev ovs_eth3
> ```
> 以確保 NAS 容器發往數據機的封包能正確轉送至 MiWiFi 網關。
