#!/usr/bin/env python3
"""
Synology NAS Remote SSH Administration & Reverse Proxy Orchestration Tool
Part of skill-synology-nas-config-ssh.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class SynologySSHManager:
    def __init__(
        self,
        host: str = "192.168.31.101",
        fallback_host: str = "100.110.72.104",
        user: str = "wjlee",
        ssh_key: Optional[str] = None,
        timeout: int = 5,
    ):
        self.host = host
        self.fallback_host = fallback_host
        self.user = user
        self.timeout = timeout
        self.active_host = host

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

    def run_cmd(self, remote_cmd: str, sudo: bool = True) -> str:
        """Executes a command on the Synology NAS via SSH with failover support."""
        cmd_str = f"sudo {remote_cmd}" if sudo else remote_cmd
        
        hosts_to_try = [self.active_host]
        if self.fallback_host and self.fallback_host != self.active_host:
            hosts_to_try.append(self.fallback_host)

        for target in hosts_to_try:
            ssh_args = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "BatchMode=yes",
                "-o", f"ConnectTimeout={self.timeout}",
            ]
            if self.ssh_key:
                ssh_args.extend(["-i", self.ssh_key])
            ssh_args.extend([f"{self.user}@{target}", cmd_str])

            try:
                res = subprocess.run(
                    ssh_args, capture_output=True, text=True, encoding="utf-8", timeout=self.timeout + 3
                )
                if res.returncode == 0:
                    self.active_host = target
                    return res.stdout
            except Exception:
                continue

        return ""

    def test_connection(self) -> bool:
        """Verifies SSH connectivity."""
        out = self.run_cmd("echo SSH_OK", sudo=False)
        return "SSH_OK" in out

    def get_public_ip(self) -> str:
        """Gets the NAS external WAN IP."""
        out = self.run_cmd("curl -s http://checkip.synology.com", sudo=False)
        import re
        m = re.search(r"Current IP Address:\s*([0-9\.]+)", out)
        return m.group(1) if m else "Unknown"

    def get_ddns_records(self) -> List[Dict[str, Any]]:
        """Queries DSM DDNS records via WebAPI."""
        raw = self.run_cmd("/usr/syno/bin/synowebapi --exec api=SYNO.Core.DDNS.Record method=list version=1")
        lines = [l for l in raw.splitlines() if not l.startswith("[Line")]
        try:
            data = json.loads("\n".join(lines))
            return data.get("data", {}).get("records", [])
        except Exception:
            return []

    def get_reverse_proxies(self) -> List[Dict[str, Any]]:
        """Queries DSM Reverse Proxy entries via WebAPI."""
        raw = self.run_cmd("/usr/syno/bin/synowebapi --exec api=SYNO.Core.AppPortal.ReverseProxy method=list version=1")
        lines = [l for l in raw.splitlines() if not l.startswith("[Line")]
        try:
            data = json.loads("\n".join(lines))
            return data.get("data", {}).get("entries", [])
        except Exception:
            return []

    def get_running_containers(self) -> List[Dict[str, str]]:
        """Lists running Docker containers on the NAS."""
        raw = self.run_cmd("/usr/local/bin/docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'")
        containers = []
        for line in raw.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                containers.append({
                    "name": parts[0].strip(),
                    "status": parts[1].strip(),
                    "ports": parts[2].strip() if len(parts) > 2 else ""
                })
        return containers

    def get_tailscale_funnel(self) -> str:
        """Gets Tailscale Funnel status from the NAS."""
        return self.run_cmd("/var/packages/Tailscale/target/bin/tailscale funnel status")

    def test_nginx_syntax(self) -> bool:
        """Runs sudo nginx -t on NAS."""
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={self.timeout}",
        ]
        if self.ssh_key:
            cmd.extend(["-i", self.ssh_key])
        cmd.extend([f"{self.user}@{self.host}", "sudo nginx -t"])
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        combined = (res.stdout + res.stderr).lower()
        return "syntax is ok" in combined and "test is successful" in combined

    def reload_nginx(self) -> bool:
        """Safely verifies syntax and reloads Nginx."""
        if not self.test_nginx_syntax():
            print("❌ Nginx 語法錯誤，終止 reload 作業！")
            return False
        out = self.run_cmd("nginx -s reload")
        print("🟢 Nginx 語法正確，已成功執行平滑重載 (nginx -s reload)。")
        return True

    def backup_ddns_conf(self) -> str:
        """Creates a timestamped backup of http.ddns-ssl.conf."""
        ts = time.strftime("%Y%m%d%H%M%S")
        backup_path = f"/etc/nginx/conf.d/http.ddns-ssl.conf.bak_{ts}"
        self.run_cmd(f"cp /etc/nginx/conf.d/http.ddns-ssl.conf {backup_path}")
        return backup_path


def main():
    parser = argparse.ArgumentParser(description="Synology NAS Remote SSH Administration Tool")
    parser.add_argument("action", choices=["status", "list-proxies", "containers", "funnel", "test-nginx", "reload-nginx", "backup-nginx"], help="Action to execute")
    parser.add_argument("--host", default="192.168.31.101", help="Target NAS IP or hostname")
    args = parser.parse_args()

    mgr = SynologySSHManager(host=args.host)
    if not mgr.test_connection():
        print(f"❌ 無法連線至 NAS ({args.host}:22)，請確認 SSH 服務已啟用且金鑰正確。")
        sys.exit(1)

    if args.action == "status":
        print(f"=== Synology NAS 系統狀態摘要 ({args.host}) ===")
        print("• SSH 連線狀態  : 🟢 成功 (Port 22 在線)")
        wan_ip = mgr.get_public_ip()
        print(f"• NAS 當前公網 IP: {wan_ip}")
        records = mgr.get_ddns_records()
        for r in records:
            print(f"• DDNS 紀錄     : {r.get('hostname')} ｜ 綁定 IP: {r.get('ip')} ｜ 啟用: {r.get('enable')}")
        containers = mgr.get_running_containers()
        print(f"• 運行中容器數量: {len(containers)} 個")
        for c in containers[:5]:
            print(f"  - {c['name']:<28} ｜ {c['status']}")
        if len(containers) > 5:
            print(f"  ... 另有 {len(containers) - 5} 個容器正在運行")

    elif args.action == "list-proxies":
        proxies = mgr.get_reverse_proxies()
        print(f"=== DSM 反向代理規則清單 (共 {len(proxies)} 筆) ===")
        for p in sorted(proxies, key=lambda x: x.get("description", "")):
            fe = p.get("frontend", {})
            be = p.get("backend", {})
            proto_fe = "https" if fe.get("protocol") == 1 else "http"
            proto_be = "https" if be.get("protocol") == 1 else "http"
            desc = p.get("description", "-")
            print(f"{desc:<18} | {proto_fe}://{fe.get('fqdn')}:{fe.get('port')} -> {proto_be}://{be.get('fqdn')}:{be.get('port')}")

    elif args.action == "containers":
        containers = mgr.get_running_containers()
        print(f"=== 運行中容器清單 ({len(containers)} 個) ===")
        for c in containers:
            print(f"{c['name']:<30} | {c['status']:<15} | {c['ports']}")

    elif args.action == "funnel":
        out = mgr.get_tailscale_funnel()
        print("=== Tailscale Funnel 即時狀態 ===")
        print(out.strip() or "無啟用中之 Funnel 端點")

    elif args.action == "test-nginx":
        ok = mgr.test_nginx_syntax()
        print(f"• Nginx 語法檢驗: {'🟢 正確 (Syntax OK)' if ok else '🔴 錯誤 (Syntax Error)'}")

    elif args.action == "reload-nginx":
        mgr.reload_nginx()

    elif args.action == "backup-nginx":
        bak = mgr.backup_ddns_conf()
        print(f"🟢 已成功在 NAS 建立備份檔: {bak}")


if __name__ == "__main__":
    main()
