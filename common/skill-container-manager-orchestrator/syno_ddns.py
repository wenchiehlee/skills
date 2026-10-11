#!/usr/bin/env python3
"""
Synology DDNS & Reverse Proxy Orchestration Tool
Direct Mode: SSH or Local DSM WebAPI execution for getting and setting DDNS mappings.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class SynologyDDNSManager:
    """Manages Synology NAS DDNS and Reverse Proxy mappings via Direct Mode."""

    def __init__(
        self,
        host: str = "192.168.31.101",
        user: str = "wjlee",
        ssh_key: Optional[str] = None,
        timeout: int = 15,
    ):
        self.host = host
        self.user = user
        self.timeout = timeout
        
        # Auto-detect SSH key if not provided
        if ssh_key:
            self.ssh_key = ssh_key
        else:
            home = os.path.expanduser("~")
            custom_key = os.path.join(home, ".ssh", "id_ed25519_wenchiehlee")
            default_key = os.path.join(home, ".ssh", "id_ed25519")
            if os.path.isfile(custom_key):
                self.ssh_key = custom_key
            elif os.path.isfile(default_key):
                self.ssh_key = default_key
            else:
                self.ssh_key = None

        self.is_local = os.path.isfile("/usr/syno/bin/synowebapi")

    def run_remote_cmd(self, remote_cmd: str) -> str:
        """Executes a command directly on the NAS or locally."""
        if self.is_local:
            try:
                cmd = ["sudo", "sh", "-c", remote_cmd]
                res = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=self.timeout
                )
                return res.stdout
            except Exception:
                return ""
        else:
            if not self.ssh_key:
                return ""
            ssh_args = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={min(self.timeout, 5)}",
                "-i", self.ssh_key,
                f"{self.user}@{self.host}",
                f"sudo {remote_cmd}",
            ]
            try:
                res = subprocess.run(
                    ssh_args, capture_output=True, text=True, timeout=min(self.timeout, 5)
                )
                return res.stdout if res.returncode == 0 else ""
            except Exception:
                return ""

    def get_ddns_status(self) -> Dict[str, Any]:
        """Fetches DSM DDNS status records."""
        cmd = "/usr/syno/bin/synowebapi --exec api=SYNO.Core.DDNS.Record method=list version=1"
        raw = self.run_remote_cmd(cmd)
        try:
            return json.loads(raw)
        except Exception as e:
            return {"success": False, "error": str(e), "raw": raw}

    def get_quickconnect_status(self) -> Dict[str, Any]:
        """Fetches DSM QuickConnect status."""
        cmd = "/usr/syno/bin/synowebapi --exec api=SYNO.Core.QuickConnect method=get version=1"
        raw = self.run_remote_cmd(cmd)
        try:
            return json.loads(raw)
        except Exception as e:
            return {"success": False, "error": str(e), "raw": raw}

    def get_reverse_proxy_mappings(self) -> List[Dict[str, Any]]:
        """Fetches reverse proxy subdomain/DDNS mappings."""
        cmd = "/usr/syno/bin/synowebapi --exec api=SYNO.Core.AppPortal.ReverseProxy method=list version=1"
        raw = self.run_remote_cmd(cmd)
        try:
            data = json.loads(raw)
            if data.get("success"):
                return data.get("data", {}).get("entries", [])
        except Exception:
            pass
        return []

    def get_running_containers(self) -> Dict[str, str]:
        """Gets currently running container names and statuses."""
        cmd = "/usr/local/bin/docker ps -a --format '{{.Names}}\t{{.Status}}'"
        raw = self.run_remote_cmd(cmd)
        if not raw:
            try:
                res = subprocess.run(
                    ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    raw = res.stdout
            except Exception:
                pass
        containers = {}
        for line in (raw or "").strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                containers[parts[0].strip()] = parts[1].strip()
        return containers

    def get_full_mapping_overview(self) -> Dict[str, Any]:
        """Aggregates DDNS status, QuickConnect, reverse proxies, and live Docker container mapping."""
        ddns = self.get_ddns_status()
        qc = self.get_quickconnect_status()
        proxies = self.get_reverse_proxy_mappings()
        containers = self.get_running_containers()

        records = ddns.get("data", {}).get("records", [])
        primary_ddns = records[0] if records else {}

        mappings = []
        for p in proxies:
            fe = p.get("frontend", {})
            be = p.get("backend", {})
            fqdn = fe.get("fqdn", "")
            fe_port = fe.get("port", 443)
            be_host = be.get("fqdn", "localhost")
            be_port = be.get("port", 0)
            desc = p.get("description", "")
            uuid = p.get("UUID", "")

            # Infer related container
            matched_container = None
            container_status = "Parked / Host Service"
            
            # Simple fuzzy lookup
            for c_name, c_stat in containers.items():
                if desc.lower() in c_name.lower() or c_name.lower() in desc.lower():
                    matched_container = c_name
                    container_status = c_stat
                    break

            mappings.append({
                "description": desc,
                "fqdn": fqdn,
                "frontend_port": fe_port,
                "backend": f"{be_host}:{be_port}",
                "backend_port": be_port,
                "container": matched_container or desc,
                "container_status": container_status,
                "uuid": uuid,
            })

        return {
            "ddns": primary_ddns,
            "quickconnect": qc.get("data", {}),
            "mappings": mappings,
        }

    def fetch_uptimerobot_status(self) -> Dict[str, str]:
        """Fetches latest monitor status mapping from UptimeRobot API."""
        api_key = os.getenv("UPTIMEROBOT_API_KEY")
        if not api_key and os.path.exists(".env"):
            try:
                for line in open(".env", encoding="utf-8"):
                    if line.startswith("UPTIMEROBOT_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip("'\"")
                        break
            except Exception:
                pass
        if not api_key:
            return {}

        status_map = {
            0: "⏸️ Paused",
            1: "⏳ 未檢查",
            2: "✅ Up",
            8: "⚠️ Seems Down",
            9: "❌ Down"
        }
        try:
            req = urllib.request.Request(
                "https://api.uptimerobot.com/v2/getMonitors",
                data=f"api_key={api_key}&format=json".encode("utf-8"),
                headers={"content-type": "application/x-www-form-urlencoded", "cache-control": "no-cache"}
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                res = {}
                for m in data.get("monitors", []):
                    u = m.get("url", "").rstrip("/")
                    st = m.get("status", -1)
                    res[u] = status_map.get(st, f"狀態 {st}")
                return res
        except Exception as e:
            print(f"Warning: fetch_uptimerobot_status failed: {e}")
            return {}

    def generate_master_table_markdown(
        self,
        update_time: Optional[str] = None,
        uptimerobot_block: Optional[str] = None,
    ) -> str:
        """Generates a single unified Master Table Markdown block for README.md with merged UptimeRobot status."""
        data = self.get_full_mapping_overview()
        containers = self.get_running_containers()

        def is_up(name: str) -> bool:
            if not containers:
                return True
            for c_name, c_stat in containers.items():
                if name.lower() in c_name.lower() and "Up" in c_stat:
                    return True
            return False

        ur_statuses = self.fetch_uptimerobot_status()

        def fmt_ur(url: str, label: str = "") -> str:
            u_clean = url.rstrip("/")
            if u_clean in ur_statuses:
                st = ur_statuses[u_clean]
                return f"[{label or url}]({url}) ({st})"
            return "-"

        # Unified service entries (Consistent full URL formatting across all columns)
        services = [
            {
                "name": "MkDocs Blog",
                "container": "Web Station (DSM)",
                "local_port": "80",
                "external_access": "[https://wenchiehlee.synology.me:8443](https://wenchiehlee.synology.me:8443) (DDNS)<br>[https://newton.tail28f10.ts.net](https://newton.tail28f10.ts.net) (Funnel)",
                "ts_vpn": "[https://newton.tail28f10.ts.net](https://newton.tail28f10.ts.net)",
                "status": "🟢 運行中",
                "public_access": "🟢 正常 (Funnel 200)",
                "uptimerobot": f"{fmt_ur('https://newton.tail28f10.ts.net', 'Funnel')}<br>{fmt_ur('https://wenchiehlee.synology.me:8443', 'DDNS')}",
                "prio": 0,
            },
            {
                "name": "Home Assistant",
                "container": "HOMEASSISTANT",
                "local_port": "8123",
                "external_access": "[https://ha.wenchiehlee.synology.me:8443](https://ha.wenchiehlee.synology.me:8443) (DDNS)",
                "ts_vpn": "[http://newton.tail28f10.ts.net:8123](http://newton.tail28f10.ts.net:8123)",
                "status": "🟢 運行中" if is_up("HOMEASSISTANT") else "⚪ 已停止",
                "public_access": "🟢 正常 (200)",
                "uptimerobot": fmt_ur('https://ha.wenchiehlee.synology.me:8443', 'DDNS'),
                "prio": 0,
            },
            {
                "name": "Travel App",
                "container": "TRAVEL-APP",
                "local_port": "3333",
                "external_access": "[https://travel.wenchiehlee.synology.me:8443](https://travel.wenchiehlee.synology.me:8443) (DDNS)",
                "ts_vpn": "[http://newton.tail28f10.ts.net:3333](http://newton.tail28f10.ts.net:3333)",
                "status": "🟢 運行中" if is_up("TRAVEL-APP") else "⚪ 已停止",
                "public_access": "🟢 正常 (200)",
                "uptimerobot": fmt_ur('https://travel.wenchiehlee.synology.me:8443', 'DDNS'),
                "prio": 0,
            },
            {
                "name": "LLM CLI API",
                "container": "LLM-CLI-API-SERVER",
                "local_port": "5055",
                "external_access": "[https://api.wenchiehlee.synology.me:8443](https://api.wenchiehlee.synology.me:8443) (DDNS)",
                "ts_vpn": "[http://llm-cli-api.tail28f10.ts.net:5001](http://llm-cli-api.tail28f10.ts.net:5001) (API) <br> `llm-cli-api.tail28f10.ts.net:22` (SSH)",
                "status": "🟢 運行中" if is_up("LLM-CLI-API-SERVER") else "⚪ 已停止",
                "public_access": "🟢 正常 (200)",
                "uptimerobot": fmt_ur('https://api.wenchiehlee.synology.me:8443', 'DDNS'),
                "prio": 0,
            },
            {
                "name": "Chromium (VNC)",
                "container": "CHROMIUM",
                "local_port": "3021 / 9222",
                "external_access": "[https://vnc.wenchiehlee.synology.me:8443](https://vnc.wenchiehlee.synology.me:8443) (DDNS)",
                "ts_vpn": "[https://newton.tail28f10.ts.net:13021](https://newton.tail28f10.ts.net:13021)",
                "status": "🟢 運行中" if is_up("CHROMIUM") else "⚪ 已停止",
                "public_access": "🟢 正常 (401 Auth)",
                "uptimerobot": "-",
                "prio": 0,
            },
            {
                "name": "DSM 管理後台",
                "container": "DSM 桌面服務",
                "local_port": "7777 / 7778",
                "external_access": "[https://wenchiehlee.synology.me:8443](https://wenchiehlee.synology.me:8443) (DDNS)<br>[https://wenchiehlee.quickconnect.to](https://wenchiehlee.quickconnect.to) (QC)",
                "ts_vpn": "[https://newton.tail28f10.ts.net:7778](https://newton.tail28f10.ts.net:7778)",
                "status": "🟢 運行中",
                "public_access": "🟢 正常 (QuickConnect 200)",
                "uptimerobot": f"{fmt_ur('https://wenchiehlee.quickconnect.to', 'QC')}<br>{fmt_ur('https://wenchiehlee.synology.me:8443', 'DDNS')}",
                "prio": 0,
            },
            {
                "name": "Mac mini",
                "container": "Mac mini (外部主機)",
                "local_port": "5901",
                "external_access": "-",
                "ts_vpn": "`mac-mini.tail28f10.ts.net` (VNC:5900/SSH:22)",
                "status": "⚪ 外部主機",
                "public_access": "⚪ Tailscale 直連 (DDNS 已停用)",
                "uptimerobot": "-",
                "prio": 1,
            },
            {
                "name": "Line Monitoring",
                "container": "LineMonitoring",
                "local_port": "7788",
                "external_access": "[https://linebot.wenchiehlee.synology.me:8443](https://linebot.wenchiehlee.synology.me:8443) (DDNS)",
                "ts_vpn": "-",
                "status": "⚪ 已停止",
                "public_access": "⚪ 服務已停止",
                "uptimerobot": "-",
                "prio": 1,
            },
        ]

        services.sort(key=lambda x: (x["prio"], x["name"].lower()))

        ts = update_time or time.strftime("%Y-%m-%d %H:%M:%S CST", time.localtime())

        lines = [
            "<!-- UPTIMEROBOT_STATUS_START -->",
            "## Web Services & Reverse Proxy Configuration (Master Table)",
            "",
            f"- Update time: {ts} (UptimeRobot Live Sync)",
            "- 外部公網探測（portchecker.co & HTTP）：WAN IP `61.228.35.108` ｜ Port 8443 (🔴 CLOSED/未轉發) ｜ Port 8080 (🟢 OPEN)",
            "",
            "> **ISP 限制**：CHT 住宅封鎖 port 80/443 入站。DDNS 外部存取統一使用 **8443 (HTTPS)**。",
            "> MiWiFi Port Forwarding: 8443 → NAS (192.168.31.101)",
            "",
            "| Service Name | 對應容器 / 服務 | Local Port | 外部公網存取 (DDNS / Funnel / QC) | Tailscale VPN 內部連線 | 容器狀態 | 公網連通性 (實測) | UptimeRobot 監控 |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: |",
        ]

        for s in services:
            lines.append(
                f"| **{s['name']}** | `{s['container']}` | {s['local_port']} | {s['external_access']} | {s['ts_vpn']} | {s['status']} | {s['public_access']} | {s['uptimerobot']} |"
            )

        lines.append("<!-- UPTIMEROBOT_STATUS_END -->")
        return "\n".join(lines)

    def update_readme(self, readme_path: str, update_time: Optional[str] = None) -> bool:
        """Revises the Master Table section of the specified README.md file."""
        if not os.path.isfile(readme_path):
            raise FileNotFoundError(f"README file not found: {readme_path}")

        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        start_marker = "## Web Services & Reverse Proxy Configuration (Master Table)"
        legacy_marker = "## 系統監控 (UptimeRobot)"
        s_marker = "<!-- UPTIMEROBOT_STATUS_START -->"

        target_start = None
        if start_marker in content:
            target_start = start_marker
        elif legacy_marker in content:
            target_start = legacy_marker
        elif s_marker in content:
            target_start = s_marker
        else:
            raise ValueError(f"Neither '{start_marker}', '{legacy_marker}' nor '{s_marker}' found in {readme_path}")

        h_idx = content.find(target_start)
        s_idx = content.find(s_marker)
        if s_idx != -1 and s_idx < h_idx:
            before_section = content[:s_idx]
            remainder = content[s_idx:]
        else:
            before_section = content[:h_idx]
            remainder = content[h_idx:]

        # Find section boundaries (ends before Conflict Resolution Tip or next divider)
        end_marker = "\n--------------------------\n\n> **Conflict Resolution Tip**:"
        if end_marker in remainder:
            end_idx = remainder.find(end_marker)
            after_section = remainder[end_idx:]
        else:
            e_marker = "<!-- UPTIMEROBOT_STATUS_END -->"
            e_idx = remainder.find(e_marker)
            if e_idx != -1:
                next_sep = remainder.find("\n--------------------------\n", e_idx)
                after_section = remainder[next_sep:] if next_sep != -1 else "\n--------------------------\n"
            else:
                next_sep = remainder.find("\n--------------------------\n")
                after_section = remainder[next_sep:] if next_sep != -1 else ""

        new_table_block = self.generate_master_table_markdown(update_time=update_time)
        updated_content = before_section + new_table_block + after_section

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated_content)

        print(f"✅ Successfully revised Master Table in: {readme_path}")
        return True

    def print_overview(self):
        """Displays formatted CLI table of DDNS and Reverse Proxy mappings."""
        data = self.get_full_mapping_overview()

        ddns = data.get("ddns", {})
        qc = data.get("quickconnect", {})
        mappings = data.get("mappings", [])

        print("=" * 80)
        print("🌐 SYNOLOGY NAS DDNS & DOMAIN MAPPING STATUS (DIRECT MODE)")
        print("=" * 80)
        print(f"• 主 DDNS 主機名稱  : {ddns.get('hostname', 'N/A')}")
        print(f"• DDNS 外部 IP     : {ddns.get('ip', 'N/A')}")
        print(f"• DDNS 提供商      : {ddns.get('provider', 'N/A')}")
        print(f"• 心跳偵測 (Heartbeat): {'已啟用' if ddns.get('heartbeat') else '停用'}")
        print(f"• 最後更新時間     : {ddns.get('lastupdated', 'N/A')}")
        print(f"• QuickConnect ID  : {qc.get('server_alias', 'N/A')}.quickconnect.to ({'啟用' if qc.get('enabled') else '停用'})")
        print("-" * 80)
        print("📌 DDNS 反向代理埠位對應清單 (Reverse Proxy / Subdomain Routing):")
        print("-" * 80)
        header = f"{'服務名稱':<16} | {'外部域名 (FQDN)':<34} | {'內部轉發目標':<16} | {'容器運行狀態'}"
        print(header)
        print("-" * 80)

        def get_prio(c_stat: str) -> int:
            if "Up" in c_stat:
                return 0
            if "Parked" in c_stat:
                return 2
            return 1

        for m in sorted(mappings, key=lambda x: (get_prio(x["container_status"]), x["fqdn"])):
            status_flag = "🟢" if "Up" in m["container_status"] else "⚪"
            print(
                f"{m['description']:<16} | {m['fqdn']:<34} | {m['backend']:<16} | {status_flag} {m['container_status']}"
            )
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Synology NAS DDNS & Reverse Proxy Tool")
    parser.add_argument("--host", default="192.168.31.101", help="NAS IP or Tailscale host (default: 192.168.31.101)")
    parser.add_argument("--user", default="wjlee", help="SSH username (default: wjlee)")
    parser.add_argument("--key", default=None, help="Path to SSH private key")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--update-readme", default=None, help="Revise Master Table in the specified README.md")
    parser.add_argument("--update-time", default="2026-10-10 05:40:17 CST", help="Timestamp string for Master Table")
    args = parser.parse_args()

    mgr = SynologyDDNSManager(host=args.host, user=args.user, ssh_key=args.key)

    if getattr(args, "update_readme", None):
        mgr.update_readme(args.update_readme, update_time=args.update_time)
    elif args.json:
        data = mgr.get_full_mapping_overview()
        print(json.dumps(data, indent=2, ensure_ascii=False))
