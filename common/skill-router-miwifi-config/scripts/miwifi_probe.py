#!/usr/bin/env python3
"""
MiWiFi Gateway Diagnostic & Forwarding Probe
Checks MiWiFi Gateway (192.168.31.1) Web UI and verifies target port forwarding.
"""

import socket
import ssl
import sys
import time
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check_tcp_port(ip: str, port: int, timeout: float = 1.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        res = s.connect_ex((ip, port))
        return res == 0
    except Exception:
        return False
    finally:
        s.close()


def probe_miwifi(ip: str = "192.168.31.1", nas_ip: str = "192.168.31.101"):
    print(f"=== MiWiFi Gateway Probe ({ip}) ===")
    
    # 1. Probe Web UI
    start = time.time()
    web_ok = False
    server_hdr = "-"
    try:
        req = urllib.request.Request(f"http://{ip}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            latency = round((time.time() - start) * 1000, 1)
            server_hdr = resp.headers.get("Server", "-")
            web_ok = (resp.status == 200)
    except Exception as e:
        latency = round((time.time() - start) * 1000, 1)
        server_hdr = str(e)

    web_status = f"🟢 HTTP 200 ({server_hdr})" if web_ok else f"🔴 Failed ({server_hdr})"
    print(f"• Web 管理介面 : {web_status} ｜ 延遲: {latency}ms")

    # 2. Probe NAS Target Forwarding Ports
    p8080 = check_tcp_port(nas_ip, 8080)
    p8443 = check_tcp_port(nas_ip, 8443)

    p8080_str = "🟢 OPEN" if p8080 else "🔴 CLOSED"
    p8443_str = "🟢 OPEN" if p8443 else "🔴 CLOSED"

    print(f"• NAS 內部服務監聽 ({nas_ip}) : Port 8080 ({p8080_str}) ｜ Port 8443 ({p8443_str})")
    
    if p8080 and p8443:
        print("• 結論 : NAS 內部服務就緒，若外網無法存取請至 MiWiFi 後台檢查 8080/8443 連接埠轉發規則。")
    else:
        print("• 結論 : NAS 內部端口尚未啟動，請先檢查 NAS Nginx 狀態。")


if __name__ == "__main__":
    probe_miwifi()
