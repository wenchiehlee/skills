"""Fetch upcoming earnings reports (財報) and investor conferences (法說會 / 受邀法說)
for TWSE/TPEX (Taiwan) and major US stocks, and refresh raw_event_upcoming_earnings.csv.

Data sources:
- Taiwan 法說會:  MOPS (公開資訊觀測站)
- Taiwan/US 財報: yfinance
- Watchlists:    StockID_TWSE_TPEX.csv / StockID_TWSE_TPEX_focus.csv (TW),
                  raw_conceptstock_company_metadata.csv (US)

類別 classification:
- 財報    財報公告事件（yfinance 財報日期）
- 法說會  公司自行召開的例行法人說明會（MOPS 日期落在財季結束後 <=50 天）
- 受邀法說 受邀參加的投資論壇/法說會（MOPS 日期落在財季結束後 >50 天，
          代表這不是配合當季財報公布的例行法說會，而是受邀參加的活動）
"""

import csv
import io
import os
import re
import sys
from datetime import datetime, timedelta

import urllib3
import requests
import yfinance as yf
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

OUTPUT_FILE = "raw_event_upcoming_earnings.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]

CATEGORY_EARNINGS = "財報"
CATEGORY_LEGAL_MEETING = "法說會"
CATEGORY_INVITED = "受邀法說"

# 監控的美股清單：從 raw_conceptstock_company_metadata.csv 動態載入
# 來源：wenchiehlee-investment/ConceptStocks
_METADATA_CSV_PATHS = [
    "raw_conceptstock_company_metadata.csv",                   # InvestorConference repo root
    "../ConceptStocks/raw_conceptstock_company_metadata.csv",  # 本機開發 fallback
]

def _load_us_watchlist() -> dict[str, str]:
    """從 raw_conceptstock_company_metadata.csv 載入 {Ticker: 公司名稱}，排除無上市 ticker（'-'）。"""
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
        print(f"  [US_WATCHLIST] Loaded {len(result)} tickers from {path}")
        return result
    print("  [US_WATCHLIST] raw_conceptstock_company_metadata.csv not found, using empty list.")
    return {}


def _load_us_next_fiscal_quarter() -> dict[str, str]:
    """從 raw_conceptstock_company_metadata.csv 的「即將發布」欄位載入
    {Ticker: 'FY2026 Q4'} -- 每家公司自己的真實財年季度命名（與 SEC 申報一致）。

    _quarter_label() 只能從財報公告日期用固定的「約一季前」位移公式反推涵蓋
    季度，對回報時滯較短的公司（例如 DELL/NVDA，財季結束後約 3-4 週即公告，
    短於公式假設的最長 3 個月）會推算錯一整季。metadata 的「即將發布」是
    ConceptStocks 用公司實際 SEC 申報維護的權威值，可直接使用、不必用日期猜。
    """
    for path in _METADATA_CSV_PATHS:
        if not os.path.exists(path):
            continue
        result = {}
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("Ticker", "").strip()
                next_fq = row.get("即將發布", "").strip()
                if ticker and ticker != "-" and next_fq and next_fq != "-":
                    result[ticker] = next_fq
        return result
    return {}

US_WATCHLIST = _load_us_watchlist()
US_NEXT_FISCAL_QUARTER = _load_us_next_fiscal_quarter()

def _market_label_for_symbol(symbol: str) -> str:
    if symbol.endswith(".HK"):
        return "港股"
    if symbol.endswith((".TW", ".TWO")):
        return "台股"
    return "美股"

WATCHLIST_CSV       = "StockID_TWSE_TPEX.csv"        # 完整觀察名單
WATCHLIST_FOCUS_CSV = "StockID_TWSE_TPEX_focus.csv"  # 專注名單


def _load_tw_watchlist(csv_path: str) -> dict[str, str]:
    """從 CSV（代號,名稱）載入台股清單，轉成 {symbol.TW: name} dict。"""
    watchlist: dict[str, str] = {}
    if not os.path.exists(csv_path):
        print(f"  Warning: {csv_path} not found, skipping Taiwan watchlist.")
        return watchlist
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get("代號", "").strip()
            name = row.get("名稱", "").strip()
            if code and code != "0000":   # 跳過指數列
                watchlist[f"{code}.TW"] = name
    return watchlist

MOPS_BASE_URL       = "https://mops.twse.com.tw/mops/#/web/t100sb07_1"
MOPS_REDIRECT_URL   = "https://mops.twse.com.tw/mops/api/redirectToOld"

_QUARTER_RE = re.compile(r'(\d{4})\s+Q([1-4])')
_FISCAL_QUARTER_RE = re.compile(r'FY\d{4}\s+Q[1-4]')
_TICKER_RE = re.compile(r'\(([^()]+)\)')

_QUARTER_END_MONTH_DAY = {"1": (3, 31), "2": (6, 30), "3": (9, 30), "4": (12, 31)}
# 法說會日期落在財季結束後超過此天數，視為受邀參加的投資論壇/法說會而非例行法說會。
INVITED_MEETING_THRESHOLD_DAYS = 50

# 財年與日曆年一致的美股（來自 skill-company-investorconference-ingest 已驗證的清單）。
# raw_conceptstock_company_metadata.csv 的「即將發布」欄位對這些 ticker 常有一整季的落差
# （例如 Alphabet 7 月公布的日曆 Q2 財報，metadata 卻標成 'FY2026 Q1'），
# 需要以財報日期反推的日曆季度覆蓋，而不是直接信任 metadata 的 FY 標籤。
KNOWN_US_CALENDAR_YEAR_EARNINGS = {"AMD", "AMZN", "GOOGL", "INTC", "META", "TSM"}
_FY_QUARTER_RE = re.compile(r'FY(\d{4})\s+Q([1-4])')


def _expected_us_calendar_earnings_quarter(date_str: str) -> tuple[str, str]:
    """依財報公告日期反推日曆季度（美股慣例：報告月份即所屬季度）。"""
    y, mo = int(date_str[:4]), int(date_str[5:7])
    if 1 <= mo <= 3:
        return str(y - 1), "4"
    if 4 <= mo <= 6:
        return str(y), "1"
    if 7 <= mo <= 9:
        return str(y), "2"
    return str(y), "3"


def _resolve_us_quarter_label(symbol: str, date_str: str, metadata_quarter: str | None,
                               fallback: datetime) -> str:
    """決定美股財報事件名稱要用的季度標籤。

    對財年與日曆年一致的已知 ticker（KNOWN_US_CALENDAR_YEAR_EARNINGS），以財報日期反推
    的日曆季度為準，metadata 的 FY 標籤僅供比對；衝突時印出警告並採用日期推算結果，
    與 skill-company-investorconference-ingest README 產生器的 expected_us_calendar_earnings_quarter
    workaround 保持一致。其餘 ticker 仍優先信任 metadata 的「即將發布」欄位。
    """
    display = symbol.replace(".TW", "").replace(".TWO", "").upper()
    if display in KNOWN_US_CALENDAR_YEAR_EARNINGS:
        date_year, date_q = _expected_us_calendar_earnings_quarter(date_str)
        m = _FY_QUARTER_RE.match(metadata_quarter) if metadata_quarter else None
        if m and (m.group(1), m.group(2)) != (date_year, date_q):
            print(
                f"  [QUARTER FIX] {symbol}: metadata {metadata_quarter} 與財報日期 {date_str} "
                f"({date_year} Q{date_q}) 不符，改用日期推算的日曆季度。"
            )
        return f"{date_year} Q{date_q}"
    return metadata_quarter or _quarter_label(fallback)


def _quarter_label(event_date: datetime) -> str:
    """從事件日期推算季度標籤，例如 '2026 Q1'。
    法說會慣例：
      1–3 月 → 前一年 Q4
      4–6 月 → 當年 Q1
      7–9 月 → 當年 Q2
      10–12 月 → 當年 Q3
    """
    m = event_date.month
    if m <= 3:
        return f"{event_date.year - 1} Q4"
    elif m <= 6:
        return f"{event_date.year} Q1"
    elif m <= 9:
        return f"{event_date.year} Q2"
    else:
        return f"{event_date.year} Q3"


def _classify_legal_meeting_category(event_name: str, date_str: str) -> str:
    """判斷法說會事件應歸類為 '法說會'（例行）或 '受邀法說'（受邀論壇/法說會）。

    Heuristic：事件名稱含 'YYYY Qn'，若事件日期晚於該財季結束日超過
    INVITED_MEETING_THRESHOLD_DAYS 天，代表這不是配合當季財報公布的例行法說會，
    而是受邀參加的投資論壇/法說會。與 skill-company-investorconference-ingest 的
    README 產生器（is_invited heuristic）採用同一規則，維持分類一致。
    """
    m = _QUARTER_RE.search(event_name)
    if not m:
        return CATEGORY_LEGAL_MEETING
    year_str, q_str = m.group(1), m.group(2)
    month_day = _QUARTER_END_MONTH_DAY.get(q_str)
    if not month_day:
        return CATEGORY_LEGAL_MEETING
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        q_end = datetime(int(year_str), *month_day)
        if (event_date - q_end).days > INVITED_MEETING_THRESHOLD_DAYS:
            return CATEGORY_INVITED
    except Exception:
        pass
    return CATEGORY_LEGAL_MEETING


def _normalize_category(row: list) -> list:
    """將既有 CSV 資料列的 類別 正規化為 財報/法說會/受邀法說 三類之一。

    對財報列直接改名；對台股法說會/受邀法說列則依目前儲存的日期重新分類，讓每次寫檔都會
    自我修正（例如日期更新後，例行/受邀分類也隨之更新）。美股法說會列一律固定為 法說會 --
    它是從同一天的 財報 列衍生出來的（見 _derive_us_call_rows），50 天門檻的日期推算不適用：
    美股「即將發布」欄位的 FY 財季標籤不見得對齊日曆季末（例如 Alphabet），套用會誤判受邀法說。
    """
    if len(row) < 4:
        return row
    if row[0] in (CATEGORY_EARNINGS, "財報公告"):
        row[0] = CATEGORY_EARNINGS
    elif row[0] in (CATEGORY_LEGAL_MEETING, CATEGORY_INVITED):
        if len(row) > 1 and row[1] == "台股":
            row[0] = _classify_legal_meeting_category(row[2], row[3])
        else:
            row[0] = CATEGORY_LEGAL_MEETING
    return row


def _normalize_fashuohui_name(event_name: str, date_str: str, category: str) -> str:
    """確保法說會事件名稱包含季度，例如 '台積電(2330) 2026 Q1 法說會'。
    若已含 'YYYY Qn' 則直接回傳；否則根據日期插入季度。
    """
    if category not in (CATEGORY_LEGAL_MEETING, CATEGORY_INVITED):
        return event_name
    if _QUARTER_RE.search(event_name):
        return event_name  # 已包含季度，不重複加
    suffix = " 法說會"
    if not event_name.endswith(suffix):
        return event_name
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        quarter = _quarter_label(event_date)
        base = event_name[: -len(suffix)]
        return f"{base} {quarter} 法說會"
    except Exception:
        return event_name


def _normalize_earnings_name(event_name: str, date_str: str, category: str) -> str:
    """確保財報公告事件名稱包含季度，例如 'Apple Inc.(AAPL) 2026 Q1 財報'。
    若已含 'YYYY Qn' 則直接回傳；否則根據日期插入季度。
    季度推算規則（與法說會相同）：
      1–3 月 → 前一年 Q4、4–6 月 → 當年 Q1、7–9 月 → 當年 Q2、10–12 月 → 當年 Q3
    """
    if category != CATEGORY_EARNINGS:
        return event_name
    if _QUARTER_RE.search(event_name):
        return event_name  # 已包含季度，不重複加
    suffix = " 財報"
    if not event_name.endswith(suffix):
        return event_name
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        quarter = _quarter_label(event_date)
        base = event_name[: -len(suffix)]
        return f"{base} {quarter} 財報"
    except Exception:
        return event_name


def _extract_event_ticker(event_name: str) -> str | None:
    """Return the ticker/code from the final parenthesized token in an event name."""
    matches = _TICKER_RE.findall(event_name)
    if not matches:
        return None
    ticker = matches[-1].strip()
    return ticker or None


def _is_fiscal_quarter_name(event_name: str) -> bool:
    return bool(_FISCAL_QUARTER_RE.search(event_name))


def _earnings_row_score(row: list) -> tuple[int, int, int, int]:
    """Higher score wins when duplicate earnings rows describe the same event.

    FY-prefixed labels are normally preferred (they trace back to metadata sourced from
    real SEC filings). But for KNOWN_US_CALENDAR_YEAR_EARNINGS tickers that preference is
    inverted: _resolve_us_quarter_label already establishes the plain 'YYYY Qn' label as
    authoritative for them (their metadata FY label can be off by a quarter), so a plain
    label must win here too or dedup keeps the wrong duplicate.
    """
    name = row[2] if len(row) > 2 else ""
    ticker = _extract_event_ticker(name)
    preferred_company = US_WATCHLIST.get(ticker, "") if ticker else ""
    has_preferred_company = int(bool(preferred_company and name.startswith(f"{preferred_company}(")))
    is_fy_name = _is_fiscal_quarter_name(name)
    if ticker and ticker.upper() in KNOWN_US_CALENDAR_YEAR_EARNINGS:
        prefers_fy_label = not is_fy_name
    else:
        prefers_fy_label = is_fy_name
    return (
        int(prefers_fy_label),
        has_preferred_company,
        len(row[5]) if len(row) > 5 else 0,
        len(name),
    )


def _merge_earnings_duplicate_rows(preferred: list, duplicate: list) -> list:
    """Merge two same-company earnings rows, keeping the better label and a full date range."""
    if _earnings_row_score(duplicate) > _earnings_row_score(preferred):
        preferred, duplicate = duplicate, preferred

    dates = [d for d in [preferred[3], preferred[4], duplicate[3], duplicate[4]] if d]
    if dates:
        preferred[3] = min(dates)
        preferred[4] = max(dates)

    return preferred


def _dedupe_nearby_earnings_events(rows: list[list]) -> list[list]:
    """Collapse duplicate 財報 rows for the same ticker on the same/next day.

    yfinance may emit a calendar-quarter event while an existing/manual row already has
    the correct fiscal-quarter label. Treat same ticker + market + category within one
    day as the same earnings event and keep the more specific row.
    """
    grouped: dict[tuple[str, str, str], list[list]] = {}
    passthrough: list[list] = []

    for row in rows:
        if len(row) < 4 or row[0] != CATEGORY_EARNINGS:
            passthrough.append(row)
            continue
        ticker = _extract_event_ticker(row[2])
        if not ticker:
            passthrough.append(row)
            continue
        grouped.setdefault((row[0], row[1], ticker), []).append(row)

    deduped = passthrough[:]
    removed = 0

    for group_rows in grouped.values():
        parsed: list[tuple[datetime, list]] = []
        unparsed: list[list] = []
        for row in group_rows:
            try:
                parsed.append((datetime.strptime(row[3], "%Y-%m-%d"), row))
            except Exception:
                unparsed.append(row)

        parsed.sort(key=lambda item: item[0])
        clusters: list[list[list]] = []
        for dt, row in parsed:
            if not clusters:
                clusters.append([row])
                continue
            last_date = datetime.strptime(clusters[-1][-1][3], "%Y-%m-%d")
            if abs((dt - last_date).days) <= 1:
                clusters[-1].append(row)
            else:
                clusters.append([row])

        for cluster in clusters:
            merged = cluster[0]
            for row in cluster[1:]:
                merged = _merge_earnings_duplicate_rows(merged, row)
                removed += 1
            deduped.append(merged)
        deduped.extend(unparsed)

    if removed:
        print(f"  [DEDUP] 合併 {removed} 筆同 ticker、日期相近的財報重複事件")

    return deduped


def _remove_orphan_us_call_rows(rows: list[list]) -> list[list]:
    """移除美股法說會孤兒列 -- 其對應的來源財報列已不存在（例如被 _dedupe_nearby_earnings_events
    合併/改名後遺留下來的舊名稱）。美股法說會是從財報日期合成的（見 _derive_us_call_rows 的
    限制說明：這是簡化假設，非保證同日），沒有獨立於來源財報列的存在意義，來源財報列消失
    後就該一併移除，而不是留下指向錯誤事件的殘影。
    """
    earnings_names = {
        r[2].strip() for r in rows if len(r) > 2 and r[0] == CATEGORY_EARNINGS and r[1] == "美股"
    }
    kept = []
    removed = 0
    for r in rows:
        if (len(r) > 2 and r[0] == CATEGORY_LEGAL_MEETING and r[1] == "美股"
                and r[2].strip().endswith(" 法說會")):
            earnings_name = r[2].strip()[: -len(" 法說會")] + " 財報"
            if earnings_name not in earnings_names:
                print(f"  [PURGE] {r[2].strip()} 找不到對應財報列，移除孤兒法說會")
                removed += 1
                continue
        kept.append(r)
    if removed:
        print(f"  [PURGE] 共移除 {removed} 筆孤兒法說會事件")
    return kept


def _date_range_30() -> tuple[datetime, datetime]:
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=30), today + timedelta(days=60)


# ── Taiwan 法說會 (MOPS) ─────────────────────────────────────────────────────

def _parse_mops_company_html(html: str, code: str, name: str,
                              start: datetime, end: datetime) -> list[list]:
    """從單一公司 ajax_t100sb07_1 HTML 擷取落在日期範圍內的法說會事件。"""
    rows = []
    # 找所有 ROC 日期（格式 YYY/MM/DD），出現在「召開法人說明會日期」附近
    date_pattern = re.compile(r"(\d{3}/\d{2}/\d{2})")
    for m in date_pattern.finditer(html):
        date_roc = m.group(1)
        try:
            y, mo, d = date_roc.split("/")
            event_date = datetime(int(y) + 1911, int(mo), int(d))
        except ValueError:
            continue
        if not (start <= event_date <= end):
            continue
        date_str = event_date.strftime("%Y-%m-%d")
        quarter = _quarter_label(event_date)
        event_name = f"{name}({code}) {quarter} 法說會"
        category = _classify_legal_meeting_category(event_name, date_str)
        rows.append([
            category, "台股", event_name, date_str, date_str,
            f"{name}（{code}）舉辦法人說明會",
            "https://mops.twse.com.tw/mops/#/web/t100sb07_1", "",
        ])
    # 同一公司同一天只取一筆
    seen = set()
    deduped = []
    for r in rows:
        key = (r[2], r[3])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def fetch_tw_legal_meetings(start: datetime, end: datetime) -> list[list]:
    """從 MOPS 抓取未來 30 天的台股法說會（focus watchlist）。

    流程：POST 新版 MOPS API 取得加密 URL → GET 該 URL 取得 HTML → 解析。
    對 focus watchlist 中每家公司逐一查詢。
    """
    tw_watchlist = _load_tw_watchlist(WATCHLIST_FOCUS_CSV)
    if not tw_watchlist:
        print(f"        Warning: {WATCHLIST_FOCUS_CSV} empty or not found.")
        return []

    results = []
    session = requests.Session()
    session.verify = False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Origin": "https://mops.twse.com.tw",
        "Referer": "https://mops.twse.com.tw/mops/",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }
    try:
        session.get("https://mops.twse.com.tw/mops/", headers=headers, timeout=15)
    except Exception:
        pass

    for symbol, name in tw_watchlist.items():
        code = symbol.replace(".TW", "").replace(".TWO", "")
        try:
            resp = session.post(
                MOPS_REDIRECT_URL,
                json={
                    "apiName": "ajax_t100sb07_1",
                    "parameters": {
                        "co_id": code,
                        "encodeURIComponent": 1,
                        "step": 1,
                        "firstin": 1,
                        "off": 1,
                        "TYPEK": "all",
                    },
                },
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            url = resp.json()["result"]["url"]

            resp2 = session.get(url, timeout=20)
            resp2.raise_for_status()
            found = _parse_mops_company_html(resp2.text, code, name, start, end)
            if found:
                print(f"        {code} {name}: {len(found)} 法說會")
            results.extend(found)
        except Exception as e:
            print(f"  MOPS {code} {name} 抓取失敗: {e}")

    return results


# ── US / TW 財報 (yfinance) ──────────────────────────────────────────────────

def _extract_earnings_dates(symbol: str, company: str, market: str,
                             start: datetime, end: datetime) -> list[list]:
    """共用：從 yfinance calendar 抽出落在範圍內的財報日期。"""
    rows = []
    ticker = yf.Ticker(symbol)
    cal = ticker.calendar
    if cal is None:
        return rows

    dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
    if not isinstance(dates, list):
        dates = [dates]

    for dt in dates:
        if dt is None:
            continue
        if hasattr(dt, "to_pydatetime"):
            dt = dt.to_pydatetime()
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if not isinstance(dt, datetime):
            dt = datetime(dt.year, dt.month, dt.day)
        else:
            try:
                dt = dt.replace(tzinfo=None)
            except TypeError:
                dt = datetime(dt.year, dt.month, dt.day)
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)

        # No upper bound: yfinance's calendar only ever returns the ticker's single next
        # confirmed earnings date, so this always reconciles the CSV against reality even
        # when that date has drifted past `end` (e.g. rescheduled further out since the
        # last run). Bounding by `end` here left stale/wrong dates unrefreshed indefinitely
        # whenever a company's next report fell beyond the +60d window.
        if dt >= start:
            date_str = dt.strftime("%Y-%m-%d")
            display = symbol.replace(".TW", "").replace(".TWO", "")
            # Prefer the company's own real fiscal-quarter label (ConceptStocks
            # metadata, sourced from actual SEC filings) over the date-shift
            # heuristic, which assumes a roughly one-quarter reporting lag and
            # mislabels companies that report sooner after quarter-end (e.g.
            # DELL/NVDA report ~3-4 weeks post quarter-end, not up to 3 months).
            # For known calendar-year reporters, the metadata FY label itself can be
            # off by a quarter -- _resolve_us_quarter_label overrides it in that case.
            if market == "美股":
                quarter = _resolve_us_quarter_label(symbol, date_str, US_NEXT_FISCAL_QUARTER.get(symbol), dt)
            else:
                quarter = _quarter_label(dt)
            rows.append([
                CATEGORY_EARNINGS, market,
                f"{company}({display}) {quarter} 財報",
                date_str, date_str,
                f"{company} 發布季度財報",
                f"https://finance.yahoo.com/quote/{symbol}/financials/",
                f"https://finance.yahoo.com/calendar/earnings?symbol={symbol}",
            ])
    return rows


def fetch_us_earnings(start: datetime, end: datetime) -> list[list]:
    """使用 yfinance 抓取非台股觀察清單的財報日期（未來 30 天）。"""
    results = []
    for symbol, company in US_WATCHLIST.items():
        try:
            results.extend(_extract_earnings_dates(symbol, company, _market_label_for_symbol(symbol), start, end))
        except Exception as e:
            print(f"  {symbol} 財報日期抓取失敗: {e}")
    return results


def _derive_us_call_rows(earnings_rows: list[list]) -> list[list]:
    """以財報日期合成對應的法說會事件，讓美股公司也能像台股一樣把「財報」數字發布與
    「法說會」法人說明會拆成兩個獨立事件。

    這是簡化假設，不是保證：多數美股大型公司確實在財報發布當天同步舉行法說會，
    但並非全部如此（例如少數公司隔天才開電話會議，或發布時間接近美東午夜跨日）。
    yfinance 的 calendar['Earnings Date'] 本身也只是日期、常是預估值，並非權威的
    已確認發布日期。目前沒有免費、可靠的來源能取得獨立於財報發布日的法說會時間，
    這個同日假設是目前最好的替代做法，但個別事件仍可能因此有一天以內的誤差。
    """
    rows = []
    for row in earnings_rows:
        if len(row) < 8 or row[0] != CATEGORY_EARNINGS or row[1] != "美股":
            continue
        name = row[2]
        suffix = " 財報"
        if not name.endswith(suffix):
            continue
        call_name = name[: -len(suffix)] + " 法說會"
        date_str = row[3]
        # Derived same-day from its own 財報 row, so this is always the routine call for
        # that quarter's report -- never an invited/forum event. Skip the day-offset
        # heuristic entirely: it compares against the US "FY" fiscal-quarter label, which
        # doesn't align to calendar quarter-end math for calendar-year reporters (e.g.
        # Alphabet), and would misclassify a same-day call as 受邀法說.
        category = CATEGORY_LEGAL_MEETING
        ticker = _extract_event_ticker(name)
        company = US_WATCHLIST.get(ticker, "") if ticker else ""
        remark = f"{company} 舉行法人說明會" if company else "舉行法人說明會"
        rows.append([
            category, row[1], call_name, date_str, row[4], remark,
            row[6], row[7],
        ])
    return rows


def _extract_earnings_dates_quiet(symbol: str, company: str, market: str,
                                   start: datetime, end: datetime) -> list[list]:
    """Same as _extract_earnings_dates but suppresses yfinance's 404 stderr noise."""
    buf = io.StringIO()
    old_stderr, old_stdout = sys.stderr, sys.stdout
    sys.stderr = sys.stdout = buf
    try:
        return _extract_earnings_dates(symbol, company, market, start, end)
    except Exception:
        return []
    finally:
        sys.stderr, sys.stdout = old_stderr, old_stdout


def fetch_tw_earnings(start: datetime, end: datetime) -> list[list]:
    """使用 yfinance 抓取台股財報日期（未來 30 天），從 watchlist CSV 載入。
    自動 fallback .TW → .TWO（TPEX 上櫃股需用 .TWO）。
    """
    tw_watchlist = _load_tw_watchlist(WATCHLIST_CSV)
    print(f"        Loaded {len(tw_watchlist)} stocks from {WATCHLIST_CSV}")
    results = []
    tpex_fallbacks = 0
    for symbol, company in tw_watchlist.items():
        # Try .TW first (suppress noisy 404 warnings)
        rows = _extract_earnings_dates_quiet(symbol, company, "台股", start, end)
        # If empty, retry with .TWO (TPEX/OTC stocks use .TWO on Yahoo Finance)
        if not rows and symbol.endswith(".TW"):
            alt = symbol[:-3] + ".TWO"
            rows = _extract_earnings_dates_quiet(alt, company, "台股", start, end)
            if rows:
                tpex_fallbacks += 1
        results.extend(rows)
    if tpex_fallbacks:
        print(f"        ({tpex_fallbacks} stocks resolved via .TWO fallback)")
    return results


def _purge_stale_future_earnings(existing_by_name: dict, fresh_rows: list[list], today: datetime) -> int:
    """移除同一 ticker 已被本次抓取的最新財報日期取代、但仍留在檔案中的舊筆資料。

    財報事件名稱含季度標籤（例如 'FY2026 Q2 財報'），若新抓到的日期落在不同季度，
    名稱就會不同，merge-by-name 邏輯無法辨識為同一事件、也就不會覆蓋掉舊筆 --
    導致同一 ticker 出現兩筆矛盾的未來財報日期（例如舊資料寫 7 月、新資料寫 10 月）。
    只處理尚未發生（>= today）的財報列，避免刪到 skill-company-investorconference-ingest
    的 --auto-todo 需要用來比對「已發生但尚未收錄」的歷史紀錄。同時移除該筆對應的
    衍生法說會事件（見 _derive_us_call_rows），避免留下指向錯誤日期的孤兒法說會。
    """
    fresh_names_by_market_ticker: dict[tuple, str] = {}
    fresh_names_by_ticker: dict[str, str] = {}
    for row in fresh_rows:
        if row[0] != CATEGORY_EARNINGS:
            continue
        ticker = _extract_event_ticker(row[2])
        if not ticker:
            continue
        fresh_name = row[2].strip()
        fresh_names_by_market_ticker[(row[1], ticker)] = fresh_name
        fresh_names_by_ticker[ticker] = fresh_name

    removed = 0
    for name in list(existing_by_name.keys()):
        row = existing_by_name[name]
        if row[0] != CATEGORY_EARNINGS:
            continue
        ticker = _extract_event_ticker(row[2])
        if not ticker:
            continue
        fresh_name = fresh_names_by_market_ticker.get((row[1], ticker)) or fresh_names_by_ticker.get(ticker)
        if not fresh_name or fresh_name == name:
            continue
        try:
            row_date = datetime.strptime(row[3], "%Y-%m-%d")
        except Exception:
            continue
        if row_date < today:
            continue  # 保留歷史紀錄供 --auto-todo 使用
        print(f"  [PURGE] {name} ({row[3]}) 已被 {fresh_name} 取代，移除過期財報事件")
        del existing_by_name[name]
        call_name = name[:-len(" 財報")] + " 法說會" if name.endswith(" 財報") else None
        if call_name and call_name in existing_by_name:
            del existing_by_name[call_name]
            print(f"  [PURGE] {call_name} 一併移除（過期財報的衍生法說會）")
        removed += 1

    return removed


# ── CSV helpers ──────────────────────────────────────────────────────────────

def _sync_tw_earnings_dates_from_mops(all_rows: list[list]) -> list[list]:
    """Post-processing: for Taiwan 財報, if a matching MOPS 法說會/受邀法說 date exists
    for the same company+quarter and the MOPS date is earlier, use MOPS date.

    Background: yfinance often returns inaccurate estimated dates for Taiwan stocks.
    The MOPS 法說會 date reflects the actual board meeting date (董事會), which is
    also when the financial report is officially released — making it more reliable.
    """
    code_quarter_re = re.compile(r'\((\d{4,5})\)\s+(\d{4}\s+Q[1-4])')

    # Build map {(stock_code, quarter): earliest_mops_date} from 法說會/受邀法說 entries
    mops_dates: dict[tuple, str] = {}
    for row in all_rows:
        if row[0] in (CATEGORY_LEGAL_MEETING, CATEGORY_INVITED) and row[1] == "台股":
            m = code_quarter_re.search(row[2])
            if m:
                key = (m.group(1), m.group(2))
                existing = mops_dates.get(key)
                if existing is None or row[3] < existing:
                    mops_dates[key] = row[3]

    if not mops_dates:
        return all_rows

    updated = 0
    for row in all_rows:
        if row[0] == CATEGORY_EARNINGS and row[1] == "台股":
            m = code_quarter_re.search(row[2])
            if m:
                key = (m.group(1), m.group(2))
                mops_date = mops_dates.get(key)
                if mops_date and mops_date < row[3]:
                    print(f"  [DATE SYNC] {row[2]}: {row[3]} → {mops_date} (從 MOPS 法說會修正)")
                    row[3] = mops_date
                    row[4] = mops_date
                    updated += 1

    if updated:
        print(f"  [DATE SYNC] 共修正 {updated} 筆台股財報日期（MOPS 法說會資料）")

    return all_rows


def save_csv(rows: list[list], output_file: str) -> None:
    """Merge new rows into the CSV, deduplicate by event name, sort by date descending, rewrite.

    Deduplication key is event_name only (not event_name + date), so that corrected dates
    from the current fetch can override stale dates stored in the existing CSV.
    New rows take precedence over existing rows for the same event name.
    Every rewrite also re-normalizes 類別 (財報/法說會/受邀法說) for existing rows, so a
    legacy '財報公告' value or a stale 法說會/受邀法說 classification self-heals over time.
    """
    process_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 讀取現有資料，以事件名稱為 key 建立 lookup
    existing_by_name: dict[str, list] = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue  # skip header
                    if len(row) >= 4:
                        row = _normalize_category(row)
                        row[2] = _normalize_fashuohui_name(row[2], row[3], row[0])
                        row[2] = _normalize_earnings_name(row[2], row[3], row[0])
                        while len(row) < len(CSV_HEADERS):
                            row.append(process_timestamp)
                        row[-2] = process_timestamp
                        row[-1] = process_timestamp
                        name = row[2].strip()
                        if name not in existing_by_name:
                            existing_by_name[name] = row
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    # 2. 新資料覆蓋同名既有資料（允許日期與類別更新），否則新增。
    #    保護已經發生過（開始日期 < today）的既有資料列不被新抓到的未來日期覆蓋 --
    #    這種情況代表同一名稱被重複使用在不同的實際事件上（例如季度標籤沒有跟著更新），
    #    直接覆蓋會抹除已經真實發生過的歷史事件（ingest_from_todo 需要這筆歷史紀錄）。
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    added = updated_dates = 0
    for row in rows:
        if len(row) < 4:
            continue
        row = _normalize_category(row)
        row[2] = _normalize_fashuohui_name(row[2], row[3], row[0])
        row[2] = _normalize_earnings_name(row[2], row[3], row[0])
        name = row[2].strip()
        while len(row) < len(CSV_HEADERS):
            row.append(process_timestamp)
        row[-2] = process_timestamp
        row[-1] = process_timestamp
        if name in existing_by_name:
            existing_row = existing_by_name[name]
            old_date = existing_row[3]
            new_date = row[3].strip()
            try:
                old_dt = datetime.strptime(old_date, "%Y-%m-%d")
            except Exception:
                old_dt = None
            if old_dt and old_dt < today and new_date != old_date:
                print(
                    f"  [SKIP] {name}: 既有日期 {old_date} 已經發生過，"
                    f"不覆蓋為新抓取的 {new_date}（同名稱可能對應到下一個實際事件，"
                    "季度標籤需要修正）"
                )
                continue
            existing_row[0] = row[0]
            if old_date != new_date:
                print(f"  [DATE UPDATE] {name}: {old_date} → {new_date}")
                existing_row[3] = new_date
                existing_row[4] = row[4].strip()
                updated_dates += 1
        else:
            existing_by_name[name] = row
            added += 1

    # 3. 移除同一 ticker 已被本次抓取的新財報日期取代、但因季度標籤不同而未被步驟 2
    #    覆蓋掉的過期未來財報列（連同其衍生法說會）。
    purged = _purge_stale_future_earnings(existing_by_name, rows, today)

    # 4. 為每一筆美股 財報（含既有、未在本次重新抓取到的舊資料）補上/同步對應法說會事件。
    #    放在合併與清理過期資料之後，確保沒有被本次抓取覆蓋到的既有 財報 列也能補齊法說會。
    #    既有的衍生法說會列一律以來源財報的最新日期覆蓋 -- 法說會日期本身不是抓取來的獨立
    #    資料，只是財報日期的鏡射，財報日期更新（例如被 [DATE UPDATE] 修正）後若不同步覆蓋，
    #    法說會列會停在舊日期形成孤兒資料。
    derived_calls = derived_syncs = 0
    for call in _derive_us_call_rows(list(existing_by_name.values())):
        name = call[2].strip()
        while len(call) < len(CSV_HEADERS):
            call.append(process_timestamp)
        call[-2] = process_timestamp
        call[-1] = process_timestamp
        if name not in existing_by_name:
            existing_by_name[name] = call
            derived_calls += 1
        else:
            existing_row = existing_by_name[name]
            if existing_row[3] != call[3] or existing_row[4] != call[4]:
                existing_row[3], existing_row[4] = call[3], call[4]
                derived_syncs += 1
            existing_row[-2] = process_timestamp
            existing_row[-1] = process_timestamp
    if derived_calls:
        print(f"  [DERIVE] 補上 {derived_calls} 筆美股法說會事件（同財報發布日）")
        added += derived_calls
    if derived_syncs:
        print(f"  [DERIVE] 同步 {derived_syncs} 筆美股法說會日期（隨財報日期更新）")
        updated_dates += derived_syncs

    merged = list(existing_by_name.values())
    merged = _dedupe_nearby_earnings_events(merged)
    merged = _remove_orphan_us_call_rows(merged)

    # 5. 日期降冪排序（新 → 舊）
    merged.sort(key=lambda r: r[3], reverse=True)

    # 6. 整檔重寫
    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(merged)

    total = len(merged)
    parts = []
    if added:
        parts.append(f"新增 {added} 筆")
    if updated_dates:
        parts.append(f"更新日期 {updated_dates} 筆")
    if purged:
        parts.append(f"移除過期 {purged} 筆")
    if parts:
        print(f"{' / '.join(parts)} → CSV 共 {total} 筆。")
    else:
        print(f"無變更。CSV 共 {total} 筆。")


# ── main ─────────────────────────────────────────────────────────────────────

def generate_upcoming_earnings() -> None:
    start, end = _date_range_30()
    print(f"Fetching upcoming 財報/法說會/受邀法說 events ({start.date()} ~ {end.date()})...")

    all_rows: list[list] = []

    print("  [1/4] Fetching Taiwan 法說會 from MOPS...")
    tw_rows = fetch_tw_legal_meetings(start, end)
    print(f"        Found {len(tw_rows)} Taiwan 法說會/受邀法說 events.")
    all_rows.extend(tw_rows)

    print("  [2/4] Fetching US earnings from yfinance...")
    us_rows = fetch_us_earnings(start, end)
    print(f"        Found {len(us_rows)} US earnings events.")
    all_rows.extend(us_rows)

    print("  [3/4] Fetching Taiwan earnings from yfinance...")
    tw_earn_rows = fetch_tw_earnings(start, end)
    print(f"        Found {len(tw_earn_rows)} Taiwan earnings events.")
    all_rows.extend(tw_earn_rows)

    print("  [4/4] Syncing Taiwan 財報 dates from MOPS 法說會 data...")
    all_rows = _sync_tw_earnings_dates_from_mops(all_rows)

    save_csv(all_rows, OUTPUT_FILE)

    if all_rows:
        print("-" * 50)
        for row in all_rows[:5]:
            print(f"  {row[3]}  {row[0]}/{row[1]}  {row[2]}")
        if len(all_rows) > 5:
            print(f"  ... and {len(all_rows) - 5} more")
        print("-" * 50)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (default: today-30d)")
    parser.add_argument("--end",   type=str, help="End date YYYY-MM-DD (default: today+60d)")
    args = parser.parse_args()

    if args.start or args.end:
        _start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else _date_range_30()[0]
        _end   = datetime.strptime(args.end,   "%Y-%m-%d") if args.end   else _date_range_30()[1]
        # Temporarily override _date_range_30 for generate_upcoming_earnings
        _orig = _date_range_30
        def _date_range_30(): return _start, _end  # noqa: E306
        generate_upcoming_earnings()
        _date_range_30 = _orig
    else:
        generate_upcoming_earnings()
