#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_watchlist.py
Description: Downloads the Taiwan stock market focus list (used to scope TAIEX's
             TW earnings coverage) directly from the same public source biztrends.TW's
             Get觀察名單.py uses (wenchiehlee/Selenium-Actions.Auction), so TAIEX.TW
             doesn't depend on biztrends.TW (private repo) being fresh or reachable.
             專注名單.csv -> data/biztrends.TW/StockID_TWSE_TPEX_focus.csv
"""

import os
import urllib.error
import urllib.request
from datetime import datetime


def download_file(url, output_file, description):
    try:
        print(f"正在下載 {description}...")
        print(f"來源: {url}")

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()

        content = raw.decode("utf-8-sig")  # normalize away BOM if present

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = os.path.getsize(output_file)
        print(f"OK {description} 下載成功! -> {output_file} ({file_size:,} bytes)")
        return True

    except urllib.error.URLError as e:
        print(f"FAILED {description} 下載失敗: {e}")
        return False
    except Exception as e:
        print(f"FAILED {description} 處理時發生錯誤: {e}")
        return False


def find_repo_root():
    curr = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(curr, ".git")) or os.path.exists(os.path.join(curr, "requirements.txt")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        curr = parent


def main():
    print("=" * 60)
    print("TAIEX.TW TW watchlist sync (biztrends.TW 專注名單)")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    base_url = "https://raw.githubusercontent.com/wenchiehlee/Selenium-Actions.Auction/refs/heads/main"
    url_focus = f"{base_url}/%E5%B0%88%E6%B3%A8%E5%90%8D%E5%96%AE.csv"

    root = find_repo_root()
    file_focus = os.path.join(root, "data", "biztrends.TW", "StockID_TWSE_TPEX_focus.csv")

    ok = download_file(url_focus, file_focus, "專注名單")
    if not ok:
        exit(1)


if __name__ == "__main__":
    main()
