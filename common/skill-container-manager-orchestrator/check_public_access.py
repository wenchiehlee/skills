#!/usr/bin/env python3
"""
Public Link & Port Accessibility Checker (via portchecker.co & HTTP Probe)
==========================================================================
Part of skill-container-manager-orchestrator.
Verifies external reachability of Synology NAS services, DDNS endpoints,
Tailscale Funnel, and router port forwarding rules from the public Internet.
"""

import argparse
import http.cookiejar
import json
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


class PublicAccessChecker:
    def __init__(self, default_ip: Optional[str] = None):
        self.default_ip = default_ip or "61.228.35.108"
        self.session_opener = None
        self._init_session()

    def _init_session(self):
        cj = http.cookiejar.CookieJar()
        self.session_opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cj)
        )

    def get_public_ip(self) -> str:
        """Determines the current public IPv4 address."""
        if self.default_ip:
            return self.default_ip
        endpoints = [
            "https://api.ipify.org",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
        ]
        for ep in endpoints:
            try:
                req = urllib.request.Request(
                    ep, headers={"User-Agent": "curl/7.68.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                        self.default_ip = ip
                        return ip
            except Exception:
                continue
        return "61.228.35.108"

    def check_port_via_portchecker(
        self, target_ip: str, port: int, retries: int = 2
    ) -> Dict[str, Any]:
        """Queries portchecker.co to check if a specific port is open to the public Internet."""
        base_url = "https://portchecker.co/"
        check_url = "https://portchecker.co/check-v0"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(retries):
            try:
                # 1. Fetch CSRF token
                req_get = urllib.request.Request(base_url, headers=headers)
                resp_get = self.session_opener.open(req_get, timeout=8)
                html_get = resp_get.read().decode("utf-8")
                csrf_match = re.search(r'name="_csrf" value="([^"]+)"', html_get)
                if not csrf_match:
                    raise ValueError("Could not extract CSRF token from portchecker.co")
                csrf = csrf_match.group(1)

                # Delay slightly to avoid aggressive rate limiting
                time.sleep(1.0)

                # 2. Post verification request
                post_data = urllib.parse.urlencode({
                    "_csrf": csrf,
                    "target_ip": target_ip,
                    "port": str(port),
                }).encode("utf-8")

                req_post = urllib.request.Request(
                    check_url,
                    data=post_data,
                    headers={
                        **headers,
                        "Referer": base_url,
                        "Origin": base_url,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                resp_post = self.session_opener.open(req_post, timeout=12)
                html_post = resp_post.read().decode("utf-8")

                # 3. Parse results
                # Look for <span class="green">open</span> or <span class="red">closed</span>
                m = re.search(
                    r"Port\s+\d+\s+is\s+<span[^>]*class=[\"']([^\"']+)[\"'][^>]*>(open|closed)</span>",
                    html_post,
                    re.I,
                )
                if m:
                    state = m.group(2).lower()
                    return {
                        "status": "success",
                        "target": target_ip,
                        "port": port,
                        "state": state,
                        "accessible": (state == "open"),
                        "source": "portchecker.co",
                    }

                if "is open" in html_post.lower():
                    return {
                        "status": "success",
                        "target": target_ip,
                        "port": port,
                        "state": "open",
                        "accessible": True,
                        "source": "portchecker.co",
                    }
                elif "is closed" in html_post.lower():
                    return {
                        "status": "success",
                        "target": target_ip,
                        "port": port,
                        "state": "closed",
                        "accessible": False,
                        "source": "portchecker.co",
                    }

                return {
                    "status": "unknown",
                    "target": target_ip,
                    "port": port,
                    "state": "unknown",
                    "accessible": False,
                    "source": "portchecker.co",
                }

            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < retries - 1:
                    time.sleep(2.5)
                    self._init_session()
                    continue
                return {
                    "status": "error",
                    "target": target_ip,
                    "port": port,
                    "error": f"HTTP {e.code}: {e.reason}",
                    "accessible": False,
                    "source": "portchecker.co",
                }
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1.5)
                    continue
                return {
                    "status": "error",
                    "target": target_ip,
                    "port": port,
                    "error": str(e),
                    "accessible": False,
                    "source": "portchecker.co",
                }

    def check_http_url(self, url: str, timeout: float = 6.0) -> Dict[str, Any]:
        """Checks if a public URL responds to HTTP/HTTPS requests."""
        start_time = time.time()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # Allow self-signed or internal CA

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                elapsed_ms = round((time.time() - start_time) * 1000, 1)
                status_code = resp.status
                return {
                    "url": url,
                    "status_code": status_code,
                    "accessible": (200 <= status_code < 400),
                    "latency_ms": elapsed_ms,
                    "error": None,
                }
        except urllib.error.HTTPError as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 1)
            # HTTP 401/403/404 still indicates the web server is reachable
            is_reachable = e.code in (401, 403, 404, 405)
            return {
                "url": url,
                "status_code": e.code,
                "accessible": is_reachable,
                "latency_ms": elapsed_ms,
                "error": f"HTTP {e.code}: {e.reason}",
            }
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 1)
            return {
                "url": url,
                "status_code": None,
                "accessible": False,
                "latency_ms": elapsed_ms,
                "error": str(e),
            }

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Runs complete external access check for configured services."""
        pub_ip = self.get_public_ip()

        # 1. Check Port Forwarding on WAN via portchecker.co
        ports_to_check = [8443, 8080]
        port_results = {}
        for p in ports_to_check:
            res = self.check_port_via_portchecker(pub_ip, p)
            port_results[p] = res
            time.sleep(1.0)

        # 2. Check Public HTTP Links
        services = [
            {
                "name": "Tailscale Funnel (MkDocs)",
                "type": "Tailscale Funnel",
                "url": "https://newton.tail28f10.ts.net",
                "port": 443,
            },
            {
                "name": "QuickConnect (DSM)",
                "type": "QuickConnect",
                "url": "https://wenchiehlee.quickconnect.to",
                "port": 443,
            },
            {
                "name": "DDNS HTTPS (MkDocs)",
                "type": "DDNS (8443)",
                "url": "https://wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "DDNS HTTPS (Home Assistant)",
                "type": "DDNS (8443)",
                "url": "https://ha.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "DDNS HTTPS (Travel App)",
                "type": "DDNS (8443)",
                "url": "https://travel.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "DDNS HTTPS (LLM API)",
                "type": "DDNS (8443)",
                "url": "https://api.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "DDNS HTTPS (Chromium VNC)",
                "type": "DDNS (8443)",
                "url": "https://vnc.wenchiehlee.synology.me:8443",
                "port": 8443,
            },
            {
                "name": "DDNS HTTP (Legacy 8080)",
                "type": "DDNS (8080)",
                "url": "http://wenchiehlee.synology.me:8080",
                "port": 8080,
            },
        ]

        url_results = []
        for s in services:
            res = self.check_http_url(s["url"])
            url_results.append({**s, **res})

        return {
            "public_ip": pub_ip,
            "port_checks": port_results,
            "url_checks": url_results,
        }

    def print_report(self, report: Dict[str, Any]):
        """Prints a human-readable CLI verification report."""
        pub_ip = report.get("public_ip", "Unknown")
        port_checks = report.get("port_checks", {})
        url_checks = report.get("url_checks", [])

        print("=" * 86)
        print("🌐 PUBLIC LINK & PORT ACCESSIBILITY REPORT (via portchecker.co & HTTP Probe)")
        print("=" * 86)
        print(f"• 外部公網 IP (WAN) : {pub_ip}")
        print("• 外部埠位探測來源  : https://portchecker.co")
        print("-" * 86)
        print("📡 路由器 WAN 外部埠位開放狀態 (Router Port Forwarding via portchecker.co):")
        print("-" * 86)
        for p, r in port_checks.items():
            state = r.get("state", "unknown")
            if state == "open":
                icon = "🟢 [OPEN 開放]"
            elif state == "closed":
                icon = "🔴 [CLOSED 關閉/未轉發]"
            else:
                icon = f"⚪ [{r.get('error', '未知')}]"
            print(f"  • Port {p:<5} : {icon:<26} (Target: {pub_ip})")
        print("-" * 86)
        print("🔗 公網服務端點即時連線性檢測 (Public Endpoints Reachability):")
        print("-" * 86)
        header = f"{'服務項目':<26} | {'連線類型':<16} | {'HTTP 狀態':<10} | {'延遲':<8} | {'存取結論'}"
        print(header)
        print("-" * 86)

        for u in url_checks:
            name = u.get("name", "")
            channel_type = u.get("type", "")
            code = u.get("status_code")
            code_str = str(code) if code else "ERR"
            latency = f"{u.get('latency_ms', 0)}ms"
            
            # Reachability evaluation
            if u.get("accessible"):
                verdict = "🟢 正常可存取"
            else:
                port = u.get("port")
                if port in port_checks and port_checks[port].get("state") == "closed":
                    verdict = "🔴 WAN 埠未轉發"
                else:
                    verdict = "🔴 無法連線"

            print(f"{name:<26} | {channel_type:<16} | {code_str:<10} | {latency:<8} | {verdict}")

        print("=" * 86)


def main():
    parser = argparse.ArgumentParser(
        description="Verify external accessibility of public links and ports via portchecker.co"
    )
    parser.add_argument(
        "--ip", default="61.228.35.108", help="Target public IP (default: 61.228.35.108)"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Check a specific port on portchecker.co"
    )
    parser.add_argument(
        "--url", default=None, help="Check a specific HTTP/HTTPS URL"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output full report as JSON"
    )
    parser.add_argument(
        "--update-readme", default=None, help="Update Master Table in README.md with live results"
    )
    parser.add_argument(
        "--update-time", default="2026-10-10 05:40:17 CST", help="Timestamp string for Master Table"
    )
    args = parser.parse_args()

    checker = PublicAccessChecker(default_ip=args.ip)

    if getattr(args, "update_readme", None):
        try:
            from syno_ddns import SynologyDDNSManager
            mgr = SynologyDDNSManager()
            mgr.update_readme(args.update_readme, update_time=args.update_time)
        except Exception as e:
            print(f"Error updating README: {e}")
    elif args.port:
        res = checker.check_port_via_portchecker(checker.get_public_ip(), args.port)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            state = res.get("state", "unknown")
            icon = "🟢 開放 (OPEN)" if state == "open" else "🔴 關閉 (CLOSED)"
            print(f"portchecker.co: Port {args.port} on {res.get('target')} is {icon}")
    elif args.url:
        res = checker.check_http_url(args.url)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            status = "🟢 可存取" if res.get("accessible") else "🔴 無法存取"
            print(f"URL: {args.url} -> {status} (Status: {res.get('status_code')}, {res.get('latency_ms')}ms)")
            if res.get("error"):
                print(f"Error: {res.get('error')}")
    else:
        report = checker.run_full_diagnostic()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            checker.print_report(report)


if __name__ == "__main__":
    main()
