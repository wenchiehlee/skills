"""Fetch dividend announcement events (董事會決議) for TWSE/TPEX (Taiwan) and major US stocks.

Data sources:
- Taiwan Dividends: MOPS (公開資訊觀測站) ajax_t05st01 (重大訊息：董事會決議發放股利)
- US Dividends:     yfinance
"""

import csv
import io
import os
import re
import sys
import time
from datetime import datetime, timedelta

import urllib3
import requests
import yfinance as yf
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

OUTPUT_FILE = "raw_event_dividends_announce.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]

# 監控的美股清單
_METADATA_CSV_PATHS = [
    "../ConceptStocks/raw_conceptstock_company_metadata.csv",
    "raw_conceptstock_company_metadata.csv",
]

def _load_us_watchlist() -> dict[str, str]:
    """載入 {Ticker: 公司名稱}"""
    for path in _METADATA_CSV_PATHS:
        if not os.path.exists(path):
            continue
        result = {}
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("Ticker", "").strip()
                name   = row.get("公司名稱", "").strip()
                if ticker and ticker != "-":
                    result[ticker] = name
        return result
    return {}

WATCHLIST_CSV = "StockID_TWSE_TPEX.csv"

def _load_tw_watchlist(csv_path: str) -> dict[str, str]:
    """載入 {code: name}"""
    watchlist: dict[str, str] = {}
    if not os.path.exists(csv_path):
        return watchlist
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get("代號", "").strip()
            name = row.get("名稱", "").strip()
            if code and code != "0000":
                watchlist[code] = name
    return watchlist

MOPS_REDIRECT_URL = "https://mops.twse.com.tw/mops/api/redirectToOld"

def fetch_tw_dividends() -> list[list]:
    """透過 MOPS 重大訊息抓取董事會決議股利分派事件。"""
    tw_watchlist = _load_tw_watchlist(WATCHLIST_CSV)
    if not tw_watchlist:
        return []

    results = []
    session = requests.Session()
    session.verify = False
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
    }

    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime("%Y-%m-%d")
    cutoff = today - timedelta(days=90)
    
    ce_year = datetime.now().year
    roc_year = str(ce_year - 1911)

    found_codes = set()

    for code, name in tw_watchlist.items():
        try:
            resp = session.post(
                MOPS_REDIRECT_URL,
                json={
                    "apiName": "ajax_t05st01",
                    "parameters": {
                        "encodeURIComponent": 1,
                        "step": 1,
                        "firstin": 1,
                        "off": 1,
                        "TYPEK": "all",
                        "year": roc_year,
                        "co_id": code,
                    },
                },
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            url = resp.json()["result"]["url"]

            resp2 = session.get(url, timeout=20)
            resp2.raise_for_status()
            
            html = resp2.text
            html_clean = re.sub(r'\s+', ' ', html)
            rows_data = re.findall(r"<tr[^>]*>(.*?)</tr>", html_clean)
            has_event = False
            for row_html in rows_data:
                # 篩選主旨包含股利相關字眼的
                if "董事會決議" in row_html and ("股利" in row_html or "盈餘" in row_html or "分派" in row_html):
                    cols = re.findall(r"<td[^>]*>(.*?)</td>", row_html)
                    if len(cols) < 5:
                        continue

                    subject = re.sub(r'<[^>]+>', '', cols[4]).replace("&nbsp;", "").strip()

                    # 排除代子公司公告的事件
                    # 通常子公司公告會以「代」開頭，或是包含「子公司」關鍵字
                    if "子公司" in subject or subject.startswith("代"):
                        continue

                    pub_date_str = cols[2].replace("&nbsp;", "").strip()

                    try:
                        y, m, d = pub_date_str.split("/")
                        pub_date = datetime(int(y) + 1911, int(m), int(d))
                        if pub_date < cutoff:
                            continue
                        
                        date_str = pub_date.strftime("%Y-%m-%d")
                        results.append([
                            "股利宣告", "台股", f"{name}({code}) 董事會決議股利", 
                            date_str, date_str,
                            f"{name}（{code}）董事會決議股利分派：{subject}",
                            f"https://mops.twse.com.tw/mops/web/t05st01?step=1&co_id={code}&year={roc_year}&month=all&TYPEK=all", "",
                        ])
                        has_event = True
                    except:
                        pass
            
            if has_event:
                found_codes.add(code)
            
            time.sleep(0.3)
            
        except Exception as e:
            print(f"  MOPS {code} {name} 抓取失敗: {e}")

    # 針對沒有事件的公司補齊 "尚未公告股息"
    for code, name in tw_watchlist.items():
        if code not in found_codes:
            results.append([
                "股利宣告", "台股", f"{name}({code}) 尚未公告股息", 
                today_str, today_str,
                f"該公司於 {roc_year} 年尚未有董事會決議發放股利之最新重大訊息",
                f"https://mops.twse.com.tw/mops/web/t05st01?step=1&co_id={code}&year={roc_year}&month=all&TYPEK=all", "",
            ])

    return results

def fetch_us_dividends() -> list[list]:
    """從 yfinance 抓取美股股利宣告事件。"""
    us_watchlist = _load_us_watchlist()
    results = []
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime("%Y-%m-%d")
    cutoff = today - timedelta(days=60)

    found_symbols = set()

    for symbol, name in us_watchlist.items():
        try:
            ticker = yf.Ticker(symbol)
            cal = ticker.calendar
            if not cal:
                continue
            
            ex_date = cal.get("Ex-Dividend Date")
            if ex_date:
                if hasattr(ex_date, "to_pydatetime"):
                    ex_date = ex_date.to_pydatetime()
                if isinstance(ex_date, str):
                    ex_date = datetime.fromisoformat(ex_date)
                if not isinstance(ex_date, datetime):
                    ex_date = datetime(ex_date.year, ex_date.month, ex_date.day)
                
                ex_date = ex_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
                
                if ex_date >= cutoff:
                    date_str = ex_date.strftime("%Y-%m-%d")
                    info = ticker.info
                    div_rate = info.get("dividendRate", "N/A")
                    results.append([
                        "股利宣告", "美股", f"{name}({symbol}) 宣告股利 {div_rate}", 
                        date_str, date_str,
                        f"{name} ({symbol}) 宣告股利分派，每股預計發放 {div_rate} 股利 (除息日 {date_str})",
                        f"https://finance.yahoo.com/quote/{symbol}/", "",
                    ])
                    found_symbols.add(symbol)
        except Exception:
            pass

    # 針對美股觀察名單補齊
    for symbol, name in us_watchlist.items():
        if symbol not in found_symbols:
            results.append([
                "股利宣告", "美股", f"{name}({symbol}) 尚未公告股息", 
                today_str, today_str,
                f"目前尚未取得該公司之最新股利宣告資訊",
                f"https://finance.yahoo.com/quote/{symbol}/", "",
            ])

    return results

def main():
    print("Fetching Taiwan dividend resolutions (Board Decisions)...")
    tw_events = fetch_tw_dividends()
    print(f"  Total TW events: {len(tw_events)}")

    print("Fetching US dividend announcements...")
    us_events = fetch_us_dividends()
    print(f"  Total US events: {len(us_events)}")

    all_events = tw_events + us_events
    # Sort by date (newest first)
    all_events.sort(key=lambda x: x[3], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(all_events)

    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
