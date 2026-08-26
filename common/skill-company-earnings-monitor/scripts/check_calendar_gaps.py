try:
    import self_update
except ImportError:
    pass


def find_repo_root():
    import os
    curr = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(curr, ".git")) or os.path.exists(os.path.join(curr, "requirements.txt")) or os.path.exists(os.path.join(curr, "CLAUDE.md")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        curr = parent

def setup_sys_path():
    import os
    import sys
    curr = os.path.dirname(os.path.abspath(__file__))
    repo_root = find_repo_root()
    p1 = os.path.join(repo_root, "scripts")
    if p1 not in sys.path and os.path.exists(p1):
        sys.path.append(p1)
    p2 = os.path.join(repo_root, "skills", "skill-taiex-report", "scripts")
    if p2 not in sys.path and os.path.exists(p2):
        sys.path.append(p2)
    temp = curr
    while temp and os.path.basename(temp) != "skills":
        parent = os.path.dirname(temp)
        if parent == temp:
            break
        temp = parent
    if os.path.basename(temp) == "skills":
        p3 = os.path.join(temp, "common", "skill-taiex-report", "scripts")
        if p3 not in sys.path and os.path.exists(p3):
            sys.path.append(p3)

setup_sys_path()

#!/usr/bin/env python3
import os
import re
import pandas as pd
from datetime import datetime, timedelta
try:
    import scripts.assembler_finguider as ag
except ModuleNotFoundError:
    import assembler_finguider as ag

ROOT = find_repo_root()
README_PATH = os.path.join(ROOT, "README.md")

def scan_calendar():
    if not os.path.exists(README_PATH): return
    
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 擷取表格內容
    table_match = re.search(r"<!-- EARNINGS_TABLE_START -->(.*)<!-- EARNINGS_TABLE_END -->", content, re.DOTALL)
    if not table_match: return
    
    table_rows = table_match.group(1).strip().split("\n")
    # 跳過標題與分隔線
    data_rows = [r for r in table_rows if "|" in r and ":---:" not in r and "財報日期" not in r]
    
    print(f"Scanning {len(data_rows)} calendar events for data readiness...")
    
    today = datetime.now().date()
    # 我們檢查過去 14 天到未來 7 天的事件 (避免掃描太舊的歷史)
    start_date = today - timedelta(days=14)
    end_date = today + timedelta(days=7)

    for row in data_rows:
        cols = [c.strip() for r in row.split("|") if (c := r.strip()) or True][1:-1]
        if len(cols) < 4: continue
        
        # 解析日期 (處理 icon)
        dt_str = re.search(r"\d{4}-\d{2}-\d{2}", cols[0]).group(0)
        dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        
        if not (start_date <= dt <= end_date): continue
        
        # 解析代號與期別
        ticker_match = re.search(r"\((\w+)\)", cols[2])
        if not ticker_match: continue
        ticker = ticker_match.group(1)
        
        # 解析期別 (e.g. 2026 Q1 -> 2026Q1)
        period = cols[3].split("<br/>")[0].replace(" ", "")
        
        print(f"  Checking {ticker} for {period} (Date: {dt_str})...")
        
        # 取得數據並驗證
        try:
            stock_data = ag.get_company_data(ticker, target_period=period)
            ready, gaps = ag._is_data_ready(ticker, stock_data, target_period=period)
            
            if not ready:
                ag._submit_data_gap_issue(ticker, period, gaps)
            else:
                print(f"    [OK] Data is ready for {ticker}")
        except Exception as e:
            print(f"    [Error] Failed to check {ticker}: {e}")

if __name__ == "__main__":
    scan_calendar()