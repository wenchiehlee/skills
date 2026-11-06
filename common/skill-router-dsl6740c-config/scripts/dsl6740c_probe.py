#!/usr/bin/env python3
"""
DSL-6740C Modem Probe & DMZ Target Reachability Tool
Checks DSL-6740C (192.168.1.2) Web UI and verifies reachability of DMZ target & direct devices.
"""

import socket
import sys
import time
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check_tcp_port(ip: str, port: int = 80, timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        res = s.connect_ex((ip, port))
        return res == 0
    except Exception:
        return False
    finally:
        s.close()


def probe_dsl6740c(
    modem_ip: str = "192.168.1.2",
    dmz_target: str = "192.168.1.101",
    pi_eth0: str = "192.168.1.102",
):
    print(f"=== DSL-6740C Modem Probe ({modem_ip}) ===")

    # 1. Probe Modem Web UI
    start = time.time()
    web_ok = False
    server_hdr = "-"
    try:
        req = urllib.request.Request(
            f"http://{modem_ip}", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            latency = round((time.time() - start) * 1000, 1)
            server_hdr = resp.headers.get("Server", "-")
            web_ok = resp.status == 200
    except Exception as e:
        latency = round((time.time() - start) * 1000, 1)
        server_hdr = str(e)

    web_status = (
        f"🟢 HTTP 200 ({server_hdr})" if web_ok else f"🔴 Failed ({server_hdr})"
    )
    print(f"• 數據機 Web 介面 : {web_status} ｜ 延遲: {latency}ms")

    # 2. Probe DMZ Target (MiWiFi WAN: 192.168.1.101)
    dmz_reachable = check_tcp_port(dmz_target, 80)
    dmz_status = "🟢 正常在線 (Port 80 響應)" if dmz_reachable else "🟡 無 HTTP 響應 (正常若關閉 WAN Web)"
    print(f"• DMZ 轉發目標 ({dmz_target}) : {dmz_status}")

    # 3. Probe Direct Attached Device (Raspberry Pi eth0: 192.168.1.102)
    pi_reachable = check_tcp_port(pi_eth0, 22)
    pi_status = "🟢 正常在線 (SSH:22)" if pi_reachable else "⚪ 離線/未監聽"
    print(f"• 直連設備 樹莓派 eth0 ({pi_eth0}) : {pi_status}")

    print("• 架構指引 : 確保數據機 DMZ 設定指向 192.168.1.101，以保證公網 8080/8443 封包完整流入 MiWiFi。")


if __name__ == "__main__":
    probe_dsl6740c()
