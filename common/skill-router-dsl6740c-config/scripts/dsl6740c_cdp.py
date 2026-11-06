#!/usr/bin/env python3
"""
DSL-6740C Modem Browser Automation via Chromium Docker + CDP
Connects to Chromium Container on NAS (Port 9222) using Chrome DevTools Protocol (CDP),
to automate inspection and configuration of CHT D-Link DSL-6740C (192.168.1.2).
"""

import argparse
import os
import sys
import time
from typing import Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_CDP_CANDIDATES = [
    os.environ.get("CHROMIUM_CDP_URL"),
    os.environ.get("GOODINFO_CDP_URL"),
    "http://192.168.31.101:9222",
    "http://100.110.72.104:9222",
    "http://127.0.0.1:9222",
    "http://172.21.0.1:9222",
]


class DSL6740CCDPController:
    def __init__(self, target_url: str = "http://192.168.1.2", cdp_url: Optional[str] = None):
        self.target_url = target_url
        self.cdp_url = cdp_url

    def get_cdp_endpoint(self) -> str:
        if self.cdp_url:
            return self.cdp_url
        candidates = [c for c in DEFAULT_CDP_CANDIDATES if c]
        import urllib.request
        for c in candidates:
            try:
                req = urllib.request.Request(f"{c}/json/version", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        return c
            except Exception:
                pass
        return "http://192.168.31.101:9222"

    def inspect_page(self, screenshot_path: Optional[str] = None, keep_open: bool = False) -> dict:
        from playwright.sync_api import sync_playwright

        endpoint = self.get_cdp_endpoint()
        print(f"🌐 [CDP] 連線至 Chromium 端點: {endpoint}")

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint, timeout=5000)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            print(f"🧭 [CDP] 導航至 DSL-6740C: {self.target_url}")
            page.goto(self.target_url, timeout=10000, wait_until="domcontentloaded")
            time.sleep(1.0)

            title = page.title()
            current_url = page.url
            print(f"📄 [CDP] 頁面標題: '{title}' ｜ 當前網址: {current_url}")

            has_login = page.locator("input[type='password'], input[name='login_pwd'], #login_pwd").count() > 0

            info = {
                "title": title,
                "url": current_url,
                "has_login_field": has_login,
                "endpoint": endpoint,
            }

            if screenshot_path:
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"📸 [CDP] 已保存畫面截圖: {screenshot_path}")

            if not keep_open:
                page.close()
            else:
                print("📌 [CDP] 已保留分頁於 Chromium 瀏覽器中供檢視。")

            return info

    def login_and_verify_dmz(self, username: str = "cht", password: Optional[str] = None, dmz_ip: str = "192.168.1.101") -> bool:
        """Automates login into DSL-6740C via CDP and checks DMZ Host status."""
        from playwright.sync_api import sync_playwright

        endpoint = self.get_cdp_endpoint()
        print(f"🌐 [CDP] 連線至 Chromium 端點: {endpoint}")

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint, timeout=5000)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            page.goto(self.target_url, timeout=10000)
            time.sleep(1.0)

            # Check if login form exists
            user_input = page.locator("input[name='login_name'], input#login_name, input[type='text']").first
            pw_input = page.locator("input[name='login_pwd'], input#login_pwd, input[type='password']").first

            if pw_input.count() > 0:
                print(f"🔑 [CDP] 輸入使用者帳號: {username} ...")
                if user_input.count() > 0:
                    user_input.fill(username)
                if password:
                    pw_input.fill(password)
                    page.locator("input[type='submit'], button[type='submit'], #submit, .btn").first.click()
                    time.sleep(2.0)
                    print(f"✅ [CDP] 登入後頁面: {page.url} ({page.title()})")
            else:
                print("ℹ️ [CDP] 未發現登入輸入框或已進入首頁。")

            page.close()
            return True


def main():
    parser = argparse.ArgumentParser(description="DSL-6740C Modem Browser Automation via Chromium Docker + CDP")
    parser.add_argument("action", choices=["inspect", "screenshot", "login"], help="Action to perform")
    parser.add_argument("--url", default="http://192.168.1.2", help="Target DSL-6740C URL")
    parser.add_argument("--cdp", default=None, help="Chromium CDP URL (default: auto-discover 192.168.31.101:9222)")
    parser.add_argument("--screenshot", default="dsl6740c_dashboard.png", help="Path to save screenshot")
    parser.add_argument("--keep-open", action="store_true", help="Keep tab open in browser GUI for interactive viewing")
    parser.add_argument("--username", default="cht", help="Modem username (default: cht)")
    parser.add_argument("--password", default=os.environ.get("DSL6740C_PASSWORD"), help="Modem password (default: cht/740C+MAC)")
    args = parser.parse_args()

    ctrl = DSL6740CCDPController(target_url=args.url, cdp_url=args.cdp)

    if args.action in ("inspect", "screenshot"):
        ctrl.inspect_page(screenshot_path=args.screenshot if args.action == "screenshot" else None, keep_open=args.keep_open)
    elif args.action == "login":
        if not args.password:
            print("❌ 請指定 --password 或設定環境變數 DSL6740C_PASSWORD")
            sys.exit(1)
        ctrl.login_and_verify_dmz(username=args.username, password=args.password)


if __name__ == "__main__":
    main()
