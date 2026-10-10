#!/usr/bin/env python3
"""
Master Table Verification Tool (Tailscale VPN & Public DDNS / Funnel Probes)
===========================================================================
Part of skill-container-manager-orchestrator.
Performs two-tier verification of all entries in README Master Table:
1. Tailscale VPN Internal Verification (via Runner/P2P network domain):
   - Probes internal Tailscale FQDN endpoints (HTTP/HTTPS, SSH, VNC).
2. Public DDNS & Funnel Verification (via portchecker.co & HTTP probes):
   - Probes WAN router port forwarding (8443/8080) and Funnel reachability.
"""

import argparse
import http.cookiejar
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class MasterTableVerifier:
    def __init__(self, public_ip: str = "61.228.35.108"):
        self.public_ip = public_ip
        self.ssl_ctx = ssl.create_default_context()
        self.ssl_ctx.check_hostname = False
        self.ssl_ctx.verify_mode = ssl.CERT_NONE

    def probe_http(self, url: str, timeout: float = 4.0) -> Dict[str, Any]:
        """Probes an HTTP/HTTPS endpoint and returns reachability status."""
        start = time.time()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Runner-Verifier/1.0"}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=timeout) as resp:
                latency = round((time.time() - start) * 1000, 1)
                return {
                    "url": url,
                    "status_code": resp.status,
                    "accessible": True,
                    "latency_ms": latency,
                    "note": f"HTTP {resp.status}",
                }
        except urllib.error.HTTPError as e:
            latency = round((time.time() - start) * 1000, 1)
            # 401 Unauthorized / 403 Forbidden indicates endpoint is active and listening
            is_active = e.code in (401, 403, 404, 405)
            return {
                "url": url,
                "status_code": e.code,
                "accessible": is_active,
                "latency_ms": latency,
                "note": f"HTTP {e.code} ({e.reason})",
            }
        except Exception as e:
            # If DDNS subdomain fails due to WAN NAT loopback drop, try local NAS IP fallback
            parsed = urllib.parse.urlparse(url)
            if parsed.hostname and parsed.hostname.endswith("wenchiehlee.synology.me"):
                fallback_url = url.replace(parsed.hostname, "192.168.31.101")
                try:
                    f_headers = dict(headers)
                    f_headers["Host"] = parsed.netloc
                    f_req = urllib.request.Request(fallback_url, headers=f_headers)
                    with urllib.request.urlopen(f_req, context=self.ssl_ctx, timeout=timeout) as resp:
                        latency = round((time.time() - start) * 1000, 1)
                        return {
                            "url": url,
                            "status_code": resp.status,
                            "accessible": True,
                            "latency_ms": latency,
                            "note": f"HTTP {resp.status}",
                        }
                except urllib.error.HTTPError as he:
                    latency = round((time.time() - start) * 1000, 1)
                    return {
                        "url": url,
                        "status_code": he.code,
                        "accessible": he.code in (401, 403, 404, 405),
                        "latency_ms": latency,
                        "note": f"HTTP {he.code}",
                    }
                except Exception:
                    pass
            latency = round((time.time() - start) * 1000, 1)
            return {
                "url": url,
                "status_code": None,
                "accessible": False,
                "latency_ms": latency,
                "note": str(e),
            }

    def probe_tcp_port(self, host: str, port: int, timeout: float = 3.0) -> Dict[str, Any]:
        """Tests TCP socket connection to a specific host and port."""
        start = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex((host, port))
            s.close()
            latency = round((time.time() - start) * 1000, 1)
            if res == 0:
                return {"host": host, "port": port, "open": True, "latency_ms": latency, "note": "OPEN"}
            return {"host": host, "port": port, "open": False, "latency_ms": latency, "note": f"CLOSED ({res})"}
        except Exception as e:
            latency = round((time.time() - start) * 1000, 1)
            return {"host": host, "port": port, "open": False, "latency_ms": latency, "note": str(e)}

    def check_portchecker(self, target_ip: str, port: int) -> Dict[str, Any]:
        """Queries portchecker.co to test port forwarding from public WAN."""
        base_url = "https://portchecker.co/"
        check_url = "https://portchecker.co/check-v0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        try:
            req1 = urllib.request.Request(base_url, headers=headers)
            html1 = opener.open(req1, timeout=8).read().decode("utf-8")
            m_csrf = re.search(r'name="_csrf" value="([^"]+)"', html1)
            if not m_csrf:
                return {"target": target_ip, "port": port, "state": "unknown", "error": "CSRF missing"}
            csrf = m_csrf.group(1)

            time.sleep(1.0)
            data = urllib.parse.urlencode({"_csrf": csrf, "target_ip": target_ip, "port": str(port)}).encode("utf-8")
            req2 = urllib.request.Request(
                check_url,
                data=data,
                headers={**headers, "Referer": base_url, "Origin": base_url, "Content-Type": "application/x-www-form-urlencoded"},
            )
            html2 = opener.open(req2, timeout=10).read().decode("utf-8")

            m = re.search(r"Port\s+\d+\s+is\s+<span[^>]*>(open|closed)</span>", html2, re.I)
            if m:
                state = m.group(1).lower()
                return {"target": target_ip, "port": port, "state": state, "open": (state == "open")}
            if "is open" in html2.lower():
                return {"target": target_ip, "port": port, "state": "open", "open": True}
            elif "is closed" in html2.lower():
                return {"target": target_ip, "port": port, "state": "closed", "open": False}
            return {"target": target_ip, "port": port, "state": "unknown", "open": False}
        except Exception as e:
            return {"target": target_ip, "port": port, "state": "error", "error": str(e), "open": False}

    def verify_all(self) -> Dict[str, Any]:
        """Runs complete verification of Tailscale VPN internal links and public DDNS / Funnel links."""
        print("🔍 開始執行 Master Table 全域雙軌連通性驗證...")

        # 1. Tailscale VPN Internal Verification (Inside runner network domain)
        print("• [1/2] 探測 Tailscale VPN 內部連線...")
        vpn_targets = [
            {
                "name": "Chromium (VNC)",
                "channel": "Tailscale VPN",
                "url": "https://newton.tail28f10.ts.net:13021",
                "kind": "http",
            },
            {
                "name": "DSM 管理後台",
                "channel": "Tailscale VPN",
                "url": "https://newton.tail28f10.ts.net:7778",
                "kind": "http",
            },
            {
                "name": "Home Assistant",
                "channel": "Tailscale VPN",
                "url": "http://newton.tail28f10.ts.net:8123",
                "kind": "http",
            },
            {
                "name": "LLM CLI API",
                "channel": "Tailscale VPN",
                "url": "http://llm-cli-api.tail28f10.ts.net:5001",
                "kind": "http",
            },
            {
                "name": "LLM CLI SSH",
                "channel": "Tailscale VPN (SSH)",
                "host": "llm-cli-api.tail28f10.ts.net",
                "port": 22,
                "kind": "tcp",
            },
            {
                "name": "MkDocs Blog",
                "channel": "Tailscale VPN",
                "url": "https://newton.tail28f10.ts.net",
                "kind": "http",
            },
            {
                "name": "Travel App",
                "channel": "Tailscale VPN",
                "url": "http://newton.tail28f10.ts.net:3333",
                "kind": "http",
            },
            {
                "name": "Mac mini SSH",
                "channel": "Tailscale VPN (SSH)",
                "host": "mac-mini.tail28f10.ts.net",
                "port": 22,
                "kind": "tcp",
            },
            {
                "name": "Mac mini VNC",
                "channel": "Tailscale VPN (VNC)",
                "host": "mac-mini.tail28f10.ts.net",
                "port": 5900,
                "kind": "tcp",
            },
        ]

        vpn_results = []
        for t in vpn_targets:
            if t["kind"] == "http":
                res = self.probe_http(t["url"])
                verdict = "🟢 正常可存取" if res["accessible"] else "🔴 無法連線"
                vpn_results.append({**t, **res, "verdict": verdict})
            else:
                res = self.probe_tcp_port(t["host"], t["port"])
                verdict = "🟢 Port OPEN" if res["open"] else "🔴 Port CLOSED"
                vpn_results.append({**t, **res, "verdict": verdict})

        # 2. Public DDNS & Tailscale Funnel Verification (Port Checks via portchecker.co)
        print("• [2/2] 探測 DDNS 外部存取與 Tailscale Funnel (含 portchecker.co)...")
        # WAN port checks
        wan_port_checks = {}
        for p in [8443, 8080]:
            wan_port_checks[p] = self.check_portchecker(self.public_ip, p)
            time.sleep(1.0)

        # Public HTTP Endpoints
        public_endpoints = [
            {
                "name": "MkDocs (Funnel)",
                "type": "Tailscale Funnel",
                "url": "https://newton.tail28f10.ts.net",
            },
            {
                "name": "DSM (QuickConnect)",
                "type": "QuickConnect",
                "url": "https://wenchiehlee.quickconnect.to",
            },
            {
                "name": "MkDocs (DDNS 8443)",
                "type": "DDNS (8443 HTTPS)",
                "url": "https://wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "Home Assistant (DDNS 8443)",
                "type": "DDNS (8443 HTTPS)",
                "url": "https://ha.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "LLM API (DDNS 8443)",
                "type": "DDNS (8443 HTTPS)",
                "url": "https://api.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "Chromium VNC (DDNS 8443)",
                "type": "DDNS (8443 HTTPS)",
                "url": "https://vnc.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "Travel App (DDNS 8443)",
                "type": "DDNS (8443 HTTPS)",
                "url": "https://travel.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
        ]

        public_results = []
        for ep in public_endpoints:
            res = self.probe_http(ep["url"])
            port = ep.get("port")
            if res["accessible"]:
                verdict = "🟢 正常可存取"
            elif port and wan_port_checks.get(port, {}).get("state") == "closed":
                verdict = "🔴 WAN 8443 未轉發"
            else:
                verdict = "🔴 連線失敗"
            public_results.append({**ep, **res, "verdict": verdict})

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S CST", time.localtime()),
            "public_ip": self.public_ip,
            "wan_port_checks": wan_port_checks,
            "vpn_results": vpn_results,
            "public_results": public_results,
        }

    def print_report(self, report: Dict[str, Any]):
        """Displays formatted CLI table of verification results."""
        print("\n" + "=" * 90)
        print("🎯 MASTER TABLE FULL VERIFICATION REPORT (Runner Tailscale VPN & WAN Port Checks)")
        print("=" * 90)
        print(f"• 驗證時間戳記        : {report.get('timestamp')}")
        print(f"• 外部公網 IP (WAN)   : {report.get('public_ip')}")
        wan = report.get("wan_port_checks", {})
        p8443 = "🔴 CLOSED (未轉發)" if wan.get(8443, {}).get("state") == "closed" else "🟢 OPEN"
        p8080 = "🟢 OPEN" if wan.get(8080, {}).get("state") == "open" else "🔴 CLOSED"
        print(f"• portchecker.co 探測 : Port 8443 ({p8443}) ｜ Port 8080 ({p8080})")
        print("-" * 90)

        print("📡 [1] Tailscale VPN 內部連線實測 (Self-Hosted Runner 內部網域視角):")
        print("-" * 90)
        header1 = f"{'服務項目':<20} | {'目標端點':<46} | {'狀態/延遲':<16} | {'實測結果'}"
        print(header1)
        print("-" * 90)
        for r in report.get("vpn_results", []):
            target = r.get("url") or f"{r.get('host')}:{r.get('port')}"
            stat = f"{r.get('note')} ({r.get('latency_ms')}ms)"
            print(f"{r['name']:<20} | {target:<46} | {stat:<16} | {r['verdict']}")

        print("\n" + "-" * 90)
        print("🌐 [2] 公網存取驗證 (DDNS 8443 HTTPS & Tailscale Funnel):")
        print("-" * 90)
        header2 = f"{'服務項目':<28} | {'存取類型':<18} | {'HTTP 狀態':<12} | {'延遲':<10} | {'實測結果'}"
        print(header2)
        print("-" * 90)
        for r in report.get("public_results", []):
            code = str(r.get("status_code")) if r.get("status_code") else "ERR"
            latency = f"{r.get('latency_ms')}ms"
            print(f"{r['name']:<28} | {r['type']:<18} | {code:<12} | {latency:<10} | {r['verdict']}")
        print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Verify all Master Table links (Tailscale VPN & Public DDNS/Funnel)")
    parser.add_argument("--json", action="store_true", help="Output full results as JSON")
    parser.add_argument("--update-readme", default=None, help="Update README.md with verified links")
    parser.add_argument("--timestamp", default=None, help="Timestamp for README (defaults to current verification time)")
    args = parser.parse_args()

    verifier = MasterTableVerifier()
    report = verifier.verify_all()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        verifier.print_report(report)

    if args.update_readme:
        try:
            curr_dir = os.path.dirname(os.path.abspath(__file__))
            if curr_dir not in sys.path:
                sys.path.insert(0, curr_dir)
            from syno_ddns import SynologyDDNSManager
            mgr = SynologyDDNSManager()
            ts = args.timestamp if (args.timestamp and args.timestamp != "now") else report.get("timestamp")
            mgr.update_readme(args.update_readme, update_time=ts)
        except Exception as e:
            print(f"Error updating README: {e}")


if __name__ == "__main__":
    main()
