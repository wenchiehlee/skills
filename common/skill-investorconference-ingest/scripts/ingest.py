import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
import shutil
import subprocess
import hashlib
import re
import warnings
import json
import datetime
import requests
from pathlib import Path
from urllib.parse import urljoin
from audio_storage_bridge import upload_to_gdrive_and_update_manifest, get_audio_link_for_readme

# Suppress InsecureRequestWarning for MOPS (Taiwan gov site SSL quirks on Windows)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Smart Ingestion - Multi-Stock Support
# Version 5.0: standalone script inside InvestorConference repo

# Find repo root dynamically
_curr = Path(__file__).resolve()
INVESTOR_CONFERENCE_REPO = None
for p in _curr.parents:
    if (p / "audio_manifest.json").exists() or (p / ".git").exists():
        INVESTOR_CONFERENCE_REPO = p
        break
if not INVESTOR_CONFERENCE_REPO:
    INVESTOR_CONFERENCE_REPO = _curr.parents[3]

# ── Company Name Lookup ───────────────────────────────────────────────────────
# (stock_id) -> (english_name, chinese_name)
KNOWN_TW_STOCKS = {
    "2330": ("TSMC", "台積電"),
    "2357": ("ASUS", "華碩"),
    "2317": ("Foxconn", "鴻海"),
    "2454": ("MediaTek", "聯發科"),
    "2382": ("Quanta", "廣達"),
    "3711": ("ASE", "日月光投控"),
    "2308": ("Delta Electronics", "台達電"),
    "2412": ("Chunghwa Telecom", "中華電信"),
    "2881": ("Fubon Financial", "富邦金"),
    "1301": ("Formosa Plastics", "台塑"),
    "6505": ("Formosa Petrochemical", "台塑化"),
    "2303": ("United Microelectronics", "聯電"),
    "2886": ("Mega Financial", "兆豐金"),
    "5871": ("CHAILEASE", "中租控股"),
    "2480": ("Stark Technology", "敦陽科"),
    "3231": ("Wistron", "緯創"),
    "3034": ("Novatek", "聯詠"),
    "8299": ("Phison", "群聯"),
    "4938": ("Pegatron", "和碩"),
    "2356": ("Inventec", "英業達"),
}

# Companies that host earnings call MP4 directly on their own IR site
# (stock_id -> IR earnings-call page URL)
# Simple requests-based scraper: looks for /documents/...mp4 links (e.g. STI Liferay portal)
KNOWN_TW_DIRECT_IR = {
    "2480": "https://www.sti.com.tw/web/official/earnings-call",  # Liferay portal, MP4 in /documents/
}

# Quarter-specific direct audio/video URLs. Use these before generic IR/MOPS
# discovery when the official company URL is known and MOPS may return a
# different quarter's latest replay.
KNOWN_TW_DIRECT_AUDIO_BY_QUARTER = {
    ("2317", "2026", "1"): "https://www.youtube.com/watch?v=gz70OTe990s",
    ("2301", "2025", "4"): "https://www.liteon.com/upload/media/video_over_20mb/IR%20conference/4Q25%E5%AE%98%E7%B6%B2%E4%B8%AD%E6%96%87%E5%BD%B1%E7%89%87.mp4",
    ("2458", "2025", "4"): "http://irconference.twse.com.tw/2458_162_20260303_ch.mp4",
}

# JS-rendered IR pages: need Playwright to intercept network or scan DOM for video URLs
# (stock_id -> IR earnings-call page URL)
KNOWN_TW_PLAYWRIGHT_IR = {
    "2382": "https://www.quantatw.com/Quanta/chinese/investment/financials_icp.aspx",  # 廣達 - JS-rendered
    "8299": "https://www.phison.com/zh-tw/investor-relations/shareholder-services/investor-meeting-information",  # 群聯 - YouTube links in DOM
    "2454": "https://ottlive.hinet.net/webapp/mediatek/watch?v=3556",  # 聯發科 2025Q4 - ottlive HLS m3u8 intercept
    "2308": "https://www.deltaww.com/zh-TW/investors/analyst-meeting", # 台達電 - ccdntech.com HLS, video URL in HTML source
}

# Quarter-specific replay pages for companies whose webcast URLs change each quarter.
# Keys use (stock_id, year, quarter).
KNOWN_TW_PLAYWRIGHT_IR_BY_QUARTER = {
    ("2330", "2025", "1"): "https://ottlive.hinet.net/webapp/tsmc/watch?v=1981",
    ("2330", "2025", "2"): "https://ottlive.hinet.net/webapp/tsmc/watch?v=2394",
    ("2330", "2025", "3"): "https://ottlive.hinet.net/webapp/tsmc/watch?v=2503",
    ("2330", "2025", "4"): "https://ottlive.hinet.net/webapp/tsmc/watch?v=2766",
    ("2330", "2026", "1"): "https://ottlive.hinet.net/webapp/tsmc/watch?v=3646", # 2026Q1 確切連結
    ("2454", "2025", "1"): "https://ottlive.hinet.net/webapp/mediatek/watch?v=2088",
    ("2454", "2025", "2"): "https://ottlive.hinet.net/webapp/mediatek/watch?v=2413",
    ("2454", "2025", "3"): "https://ottlive.hinet.net/webapp/mediatek/watch?v=2531",
    ("2454", "2025", "4"): "https://ottlive.hinet.net/webapp/mediatek/watch?v=3556",
    ("2454", "2026", "1"): "https://ottlive.hinet.net/webapp/mediatek/watch?v=3635",
    ("3034", "2025", "3"): "https://www.novatek.com.tw/upload/website/_2025Q3_25110708_904.html",
    ("3034", "2025", "4"): "https://www.novatek.com.tw/upload/website/_2025Q4_26020909_911.html",
    ("3045", "2026", "1"): "http://www.zucast.com/webcast/YZRGwetH",  # 台灣大 2026Q1 法說會 2026-05-13 (Zucast 需註冊; 音檔為 S3 直連 mp3, 已下載至 3045_2026_q1.m4a)
}

# IR portal URLs for Taiwan stocks that host webcast on their own IR sites
# (stock_id -> IR page URL)
KNOWN_TW_IR = {
    "2357": "https://www.asus.com/event/Investor/C/",  # ASUS - uses webcast-eqs.com
    "3034": "https://www.novatek.com.tw/en-global/Download/ir_event/Index/analyst_meeting", # Novatek IR
}

# Per-company PDF attachment URL templates (optional, keyed by stock_id)
# Use {year} and {quarter} placeholders
KNOWN_PDF_ATTACHMENTS = {
    "2357": [
        ("ir", "https://www.asus.com/event/Investor/Content/attachment/{year}Q{quarter}%20IR(Chinese).pdf"),
        ("qa", "https://www.asus.com/event/Investor/Content/attachment/{year}Q{quarter}_QA(Chinese).pdf"),
    ],
    "2395": [
        ("ir_en", "https://advcloudfiles.advantech.com/investor/Events/Advantech_{quarter}Q_{year}_Investors_Meeting_English.pdf"),
    ],
}

# IR portal URLs for US stocks (ticker -> IR URL)
KNOWN_US_IR = {
    "NVDA": "https://investor.nvidia.com/events-and-presentations/events/default.aspx",
    "AAPL": "https://investor.apple.com/investor-relations/events-and-presentations/",
    "MSFT": "https://www.microsoft.com/en-us/Investor/events/FY-2024/",
    "TSLA": "https://ir.tesla.com/events-and-presentations/events",
    "AMD":  "https://ir.amd.com/events-and-presentations",
    "QCOM": "https://investor.qualcomm.com/events-presentations/events",
}

# Quarter-specific direct audio URLs for US stocks (choruscall VOD / YouTube / etc.)
# Keys use (ticker, year, quarter) matching expected_quarter() convention.
KNOWN_US_DIRECT_BY_QUARTER = {
    ("QCOM", "2025", "4"): "https://vodchoruscall.akamaized.net/07452/qualcomm/qualcomm260204.mp4",  # Q1FY26 call 2026-02-04
    ("QCOM", "2026", "1"): "https://vodchoruscall.akamaized.net/07452/qualcomm/qualcomm260429.mp4",  # Q2FY26 call 2026-04-29
}

# Official webcast replay pages when no direct downloadable audio URL is available.
KNOWN_US_WEBCASTS_BY_QUARTER = {
    ("DELL", "2026", "1"): "https://event.webcasts.com/starthere.jsp?ei=1747660&tp_key=82c5169428",  # Q1FY27 results call 2026-05-28
}

# Quarter-specific Yahoo Finance earnings transcript pages.
# These are browser-rendered pages and require Playwright/Chromium for extraction.
KNOWN_YAHOO_TRANSCRIPTS_BY_QUARTER = {
    ("2454", "2025", "4"): "https://finance.yahoo.com/quote/2454.TW/earnings/2454.TW-Q4-2025-earnings_call-404281.html",
}

# US stock display names (ticker -> (english_name, chinese_name))
KNOWN_US_STOCKS = {
    "NVDA": ("NVIDIA",     "輝達"),
    "AAPL": ("Apple",      "蘋果"),
    "MSFT": ("Microsoft",  "微軟"),
    "TSLA": ("Tesla",      "特斯拉"),
    "AMD":  ("AMD",        "超微"),
    "QCOM": ("Qualcomm",   "高通"),
    "DELL": ("Dell Technologies", "戴爾科技"),
    "GOOGL": ("Alphabet Inc.", ""),
}

# Calendar-year US companies where stale Yahoo/CSV FY labels should be sanity-checked
# against the earnings announcement month. Unknown tickers keep CSV/FY labels until
# a company IR or SEC source confirms the quarter.
KNOWN_US_CALENDAR_YEAR_EARNINGS = {
    "AMD",
    "AMZN",
    "GOOGL",
    "INTC",
    "META",
    "TSM",
}

# Fiscal year start month for US stocks whose fiscal year ≠ calendar year.
# e.g. QCOM fiscal year starts October -> FY2026 Q1 = Oct-Dec 2025 (calendar Q4 2025)
KNOWN_US_FISCAL_YEAR_START_MONTH = {
    "QCOM": 10,   # October
    "AAPL": 10,   # October
    "MSFT": 7,    # July
    "NVDA": 2,    # February (FY starts Feb 1)
    "DELL": 2,    # February (FY starts Feb 1)
}


def calendar_to_fiscal(ticker: str, cal_year: str, cal_q: str):
    """Return (fy_year, fy_q) strings for a US stock given its calendar year/quarter.
    Returns (None, None) if no fiscal year mapping is defined for the ticker."""
    start_month = KNOWN_US_FISCAL_YEAR_START_MONTH.get(ticker.upper())
    if start_month is None:
        return None, None
    fy_start_cal_q = (start_month - 1) // 3 + 1  # e.g. Oct(10) -> Q4
    cq = int(cal_q)
    cy = int(cal_year)
    fy_q = (cq - fy_start_cal_q) % 4 + 1
    fy_year = cy + 1 if cq >= fy_start_cal_q else cy
    return str(fy_year), str(fy_q)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def detect_market(stock_id: str) -> str:
    """Detect if stock is Taiwan (numeric) or US (alphabetic)."""
    return "TW" if stock_id.isdigit() else "US"


def get_company_name(stock_id: str) -> tuple:
    """Return (english_name, chinese_name) for a stock ID."""
    if stock_id in KNOWN_TW_STOCKS:
        return KNOWN_TW_STOCKS[stock_id]

    if stock_id.isdigit():
        try:
            resp = requests.get(
                "https://openapi.twse.com.tw/v1/opendata/t187ap03_L", timeout=10,
            )
            for item in resp.json():
                if item.get("公司代號") == stock_id:
                    chi = item.get("公司簡稱", stock_id)
                    return (chi, chi)
        except Exception:
            pass

    return (stock_id, stock_id)


def resolve_tw_playwright_ir_url(stock_id: str, year: str, quarter: str):
    """Return the quarter-specific Playwright IR URL when known, otherwise the stock default."""
    return KNOWN_TW_PLAYWRIGHT_IR_BY_QUARTER.get(
        (stock_id, year, quarter),
        KNOWN_TW_PLAYWRIGHT_IR.get(stock_id),
    )


def discover_mediatek_hinet_page(year: str, quarter: str) -> tuple[str | None, str | None]:
    """
    Discover a MediaTek Hinet watch page for the requested quarter.

    The newer Hinet pages embed the real HLS URL in HTML/JS, so match by the
    stream date first instead of trusting the human-facing title text.

    Returns (watch_page_url, conf_date_yyyymmdd).
    """
    if quarter == "4":
        target_year = str(int(year) + 1)
        month_min, month_max = 1, 4
    elif quarter == "1":
        target_year = year
        month_min, month_max = 4, 6
    elif quarter == "2":
        target_year = year
        month_min, month_max = 7, 9
    else:
        target_year = year
        month_min, month_max = 10, 12

    watch_pages: list[str] = []

    def probe_watch_page(url: str) -> tuple[str | None, str | None]:
        print(f"[MediaTek] Probing watch page: {url}")
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": UA})
            html = resp.text
        except Exception as e:
            print(f"[MediaTek] Probe failed: {e}")
            return None, None

        stream_m = re.search(r'"url":"(https:\/\/.*?playlist\.m3u8)"', html)
        if not stream_m:
            stream_m = re.search(r"(https?://[^\s\"']+playlist\.m3u8)", html, re.I)
        if not stream_m:
            return None, None

        stream_url = stream_m.group(1).replace(r"\/", "/")
        date_m = re.search(r'(\d{8})', stream_url)
        conf_date = date_m.group(1) if date_m else None
        if conf_date:
            y, mo = conf_date[:4], int(conf_date[4:6])
            if y == target_year and month_min <= mo <= month_max:
                print(f"[MediaTek] Matched watch page by stream date: {url}")
                return url, conf_date

        date_m = re.search(r"Time[:：]\s*(\d{4})-(\d{2})-(\d{2})", html, re.I)
        if date_m:
            conf_date = "".join(date_m.groups())
            y, mo = conf_date[:4], int(conf_date[4:6])
            if y == target_year and month_min <= mo <= month_max:
                print(f"[MediaTek] Matched watch page by title time: {url}")
                return url, conf_date

        return None, None

    vod_url = "https://webpage-ott2b.cdn.hinet.net/webpage/vod?contentProvider=mediatek"
    try:
        resp = requests.get(vod_url, timeout=20, headers={"User-Agent": UA})
        html = resp.text
        hrefs = re.findall(
            r"href=[\"']([^\"']*watch\?contentProvider=mediatek[^\"']*v=\d+[^\"']*)[\"']",
            html,
            re.I,
        )
        seen = set()
        for href in hrefs:
            watch_url = urljoin(vod_url, href.replace("&amp;", "&"))
            if watch_url not in seen:
                seen.add(watch_url)
                watch_pages.append(watch_url)
    except Exception as e:
        print(f"[MediaTek] VOD list fetch failed: {e}")

    watch_pages.extend([
        "https://ottlive-ott2b2.cdn.hinet.net/mediatek/index.html",
        "https://webpage-ott2b.cdn.hinet.net/webpage/live?contentProvider=mediatek",
    ])

    for watch_url in watch_pages:
        matched_url, conf_date = probe_watch_page(watch_url)
        if matched_url:
            return matched_url, conf_date

    fallback = KNOWN_TW_PLAYWRIGHT_IR_BY_QUARTER.get(("2454", year, quarter))
    if fallback:
        print(f"[MediaTek] Falling back to pinned watch page: {fallback}")
        return fallback, None

    return KNOWN_TW_PLAYWRIGHT_IR.get("2454"), None


# ── TWSE irconference.twse.com.tw Direct Downloader ──────────────────────────

def scrape_tw_direct_ir(stock_id: str, ir_url: str, year: str, quarter: str) -> tuple:
    """
    Scrape a company IR page that hosts MP4 directly (e.g. STI Liferay portal).
    Looks for /documents/...mp4 links and picks the one matching year+quarter.

    Returns (mp4_url, conf_date_str) where conf_date_str is YYYYMMDD, or (None, None).
    Example: https://www.sti.com.tw/web/official/earnings-call
      -> /documents/36928/73640/敦陽科法人說明會-20260310+0658-1.mp4/...
    Date pattern: YYYYMMDD in filename, match by year+quarter calendar mapping.
    """
    base = re.match(r'(https?://[^/]+)', ir_url).group(1)
    print(f"[Direct-IR] Fetching {ir_url} ...")
    try:
        resp = requests.get(ir_url, headers={"User-Agent": UA}, timeout=15, verify=False)
        html = resp.text.replace("&amp;", "&")

        # Collect all MP4 document links
        mp4_links = re.findall(r'(/documents/[^\s"\'<>&]+\.mp4[^\s"\'<>&]*)', html)
        if not mp4_links:
            print(f"[Direct-IR] No MP4 links found.")
            return None, None

        print(f"[Direct-IR] Found {len(mp4_links)} MP4 link(s).")

        # Quarter -> expected conference month range
        if quarter == "4":
            target_year = str(int(year) + 1)
            month_min, month_max = 1, 4   # Q4 call held Jan–Apr of next year
        else:
            q_end = {"1": 3, "2": 6, "3": 9}[quarter]
            target_year = year
            month_min, month_max = q_end, q_end + 3

        for link in mp4_links:
            m = re.search(r'(\d{8})', link)
            if not m:
                continue
            date_str = m.group(1)
            y, mo = date_str[:4], int(date_str[4:6])
            if y == target_year and month_min <= mo <= month_max:
                full_url = f"{base}{link}"
                print(f"[Direct-IR] Matched: {full_url[:80]}...")
                return full_url, date_str

        # Fallback: first link (most recent)
        m = re.search(r'(\d{8})', mp4_links[0])
        date_str = m.group(1) if m else ""
        full_url = f"{base}{mp4_links[0]}"
        print(f"[Direct-IR] No exact match - using first: {full_url[:80]}...")
        return full_url, date_str

    except Exception as e:
        print(f"[Direct-IR] Failed: {e}")
    return None, None


# ── Taiwan IR Site Scraper ────────────────────────────────────────────────────

def scrape_tw_ir(stock_id: str, ir_url: str, year: str, quarter: str) -> str | None:
    """
    Scrape a Taiwan company's IR page for the earnings call webcast URL.

    ASUS (2357) example:
      IR page  : https://www.asus.com/event/Investor/C/
      HTML link: <a href='https://www.webcast-eqs.com/asus25q4/tc'>2025年第四季法人說明會</a>
      Slug rule: asus{YY}q{Q}  (e.g. asus25q4 for 2025 Q4)
    """
    print(f"[TW-IR] Fetching {ir_url} ...")
    try:
        resp = requests.get(ir_url, timeout=15, headers={"User-Agent": UA})
        html = resp.text

        webcast_urls = re.findall(
            r'https?://(?:www\.|asia\.)?webcast-eqs\.com/[a-zA-Z0-9]+/[a-zA-Z]+',
            html
        )
        if not webcast_urls:
            print(f"[TW-IR] No webcast-eqs.com links found.")
            return None

        print(f"[TW-IR] Found {len(webcast_urls)} webcast link(s).")

        yy = year[-2:]   # "2025" -> "25"
        q  = quarter     # "4"
        slug_re = re.compile(rf'[a-zA-Z]+{re.escape(yy)}q{re.escape(q)}', re.IGNORECASE)

        for url in webcast_urls:
            slug = url.rstrip('/').split('/')[-2]
            if slug_re.match(slug):
                print(f"[TW-IR] Matched: {url}")
                return url

        # Fallback: first link (most recent entry at top of page)
        print(f"[TW-IR] No exact match - using first: {webcast_urls[0]}")
        return webcast_urls[0]

    except Exception as e:
        print(f"[TW-IR] Fetch failed: {e}")

    return None


# ── webcast-eqs.com Login + HLS Stream Extraction ────────────────────────────

def extract_webcast_eqs_stream(webcast_url: str) -> str | None:
    """
    Obtain the real HLS (.m3u8) stream URL from a webcast-eqs.com replay page.

    Flow:
      1. requests: GET register page -> extract CSRF token + session cookie
      2. requests: POST registration form -> get authenticated session cookie
      3. Playwright: load player page with session cookie, intercept network
                     requests until an .m3u8 URL is captured
    """
    # Derive the registration URL (replace /tc or /en suffix with /register/.../tc)
    # webcast_url e.g. https://www.webcast-eqs.com/asus25q4/tc
    base = webcast_url.rstrip('/')
    parts = base.split('/')
    lang = parts[-1]                        # "tc" or "en"
    code = parts[-2]                        # "asus25q4"
    register_url = f"https://www.webcast-eqs.com/register/{code}/{lang}"

    print(f"[webcast-eqs] Logging in via {register_url} ...")

    # ── Step 1 & 2: requests-based login ─────────────────────────────────────
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    try:
        r1 = session.get(register_url, timeout=15)
        token_m = re.search(r'name="_token"\s+value="([^"]+)"', r1.text)
        if not token_m:
            print(f"[webcast-eqs] Could not find CSRF token.")
            return None
        token = token_m.group(1)

        r2 = session.post(
            f"https://www.webcast-eqs.com/active-collection/{code}",
            data={
                "_token":         token,
                "activeCollection": "1",
                "language":       lang,
                "name":           "Investor",
                "company":        "Individual",
                "email":          "investor@example.com",
                "identitiy":      "投資者",   # note: typo in original form field name
                "disclaimer":     "accepted",
            },
            allow_redirects=True,
            headers={
                "Referer": register_url,
                "Origin":  "https://www.webcast-eqs.com",
            },
            timeout=20,
        )

        if "register" in r2.url:
            print(f"[webcast-eqs] Login failed (redirected back to register).")
            return None

        print(f"[webcast-eqs] Logged in -> {r2.url}")

    except Exception as e:
        print(f"[webcast-eqs] Login request failed: {e}")
        return None

    # Convert requests cookies to Playwright format
    pw_cookies = [
        {"name": c.name, "value": c.value, "domain": ".webcast-eqs.com", "path": "/"}
        for c in session.cookies
    ]

    # ── Step 3: Playwright intercepts the HLS stream request ─────────────────
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"[webcast-eqs] playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        return None

    m3u8_url = None

    def on_request(request):
        nonlocal m3u8_url
        if m3u8_url is None and ".m3u8" in request.url:
            m3u8_url = request.url
            print(f"[webcast-eqs] HLS stream: {m3u8_url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            ctx = browser.new_context(user_agent=UA)
            ctx.add_cookies(pw_cookies)

            page = ctx.new_page()
            page.on("request", on_request)

            print(f"[webcast-eqs] Loading player page ...")
            page.goto(webcast_url, wait_until="domcontentloaded")

            # Wait up to 25 s for the player to start the HLS stream
            for _ in range(25):
                if m3u8_url:
                    break
                page.wait_for_timeout(1000)

            browser.close()

    except Exception as e:
        print(f"[webcast-eqs] Playwright error: {e}")

    if not m3u8_url:
        print(f"[webcast-eqs] No HLS stream intercepted.")

    return m3u8_url


# ── MOPS Scraper (Taiwan) ─────────────────────────────────────────────────────

def scrape_mops_tw(stock_id: str, year: str, quarter: str) -> str | None:
    """
    Query MOPS (公開資訊觀測站) 法說會影音 for a Taiwan-listed stock.
    Returns a YouTube URL or direct media URL if found, else None.
    """
    roc_year = int(year) - 1911
    print(f"[MOPS] Querying {stock_id} {year}(民{roc_year}) Q{quarter} ...")

    try:
        resp = requests.post(
            "https://mops.twse.com.tw/mops/web/ajax_t100sb04",
            data={
                "encodeURIComponent": "1",
                "step": "1", "firstin": "1", "off": "1",
                "co_id": stock_id,
                "year":  str(roc_year),
                "season": quarter,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer":      "https://mops.twse.com.tw/mops/web/t100sb04",
                "User-Agent":   UA,
            },
            timeout=15,
            verify=False,
        )
        html = resp.text

        yt_ids = re.findall(r'(?:v=|embed/|video/|youtu\.be/)([a-zA-Z0-9_-]{11})', html)
        if yt_ids:
            url = f"https://www.youtube.com/watch?v={yt_ids[0]}"
            print(f"[MOPS] Found YouTube: {url}")
            return url

        media = re.findall(r'href=["\']([^"\']*\.(?:mp4|m4a|mp3|wav)[^"\']*)["\']', html)
        if media:
            print(f"[MOPS] Found media: {media[0]}")
            return media[0]

        print(f"[MOPS] No media found (JS-rendered or no record).")

    except Exception as e:
        print(f"[MOPS] Failed: {e}")

    return None


# ── MOPS Playwright Scraper ───────────────────────────────────────────────────

def scrape_mops_playwright(stock_id: str, year: str, quarter: str) -> dict:
    """
    Use Playwright to navigate mops.twse.com.tw/mops/#/web/t100sb07_1,
    type the stock_id, intercept the ajax_t100sb07_1 XHR request,
    then parse the response for video URL and PDF filenames.

    Returns dict with keys:
      'ajax_url'  : full ajax URL (with encrypted parameters)
      'video_url' : irconference.twse.com.tw MP4 URL or None
      'pdfs'      : list of (filename, mopsov_url) tuples
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[MOPS-PW] playwright not installed.")
        return {}

    result = {"ajax_url": None, "video_url": None, "pdfs": []}
    ajax_url_captured = [None]

    print(f"[MOPS-PW] Launching browser for stock {stock_id} ...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            ctx = browser.new_context(user_agent=UA)

            # MOPS opens the result in a NEW PAGE (popup) - intercept context.on("page")
            def on_new_page(popup):
                url = popup.url
                if "ajax_t100sb07_1" in url and ajax_url_captured[0] is None:
                    ajax_url_captured[0] = url
                    print(f"[MOPS-PW] Popup URL: {url[:100]}...")

            ctx.on("page", on_new_page)

            page = ctx.new_page()
            page.goto("https://mops.twse.com.tw/mops/#/web/t100sb07_1",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Fill stock_id into #co_id (confirmed selector)
            page.fill("#co_id", stock_id)
            print(f"[MOPS-PW] Filled #co_id with {stock_id}")
            page.wait_for_timeout(500)

            # Click 查詢 button (button.mainBtn confirmed)
            page.click("button.mainBtn")
            print(f"[MOPS-PW] Clicked 查詢")

            # Wait for popup up to 15s
            for _ in range(15):
                if ajax_url_captured[0]:
                    break
                page.wait_for_timeout(1000)

            browser.close()
    except Exception as e:
        print(f"[MOPS-PW] Browser error: {e}")
        return result

    if not ajax_url_captured[0]:
        print(f"[MOPS-PW] No popup with ajax_t100sb07_1 detected.")
        return result

    result["ajax_url"] = ajax_url_captured[0]

    # Fetch the ajax URL and parse for video + PDFs
    try:
        resp = requests.get(
            ajax_url_captured[0],
            headers={"User-Agent": UA,
                     "Referer": "https://mops.twse.com.tw/mops/"},
            timeout=15, verify=False,
        )
        html = resp.text

        target_year, month_min, month_max = _quarter_date_window(year, quarter)

        def mops_asset_date_ok(date_str: str) -> bool:
            if not date_str or len(date_str) != 8:
                return False
            return date_str[:4] == target_year and month_min <= int(date_str[4:6]) <= month_max

        # Video: irconference.twse.com.tw MP4 (may be absolute or relative).
        # Do not trust the first result blindly: MOPS can return the latest event
        # for a stock even when it belongs to a different quarter.
        vids = re.findall(r'(https?://irconference\.twse\.com\.tw/[^\s"\'<>]+\.mp4)', html)
        if not vids:
            # Sometimes the URL is relative: /irconference/...mp4 or just the filename
            vids_rel = re.findall(r'(?:href|src)=["\']([^"\']*irconference[^"\']*\.mp4)["\']', html, re.I)
            vids = [v if v.startswith("http") else f"http://irconference.twse.com.tw/{v.lstrip('/')}"
                    for v in vids_rel]

        accepted_vids = []
        for vid in dict.fromkeys(vids):
            m = re.search(r'(\d{8})', vid)
            date_str = m.group(1) if m else ""
            if mops_asset_date_ok(date_str):
                accepted_vids.append(vid)
            else:
                print(
                    f"[MOPS-PW] Reject video outside target window "
                    f"{target_year}-{month_min:02d}..{target_year}-{month_max:02d}: {vid}"
                )

        if accepted_vids:
            result["video_url"] = accepted_vids[0]
            print(f"[MOPS-PW] Video: {accepted_vids[0]}")
        else:
            print(f"[MOPS-PW] No video URL found in MOPS response for target quarter.")

        # PDFs: {stock_id}YYYYMMDD{M|E}001.pdf. Apply the same date gate.
        pdfs = re.findall(rf'({re.escape(stock_id)}\d{{8}}[A-Z]\d{{3}}\.pdf)', html)
        for fn in dict.fromkeys(pdfs):   # deduplicate preserving order
            date_str = fn[len(stock_id):len(stock_id)+8]
            if not mops_asset_date_ok(date_str):
                print(
                    f"[MOPS-PW] Reject PDF outside target window "
                    f"{target_year}-{month_min:02d}..{target_year}-{month_max:02d}: {fn}"
                )
                continue
            url = f"https://mopsov.twse.com.tw/nas/STR/{fn}"
            result["pdfs"].append((fn, url))
            print(f"[MOPS-PW] PDF: {fn}")

    except Exception as e:
        print(f"[MOPS-PW] Parse error: {e}")

    return result


# ── JS-rendered Direct-IR Scraper (Playwright) ───────────────────────────────

def _quarter_date_window(year: str, quarter: str) -> tuple[str, int, int]:
    """Return the expected conference year and month window for a quarter."""
    if quarter == "4":
        return str(int(year) + 1), 1, 4
    if quarter == "1":
        return year, 4, 6
    if quarter == "2":
        return year, 7, 9
    return year, 10, 12


def _probe_delta_ccdntech_url(url: str, expect_playlist: bool = False) -> bool:
    """Return True when a Delta ccdntech URL looks live."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": UA})
        body = resp.text
        if expect_playlist:
            return resp.status_code == 200 and "#EXTM3U" in body
        return resp.status_code == 200 and (
            "CCDNPlayer" in body or "open-video" in body or "jwplayer" in body
        )
    except Exception:
        return False



def _extract_delta_landing_video(stock_id: str, year: str, quarter: str) -> tuple[str | None, str | None]:
    """Resolve Delta's Chinese replay URL from page data or verified URL patterns."""
    if stock_id != "2308":
        return None, None

    target_year, month_min, month_max = _quarter_date_window(year, quarter)
    quarter_label = f"第{'一二三四'[int(quarter) - 1]}季法人說明會"
    candidate_pages = [
        "https://landing.deltaww.com/zh-TW/Investors/Analyst-Meeting",
        "https://www.deltaww.com/zh-TW/investors/analyst-meeting",
    ]
    matched_conf_date = None

    for page_url in candidate_pages:
        try:
            resp = requests.get(page_url, timeout=20, headers={"User-Agent": UA})
            html = resp.text
        except Exception as e:
            print(f"[Delta] Landing page fetch failed: {e}")
            continue

        blocks = re.findall(r'<div class="meeting-list">(.*?)</ul></div>', html, re.S)
        if not blocks:
            continue

        print(f"[Delta] Found {len(blocks)} meeting block(s) on {page_url}")
        for block in blocks:
            date_m = re.search(r'<li class="date">\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*</li>', block)
            title_m = re.search(r'<li class="title">\s*([^<]+?)\s*</li>', block)
            if not date_m or not title_m:
                continue

            conf_year = date_m.group(1)
            conf_month = int(date_m.group(2))
            conf_date = f"{date_m.group(1)}{int(date_m.group(2)):02d}{int(date_m.group(3)):02d}"
            title = title_m.group(1).strip()
            if conf_year != target_year or not (month_min <= conf_month <= month_max):
                continue
            if quarter_label not in title:
                continue

            matched_conf_date = conf_date
            zh_m = re.search(
                r'class="open-video"[^>]*data-url="([^"]+)"[^>]*>\s*(?:Chinese|中文影片|中文)\s*<',
                block,
                re.I,
            )
            if zh_m:
                video_url = zh_m.group(1).replace('&amp;', '&')
                direct_hls = None
                m = re.search(r'vod41/([^&]+)', video_url)
                if m:
                    direct_hls = f"https://cdn41.ccdntech.com/vod-http/_definst_/vod41/{m.group(1)}/playlist.m3u8"
                if direct_hls and _probe_delta_ccdntech_url(direct_hls, expect_playlist=True):
                    print(f"[Delta] Matched landing-page Chinese HLS: {direct_hls[:80]}...")
                    return direct_hls, conf_date
                print(f"[Delta] Matched landing-page Chinese video: {video_url[:80]}...")
                return video_url, conf_date

        print(f"[Delta] No matching Chinese video block found on {page_url}")

    if not matched_conf_date:
        return None, None

    yyyy = matched_conf_date[:4]
    mmdd = matched_conf_date[4:]
    hls_candidates = [
        f"https://cdn41.ccdntech.com/vod-http/_definst_/vod41/{yyyy}_{mmdd}_中文_1.mp4/playlist.m3u8",
        f"https://cdn41.ccdntech.com/vod-http/_definst_/vod41/{matched_conf_date}_中文_1.mp4/playlist.m3u8",
        f"https://cdn41.ccdntech.com/vod-http/_definst_/vod41/{mmdd}_TW_1.mp4/playlist.m3u8",
        f"https://cdn41.ccdntech.com/vod-http/_definst_/vod41/{mmdd}_中文_1.mp4/playlist.m3u8",
    ]
    for url in hls_candidates:
        if _probe_delta_ccdntech_url(url, expect_playlist=True):
            print(f"[Delta] Matched synthesized Chinese HLS URL: {url[:80]}...")
            return url, matched_conf_date

    player_candidates = [
        f"https://crs.ccdntech.com/rds/playerh7vodcdn?vod41/{yyyy}_{mmdd}_中文_1.mp4&cname&hls",
        f"https://crs.ccdntech.com/rds/playerh7vodcdn?vod41/{matched_conf_date}_中文_1.mp4&cname&hls",
        f"https://crs.ccdntech.com/rds/playerh7vodcdn?vod41/{mmdd}_TW_1.mp4&cname&hls",
        f"https://crs.ccdntech.com/rds/playerh7vodcdn?vod41/{mmdd}_中文_1.mp4&cname&hls",
    ]
    for url in player_candidates:
        if _probe_delta_ccdntech_url(url):
            print(f"[Delta] Matched synthesized Chinese player URL: {url[:80]}...")
            return url, matched_conf_date

    print(f"[Delta] Could not verify a Chinese replay URL for {matched_conf_date}")
    return None, matched_conf_date


def scrape_playwright_direct_ir(stock_id: str, ir_url: str, year: str, quarter: str) -> tuple:
    """
    Use Playwright to render a JS-heavy IR page and intercept video URLs.

    Intercepts network responses for .mp4 / .m3u8 and also scans DOM for
    <video src>, <source src>, and <iframe src> with video players.
    Matches by year+quarter calendar range.

    Returns (video_url, conf_date_str) or (None, None).

    Example: quantatw.com - JS dynamically loads icp player with MP4 links.
    Quarter date mapping:
      Q4 -> target_year=year+1, months Jan–Apr
      Q1 -> target_year=year, months Apr–Jun
      Q2 -> target_year=year, months Jul–Sep
      Q3 -> target_year=year, months Oct–Dec
    """
    # Quarter -> expected conference month range
    target_year, month_min, month_max = _quarter_date_window(year, quarter)

    # Delta's page opens replay URLs via JS data-url attributes; parse those first.
    delta_video_url, delta_conf_date = _extract_delta_landing_video(stock_id, year, quarter)
    if delta_video_url:
        return delta_video_url, delta_conf_date

    # Newer Hinet pages embed the HLS URL in page HTML; use it directly when present.
    try:
        resp = requests.get(ir_url, timeout=20, headers={"User-Agent": UA})
        html = resp.text
        embedded = []
        for m in re.finditer(r'"url":"(https:\/\/.*?playlist\.m3u8)"', html):
            url = m.group(1).replace("/", "/")
            dm = re.search(r'(\d{8})', url)
            embedded.append((url, dm.group(1) if dm else ""))
        for m in re.finditer(r"(https?://[^\s\"']+\.(?:mp4|m3u8|flv)(?:\?[^\s\"']*)?)", html, re.I):
            url = m.group(1)
            dm = re.search(r'(\d{8})', url)
            embedded.append((url, dm.group(1) if dm else ""))
        if embedded:
            print(f"[PW-IR] Found {len(embedded)} embedded media candidate(s) in HTML")
            for url, date_str in embedded:
                if len(date_str) == 8:
                    y, mo = date_str[:4], int(date_str[4:6])
                    if y == target_year and month_min <= mo <= month_max:
                        print(f"[PW-IR] HTML match: {url[:80]}...")
                        return url, date_str
            url, date_str = embedded[0]
            print(f"[PW-IR] HTML fallback: {url[:80]}...")
            return url, date_str
    except Exception as e:
        print(f"[PW-IR] HTML probe failed: {e}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[PW-IR] playwright not installed - pip install playwright && playwright install chromium")
        return None, None

    captured_videos = []   # list of (url, date_str)

    def on_response(response):
        url = response.url
        # Intercept any .mp4 or .m3u8 network request
        if re.search(r'\.(mp4|m3u8|flv)(\?|$)', url, re.I):
            m = re.search(r'(\d{8})', url)
            date_str = m.group(1) if m else ""
            captured_videos.append((url, date_str))
            print(f"[PW-IR] Intercepted video: {url[:80]}...")

    print(f"[PW-IR] Launching browser for {ir_url} ...")
    dom_videos = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = browser.new_page(user_agent=UA)
            page.on("response", on_response)

            page.goto(ir_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)  # let lazy JS finish

            # TSMC Special: Look for play button or audio link specifically
            if "tsmc" in ir_url.lower():
                print("[PW-IR] TSMC specific: Looking for Play button...")
                try:
                    # Try to find and click play/audio buttons
                    selectors = ["text=Play", "text=Audio", ".play-button", "button:has-text('Replay')"]
                    for sel in selectors:
                        if page.is_visible(sel):
                            page.click(sel)
                            print(f"[PW-IR] Clicked {sel}")
                            page.wait_for_timeout(5000)
                            break
                except Exception as e:
                    print(f"[PW-IR] TSMC click failed: {e}")

            # Scan DOM for video/source/iframe src attrs
            for attr in ["video[src]", "source[src]", "a[href]"]:
                try:
                    els = page.query_selector_all(attr)
                    for el in els:
                        src = el.get_attribute("src") or el.get_attribute("href") or ""
                        if re.search(r'\.(mp4|m3u8|flv)(\?|$)', src, re.I):
                            m = re.search(r'(\d{8})', src)
                            date_str = m.group(1) if m else ""
                            dom_videos.append((src, date_str))
                            print(f"[PW-IR] DOM video: {src[:80]}...")
                        elif re.search(r'(?:youtu\.be/|youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})', src):
                            dom_videos.append((src, ""))
                            print(f"[PW-IR] DOM YouTube: {src[:80]}...")
                except Exception:
                    pass

            browser.close()
    except Exception as e:
        print(f"[PW-IR] Browser error: {e}")
        return None, None

    all_videos = captured_videos + dom_videos
    if not all_videos:
        print(f"[PW-IR] No video URLs found on {ir_url}")
        return None, None

    print(f"[PW-IR] Total video candidates: {len(all_videos)}")

    # Try to match by year+quarter date range
    for url, date_str in all_videos:
        if len(date_str) == 8:
            y, mo = date_str[:4], int(date_str[4:6])
            if y == target_year and month_min <= mo <= month_max:
                print(f"[PW-IR] Matched Q{quarter} {year}: {url[:80]}...")
                return url, date_str

    # TSMC Fallback: If on TSMC page and captured anything, take the first one
    if "tsmc" in ir_url.lower() and all_videos:
        print(f"[PW-IR] TSMC Fallback: Taking first captured video for 2330: {all_videos[0][0][:80]}...")
        return all_videos[0][0], ""

    # For YouTube URLs without date: check title via yt-dlp
    yt_candidates = [(u, d) for u, d in all_videos
                     if re.search(r'(?:youtu\.be/|youtube\.com/watch)', u)]
    if yt_candidates:
        q_str = f"Q{quarter}"
        for yt_url, _ in yt_candidates:
            try:
                r = subprocess.run(
                    ["yt-dlp", "--get-title", "--no-warnings", yt_url],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                )
                title = r.stdout.strip()
                if target_year in title or (year in title and q_str.lower() in title.lower()):
                    print(f"[PW-IR] YouTube title match: {title}")
                    return yt_url, ""
            except Exception:
                continue
        # No title match - use first YouTube candidate (most recent = first on page)
        url, _ = yt_candidates[0]
        print(f"[PW-IR] YouTube fallback (first on page): {url[:80]}...")
        return url, ""

    # Fallback: first intercepted (most recent)
    url, date_str = all_videos[0]
    print(f"[PW-IR] No exact Q{quarter} {year} match - using first: {url[:80]}...")
    return url, date_str


# ── IR Site Scraper (US) ──────────────────────────────────────────────────────

def scrape_ir_site(ir_url: str, year: str, quarter: str) -> str | None:
    """Scrape a US IR page for YouTube video IDs matching year/quarter."""
    print(f"[IR] Fetching {ir_url} ...")
    try:
        resp = requests.get(ir_url, timeout=15, headers={"User-Agent": UA})
        html = resp.text

        yt_ids = re.findall(r'(?:v=|embed/|video/|youtu\.be/)([a-zA-Z0-9_-]{11})', html)
        if not yt_ids:
            print(f"[IR] No YouTube IDs found (likely JS-rendered).")
            return None

        print(f"[IR] Found {len(yt_ids)} YouTube ID(s).")
        q_str = f"Q{quarter}"
        for vid_id in yt_ids:
            check_url = f"https://www.youtube.com/watch?v={vid_id}"
            try:
                r = subprocess.run(
                    ["yt-dlp", "--get-title", "--no-warnings", check_url],
                    capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                )
                title = r.stdout.strip()
                if year in title and q_str.lower() in title.lower():
                    print(f"[IR] Matched: {title}")
                    return check_url
            except Exception:
                continue

        fallback = f"https://www.youtube.com/watch?v={yt_ids[0]}"
        print(f"[IR] No exact match - using first: {fallback}")
        return fallback

    except Exception as e:
        print(f"[IR] Failed: {e}")

    return None


# ── Audio Checksum Guard ──────────────────────────────────────────────────────

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".mp4", ".wav"}


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for a local file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_audio_duration(path: Path) -> float | None:
    """Return ffprobe duration in seconds, or None when probing fails."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            return float(r.stdout.strip())
    except Exception as e:
        print(f"[audio-metadata] ffprobe failed for {path}: {e}")
    return None


def load_audio_metadata(repo: Path) -> dict:
    """Load audio_metadata.json. The file is partial and append-only friendly."""
    metadata_file = repo / "audio_metadata.json"
    if not metadata_file.exists():
        return {}
    try:
        data = json.loads(metadata_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[audio-metadata] Could not read audio_metadata.json: {e}")
        return {}


def write_audio_metadata(repo: Path, metadata: dict) -> None:
    metadata_file = repo / "audio_metadata.json"
    metadata_file.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def release_url_for_stem(repo: Path, stem: str) -> str | None:
    manifest_file = repo / "audio_manifest.json"
    if not manifest_file.exists():
        return None
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        url = manifest.get(stem)
        return url if isinstance(url, str) else None
    except Exception:
        return None


def find_audio_metadata_duplicate(repo: Path, candidate_sha: str, expected_stem: str) -> str | None:
    """Return duplicate description from audio_metadata.json if the checksum is known."""
    for stem, item in load_audio_metadata(repo).items():
        if stem == expected_stem or not isinstance(item, dict):
            continue
        if str(item.get("sha256", "")).lower() == candidate_sha.lower():
            status = item.get("status", "known")
            return f"audio_metadata.json entry {stem} ({status})"
    return None


def update_audio_metadata(
    repo: Path,
    audio_path: Path,
    release_url: str | None = None,
    status: str = "ok",
    duplicate_of: str | None = None,
) -> None:
    """Record checksum, size and probed duration for a local audio file."""
    stem = audio_path.stem
    duration = probe_audio_duration(audio_path)
    item = {
        "file": str(audio_path.relative_to(repo)).replace("\\", "/"),
        "sha256": sha256_file(audio_path),
        "size_bytes": audio_path.stat().st_size,
        "duration_sec": round(duration, 3) if duration is not None else None,
        "release_url": release_url or release_url_for_stem(repo, stem),
        "checked_at": datetime.date.today().isoformat(),
        "source": "local_file",
        "status": status,
    }
    if duplicate_of:
        item["duplicate_of"] = duplicate_of
    metadata = load_audio_metadata(repo)
    metadata[stem] = item
    write_audio_metadata(repo, metadata)
    print(f"[audio-metadata] Updated {stem}: sha256={item['sha256'][:12]}..., duration={item['duration_sec']}s")


def _release_audio_asset_digests() -> dict[str, str]:
    """Return {asset_name: sha256_hex} for GitHub release audio assets when available."""
    url = "https://api.github.com/repos/wenchiehlee-money/InvestorConference/releases/tags/audio-files"
    try:
        r = requests.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=20)
        if r.status_code != 200:
            print(f"[checksum] Could not load release assets: HTTP {r.status_code}")
            return {}
        assets = r.json().get("assets", [])
    except Exception as e:
        print(f"[checksum] Could not load release assets: {e}")
        return {}

    digests = {}
    for asset in assets:
        name = asset.get("name") or ""
        digest = asset.get("digest") or ""
        if Path(name).suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if digest.startswith("sha256:"):
            digests[name] = digest.split(":", 1)[1].lower()
    return digests


def find_duplicate_audio(repo: Path, audio_path: Path, expected_stem: str) -> str | None:
    """Return a duplicate audio description if *audio_path* already exists under another stem."""
    if not audio_path.exists():
        return None

    candidate_sha = sha256_file(audio_path)
    candidate_name = audio_path.name

    metadata_duplicate = find_audio_metadata_duplicate(repo, candidate_sha, expected_stem)
    if metadata_duplicate:
        return metadata_duplicate

    # Local audio may be sparse because most files are stored as release assets, but check it first.
    exclude_dirs = {".git", ".github", "tmp", "tools", "web", "data", "skills", "scripts"}
    for p in repo.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if p.resolve() == audio_path.resolve():
            continue
        if any(part in exclude_dirs for part in p.relative_to(repo).parts[:-1]):
            continue
        if p.stem == expected_stem:
            continue
        try:
            if sha256_file(p) == candidate_sha:
                return f"local file {p.relative_to(repo)}"
        except Exception as e:
            print(f"[checksum] Skipped {p}: {e}")

    for asset_name, digest in _release_audio_asset_digests().items():
        if asset_name == candidate_name or Path(asset_name).stem == expected_stem:
            continue
        if digest == candidate_sha:
            return f"release asset {asset_name}"

    return None


# ── yt-dlp Downloader ─────────────────────────────────────────────────────────

def download_audio(source: str, output_path: Path,
                   match_title: str = None, no_check_cert: bool = False) -> bool:
    """
    Download audio from a URL or yt-dlp search query.
    Returns True if output file exists after the attempt.
    """
    # Workaround for CCDNTech TLS alert 112 (unrecognized name) warning
    if "ccdntech" in source:
        # 1. Convert player URL to direct HLS URL
        m = re.search(r'playerh7vodcdn\?(vod(\d+)/[^&]+)', source)
        if m:
            vod_part = m.group(1)
            cdn_num = m.group(2)
            source = f"https://cdn{cdn_num}.ccdntech.com/vod-http/_definst_/{vod_part}/playlist.m3u8"
        
        # 2. Replace unrecognized domain name with working CNAME
        m_hn = re.search(r'vod(\d+)-ccdntech\.cdn\.hinet\.net', source)
        if m_hn:
            cdn_num = m_hn.group(1)
            source = source.replace(f"vod{cdn_num}-ccdntech.cdn.hinet.net", f"cdn{cdn_num}.ccdntech.com")
        
        print(f"[CCDNTech] Patched HLS stream URL to: {source}")

    is_direct_media = (
        source.startswith(("http://", "https://"))
        and re.search(r"\.(?:mp4|m4a|mp3|wav)(?:[?#].*)?$", source, re.I)
        and "playlist.m3u8" not in source.lower()
    )
    if is_direct_media:
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-i", source,
            "-vn", "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        print(f"[ffmpeg] {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, encoding="utf-8", errors="replace")
        if output_path.exists() and output_path.stat().st_size > 0:
            return True
        if output_path.exists():
            output_path.unlink()
        if result.stderr:
            lines = [l for l in result.stderr.splitlines() if l.strip()]
            for line in lines[-3:]:
                print(f"[ffmpeg] {line}")
        print("[ffmpeg] Direct media extraction failed. Falling back to yt-dlp...")

    cmd = [
        "yt-dlp", source,
        "--extract-audio",
        "--audio-format", "m4a",
        "--audio-quality", "0",
        "--output", str(output_path),
        "--no-playlist",
        "--no-warnings",
        "--no-check-certificates",
        "--legacy-server-connect",
        "--prefer-free-formats"
    ]
    if match_title:
        cmd += ["--match-filter", f"title~='{match_title}'"]

    print(f"[yt-dlp] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")

    if not output_path.exists() and result.stderr:
        lines = [l for l in result.stderr.splitlines() if l.strip()]
        for line in lines[-3:]:
            print(f"[yt-dlp] {line}")

    return output_path.exists()


# ── MOPS PDF Downloader ───────────────────────────────────────────────────────

def download_mops_pdfs(stock_id: str, conf_date: str, year: str, quarter: str,
                       save_dir: Path) -> list:
    """
    Download 法說會簡報 PDFs from mopsov.twse.com.tw/nas/STR/.
    Naming: {stock_id}{YYYYMMDD}{M|E}001.pdf  (M=中文, E=英文)
    conf_date: YYYYMMDD string from conference MP4 filename.
    Tries conf_date and ±2 days to handle filing-vs-conference date mismatch.
    Saves as {stock_id}_{year}_q{quarter}_ir.pdf / _ir_en.pdf.
    """
    if not conf_date:
        return []

    from datetime import datetime, timedelta
    base_url = "https://mopsov.twse.com.tw/nas/STR/"
    referer  = "https://mopsov.twse.com.tw/mops/web/t100sb07"

    try:
        base_dt = datetime.strptime(conf_date, "%Y%m%d")
    except ValueError:
        return []

    suffix_map = [("M", f"{stock_id}_{year}_q{quarter}_ir.pdf"),
                  ("E", f"{stock_id}_{year}_q{quarter}_ir_en.pdf")]
    downloaded = []

    for lang_code, dest_name in suffix_map:
        dest = save_dir / dest_name
        if dest.exists():
            print(f"[MOPS-PDF] Already exists: {dest_name}")
            downloaded.append(dest)
            continue
        found = False
        for delta in range(-2, 3):          # try ±2 days
            probe_date = (base_dt + timedelta(days=delta)).strftime("%Y%m%d")
            fn  = f"{stock_id}{probe_date}{lang_code}001.pdf"
            url = base_url + fn
            try:
                r = requests.get(
                    url,
                    headers={"User-Agent": UA, "Referer": referer},
                    timeout=20, verify=False,
                )
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    dest.write_bytes(r.content)
                    print(f"[MOPS-PDF] OK {fn} -> {dest_name} ({len(r.content)//1024}KB)")
                    downloaded.append(dest)
                    found = True
                    break
            except Exception:
                continue
        if not found:
            print(f"[MOPS-PDF] FAILED {lang_code} PDF not found (tried ±2 days around {conf_date})")

    return downloaded


# ── PDF Downloader ────────────────────────────────────────────────────────────

def download_pdfs(stock_id: str, year: str, quarter: str,
                  save_dir: Path) -> list:
    """
    Download PDF attachments (IR slides, Q&A) for a given stock/year/quarter.
    Returns list of downloaded Path objects.
    """
    downloaded = []

    # Novatek (3034) special handling: JS-rendered IR page with hashed filenames
    if stock_id == "3034":
        ir_url = KNOWN_TW_IR.get("3034")
        print(f"[PDF-3034] Scraping {ir_url} for {year} Q{quarter} PDF...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=UA)
                page.goto(ir_url, wait_until="networkidle", timeout=30000)
                # Find the link matching "year/Qquarter" e.g. "2025/Q4"
                target_label = f"{year}/Q{quarter}"
                pdf_link = page.get_attribute(f"a:has-text('{target_label}')", "href")
                if pdf_link:
                    pdf_url = urljoin(ir_url, pdf_link)
                    filename = f"{stock_id}_{year}_q{quarter}_ir.pdf"
                    dest = save_dir / filename
                    print(f"[PDF-3034] Found {target_label}: {pdf_url}")
                    resp = requests.get(pdf_url, timeout=30, headers={"User-Agent": UA})
                    if resp.status_code == 200:
                        dest.write_bytes(resp.content)
                        print(f"[PDF-3034] OK Saved: {dest} ({dest.stat().st_size // 1024} KB)")
                        downloaded.append(dest)
                else:
                    print(f"[PDF-3034] FAILED No link found for label '{target_label}'")
                browser.close()
        except Exception as e:
            print(f"[PDF-3034] FAILED Failed to scrape PDFs: {e}")

    templates = KNOWN_PDF_ATTACHMENTS.get(stock_id, [])
    if not templates:
        return downloaded

    for suffix, url_template in templates:
        url = url_template.format(year=year, quarter=quarter)
        filename = f"{stock_id}_{year}_q{quarter}_{suffix}.pdf"
        dest = save_dir / filename

        if dest.exists():
            print(f"[PDF] Already downloaded: {dest}")
            downloaded.append(dest)
            continue

        print(f"[PDF] Downloading {suffix.upper()}: {url}")
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": UA}, stream=True)
            if resp.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                print(f"[PDF] OK Saved: {dest} ({dest.stat().st_size // 1024} KB)")
                downloaded.append(dest)
            else:
                print(f"[PDF] FAILED HTTP {resp.status_code}: {url}")
        except Exception as e:
            print(f"[PDF] FAILED Failed: {e}")

    return downloaded


def expected_quarter(date_str: str) -> tuple[str | None, str | None]:
    """Return (year, quarter) the fiscal quarter reported on a given conference date."""
    if not date_str:
        return None, None
    try:
        y, mo = int(date_str[:4]), int(date_str[5:7])
    except (ValueError, IndexError):
        return None, None
    # Taiwan/US standard: Q4 earnings usually in Jan-Apr of next year
    if 1 <= mo <= 4:
        return str(y - 1), "4"
    if 5 <= mo <= 6:
        return str(y), "1"
    if 7 <= mo <= 9:
        return str(y), "2"
    return str(y), "3"


def expected_us_calendar_earnings_quarter(date_str: str) -> tuple[str | None, str | None]:
    """Return (year, quarter) for US calendar-year earnings announcement dates."""
    if not date_str:
        return None, None
    try:
        y, mo = int(date_str[:4]), int(date_str[5:7])
    except (ValueError, IndexError):
        return None, None
    if 1 <= mo <= 3:
        return str(y - 1), "4"
    if 4 <= mo <= 6:
        return str(y), "1"
    if 7 <= mo <= 9:
        return str(y), "2"
    return str(y), "3"


def _csv_row_yq(ev_name: str, remarks: str, date_str: str) -> tuple[str | None, str | None]:
    """Return (year, quarter) for a CSV event row.

    Priority:
    1. Explicit ``YYYY Q#`` pattern found in 備註 (remarks) column.
    2. Explicit ``YYYY Q#`` pattern found in 事件名稱 (event name).
    3. Fall back to date-based heuristic via expected_quarter().
    """
    _yq_pat = re.compile(r'(\d{4})\s*[Qq](\d)')
    # Explicitly check remarks and event name
    for text in [remarks, ev_name]:
        if not text: continue
        m = _yq_pat.search(text)
        if m:
            return m.group(1), m.group(2)
    return expected_quarter(date_str)


def ingest_from_todo(auto_push: bool = False) -> None:
    """Scan raw_event_upcoming_earnings.csv and ingest any missing past events."""
    import csv as _csv
    from datetime import date as _date

    csv_path = Path("raw_event_upcoming_earnings.csv")
    if not csv_path.exists():
        print(f"[TODO] FAILED {csv_path} not found.")
        return

    today = _date.today()
    todo_list = []

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                evt_name = row.get("事件名稱", "")
                evt_date_str = row.get("開始日期", "")
                if not evt_name or not evt_date_str: continue

                try:
                    evt_date = _date.fromisoformat(evt_date_str)
                except ValueError: continue

                # Only process events that have already happened or are today
                if evt_date > today: continue

                # Extract stock ID
                m = re.search(r'[（(](\w+)[）)]', evt_name)
                if not m: continue
                stock_id = m.group(1)

                # Determine year/quarter - prefer explicit info in CSV over date heuristic
                remarks = row.get("備註", "")
                y, q = _csv_row_yq(evt_name, remarks, evt_date_str)
                if not y or not q: continue

                # Check if audio already exists (locally or in manifest)
                stem = f"{stock_id}_{y}_q{q}"
                save_dir = Path(stock_id)
                exists_local = any(save_dir.glob(f"{stem}.*"))

                # Check manifest (lazy load)
                if not hasattr(ingest_from_todo, "_manifest_cache"):
                    manifest_path = Path("audio_manifest.json")
                    if manifest_path.exists():
                        ingest_from_todo._manifest_cache = json.loads(manifest_path.read_text(encoding="utf-8"))
                    else:
                        ingest_from_todo._manifest_cache = {}

                exists_manifest = stem in ingest_from_todo._manifest_cache

                if not exists_local and not exists_manifest:
                    todo_list.append((stock_id, y, q, evt_date_str))
    except Exception as e:
        print(f"[TODO] FAILED Error reading CSV: {e}")
        return

    if not todo_list:
        print("[TODO] OK No missing past events found. Everything up to date.")
        return

    print(f"[TODO] Found {len(todo_list)} missing events to ingest.")
    for sid, y, q, dt in todo_list:
        print(f"\n[TODO] >>> Processing {sid} {y} Q{q} (Date: {dt}) ...")
        try:
            ingest_earnings_audio(sid, y, q, auto_push=auto_push)
        except Exception as e:
            print(f"[TODO] FAILED Failed {sid}: {e}")

    # Final step: Refresh README
    update_readme()


# ── README Generator ─────────────────────────────────────────────────────────

def update_readme() -> None:
    """Regenerate README.md from repo state + raw_event_upcoming_earnings.csv."""
    import csv as _csv

    repo = INVESTOR_CONFERENCE_REPO
    
    # Load historical dates if exists
    historical_dates = {}
    hist_date_path = repo / "mops_historical_dates.json"
    if hist_date_path.exists():
        try:
            historical_dates = json.loads(hist_date_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Ensure audio_durations.json is synced first ──
    sync_all_audio_durations(repo)
    durations_file = repo / "audio_durations.json"
    durations_cache = {}
    if durations_file.exists():
        try:
            durations_cache = json.loads(durations_file.read_text(encoding="utf-8"))
        except Exception: pass

    # Load company names from raw_companyinfo.csv
    tw_company_names = {}
    csv_info_path = repo / "raw_companyinfo.csv"
    if csv_info_path.exists():
        try:
            with open(csv_info_path, encoding="utf-8-sig") as fh:
                for r_info in _csv.DictReader(fh):
                    sid_info = r_info.get("代號")
                    name_info = r_info.get("名稱")
                    if sid_info and name_info:
                        tw_company_names[sid_info.strip()] = name_info.strip()
        except Exception: pass

    _TICKER = r'(?:\d{4}|[A-Z]{1,5})'
    audio_pat  = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)\.(mp3|m4a|wav|mp4)$', re.I)
    pdf_cn_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_ir\.pdf$', re.I)
    pdf_en_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_ir_en\.pdf$', re.I)
    report_cn_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_report\.(pdf|md)$', re.I)
    report_en_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_report_en\.(pdf|md)$', re.I)
    earnings_release_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_earnings_release\.(pdf|md)$', re.I)
    financial_tables_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_financial_tables\.(pdf|md)$', re.I)
    performance_review_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_performance_review\.(pdf|md)$', re.I)
    sec_8k_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_8k\.md$', re.I)
    sec_10q_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_10q\.md$', re.I)
    transcript_pdf_pat = re.compile(rf'^({_TICKER})_(\d{{4}})_q(\d)_transcript\.(pdf|md)$', re.I)

    entries = {}  # key=(stock_id, year, quarter) -> dict

    def _entry(stock_id, year, qnum):
        key = (stock_id, year, qnum)
        if key not in entries:
            entries[key] = {"stock_id": stock_id, "year": year, "quarter": qnum,
                            "audio_min": None, "audio_path": None, 
                            "pdf_cn": None, "pdf_en": None,
                            "report_cn": None, "report_en": None,
                            "financial_tables_en": None, "transcript_pdf": None,
                            "webcast_url": None}
            entries[key]["webcast_url"] = KNOWN_US_WEBCASTS_BY_QUARTER.get((stock_id.upper(), year, qnum))
        return entries[key]

    exclude_dirs = {"web", "tmp", "tools", "spec", "definitions", ".git", ".github", "__pycache__"}
    for d in sorted((repo / "data").iterdir()):
        if not d.is_dir() or d.name.lower() in exclude_dirs or not re.match(r'^(\d{4}|[A-Z]{1,5})$', d.name, re.I):
            continue
        stock_id = d.name.upper() if not d.name.isdigit() else d.name
        for f in sorted(d.iterdir()):
            m = audio_pat.match(f.name)
            if m:
                _, year, qnum, _ = m.groups()
                e = _entry(stock_id, year, qnum)
                rel_path = f"data/{stock_id}/{f.name}"
                e["audio_path"] = rel_path
                # Use cached duration if available
                if rel_path in durations_cache:
                    e["audio_min"] = float(durations_cache[rel_path]) / 60
                else:
                    # Fallback for unexpected cases (should be handled by sync_all_audio_durations)
                    try:
                        r = subprocess.run(
                            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                             "-of", "csv=p=0", str(f)],
                            capture_output=True, encoding="utf-8", errors="replace", timeout=15,
                        )
                        duration_sec = float(r.stdout.strip())
                        e["audio_min"] = duration_sec / 60
                    except Exception: pass
            m2 = pdf_cn_pat.match(f.name)
            if m2:
                _, year, qnum = m2.groups()[:3]
                _entry(stock_id, year, qnum)["pdf_cn"] = f"data/{stock_id}/{f.name}"
            m3 = pdf_en_pat.match(f.name)
            if m3:
                _, year, qnum = m3.groups()[:3]
                _entry(stock_id, year, qnum)["pdf_en"] = f"data/{stock_id}/{f.name}"
            m4 = report_cn_pat.match(f.name)
            if m4:
                _, year, qnum = m4.groups()[:3]
                _entry(stock_id, year, qnum)["report_cn"] = f"data/{stock_id}/{f.name}"
            m5_primary = report_en_pat.match(f.name) or earnings_release_pat.match(f.name)
            m5_secondary = sec_8k_pat.match(f.name) or sec_10q_pat.match(f.name)
            m5 = m5_primary or m5_secondary
            if m5:
                _, year, qnum = m5.groups()[:3]
                e = _entry(stock_id, year, qnum)
                if m5_primary or not e.get("report_en"):
                    e["report_en"] = f"data/{stock_id}/{f.name}"
            m6 = financial_tables_pat.match(f.name)
            if m6:
                _, year, qnum = m6.groups()[:3]
                _entry(stock_id, year, qnum)["financial_tables_en"] = f"data/{stock_id}/{f.name}"
            m7 = performance_review_pat.match(f.name)
            if m7:
                _, year, qnum = m7.groups()[:3]
                _entry(stock_id, year, qnum)["pdf_en"] = f"data/{stock_id}/{f.name}"
            m8 = transcript_pdf_pat.match(f.name)
            if m8:
                _, year, qnum = m8.groups()[:3]
                _entry(stock_id, year, qnum)["transcript_pdf"] = f"data/{stock_id}/{f.name}"

    # Scan sibling MOPS repo downloads for TW stock financial reports
    mops_downloads = repo.parent / "MOPS" / "downloads"
    if mops_downloads.is_dir():
        for d in sorted(mops_downloads.iterdir()):
            if not d.is_dir() or not re.match(r'^(\d{4})$', d.name):
                continue
            stock_id = d.name
            for f in sorted(d.iterdir()):
                # Match Chinese Consolidated Financial Report: [year][qnum_two_digits]_[stock_id]_AI1.pdf
                m_cn = re.match(rf'^(\d{{4}})(\d{{2}})_({stock_id})_AI1\.pdf$', f.name, re.I)
                if m_cn:
                    year, qnum_str, sid = m_cn.groups()
                    qnum = str(int(qnum_str))  # e.g., "01" -> "1"
                    _entry(sid, year, qnum)["report_cn"] = f"https://github.com/wenchiehlee-investment/MOPS/blob/main/downloads/{sid}/{f.name}"

                # Match English Consolidated Financial Report: [year][qnum_two_digits]_[stock_id]_AIA.pdf
                m_en = re.match(rf'^(\d{{4}})(\d{{2}})_({stock_id})_AIA\.pdf$', f.name, re.I)
                if m_en:
                    year, qnum_str, sid = m_en.groups()
                    qnum = str(int(qnum_str))  # e.g., "01" -> "1"
                    _entry(sid, year, qnum)["report_en"] = f"https://github.com/wenchiehlee-investment/MOPS/blob/main/downloads/{sid}/{f.name}"

    # ── Process Manifest (Remote/Drive files) ──
    manifest_file = repo / "audio_manifest.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            for stem in manifest.keys():
                m = re.match(rf'^({_TICKER})_(\d{{4}})_q(\d)$', stem, re.I)
                if m:
                    sid, y, q = m.groups()
                    e = _entry(sid, y, q)
                    if not e["audio_path"]:
                        # audio_path can be anything truthy to indicate "audio exists"
                        e["audio_path"] = f"data/{sid}/{stem}.m4a" 
                        for rel_path, dur in durations_cache.items():
                            if rel_path.startswith(f"data/{sid}/{stem}."):
                                e["audio_path"] = rel_path
                                e["audio_min"] = float(dur) / 60
                                break
        except Exception: pass

    rows = list(entries.values())

    # Read raw_event_upcoming_earnings.csv - all event types (法說會 + 財報公告)
    upcoming_ir = []
    csv_path = repo / "raw_event_upcoming_earnings.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig") as fh:
            for row in _csv.DictReader(fh):
                upcoming_ir.append(row)

    # Build merged rows: one row per CSV event (with optional ingested data),
    # plus any ingested entries that have no matching CSV event.
    from datetime import date as _date, timedelta
    today     = _date.today()
    two_weeks = today + timedelta(weeks=4)

    merged = []
    matched_keys = set()

    def _format_pdf_cell(pdf_val: str | None, label: str) -> str:
        if not pdf_val:
            return "-"
        res = f"[{label}]({pdf_val})"
        if not pdf_val.startswith("https://"):
            if pdf_val.lower().endswith(".md"):
                return res
            local_md = repo / pdf_val.replace(".pdf", ".md")
            if local_md.exists():
                res += f" ([MD]({pdf_val.replace('.pdf', '.md')}))"
        else:
            try:
                parts = pdf_val.split("/")
                if "downloads" in parts:
                    dl_idx = parts.index("downloads")
                    sid = parts[dl_idx + 1]
                    filename = parts[dl_idx + 2]
                    md_filename = filename.replace(".pdf", ".md")
                    local_mops_md = repo.parent / "MOPS" / "downloads" / sid / md_filename
                    if local_mops_md.exists():
                        md_url = pdf_val.replace(".pdf", ".md")
                        res += f" ([MD]({md_url}))"
            except Exception:
                pass
        return res

    def _digest_cell(stock_id: str | None, year, quarter) -> str:
        """Return the Digest(TW) cell.

        Canonical reports live under data/reports/conference-digests/{stock_id}/.
        The old top-level Conference-digest/ path is kept as a read fallback during migration.
        """
        if not (stock_id and year and quarter):
            return "-"
        digest_name = f"{stock_id}_{year}_q{quarter}_digest.md"
        new_rel = f"data/reports/conference-digests/{stock_id}/{digest_name}"
        old_rel = f"Conference-digest/{digest_name}"
        if (repo / new_rel).exists():
            return f"[📊]({new_rel})"
        if (repo / old_rel).exists():
            return f"[📊]({old_rel})"
        return "-"

    def _format_ir_cells(stock_id: str | None, pdf_cn_file: str | None, pdf_en_file: str | None) -> tuple[str, str]:
        """Return README IR cells. For US tickers, the default _ir file is English."""
        if stock_id and not str(stock_id).isdigit():
            en_file = pdf_en_file or pdf_cn_file
            return "-", _format_pdf_cell(en_file, "EN")
        return _format_pdf_cell(pdf_cn_file, "中"), _format_pdf_cell(pdf_en_file, "EN")

    def _get_mops_link(stock_id: str, fallback_link: str = None) -> str:
        """Return a markdown link to MOPS for TW stocks, or fallback for others."""
        if stock_id and stock_id.isdigit() and len(stock_id) == 4:
            # Direct link to MOPS for Taiwan stocks
            url = f"https://mops.twse.com.tw/mops/web/t100sb07_1?step=1&firstin=1&co_id={stock_id}"
            return f"[↗]({url})"
        if fallback_link:
            return f"[↗]({fallback_link})"
        return "[↗](https://mops.twse.com.tw/mops/#/web/t100sb07_1)"

    def _audio_cell(stock_id: str, year: str, quarter: str, audio_min: float | None) -> str:
        return get_audio_link_for_readme(repo, stock_id, year, quarter, audio_min)

    def _webcast_cell(r: dict) -> str:
        audio = _audio_cell(r["stock_id"], r["year"], r["quarter"], r["audio_min"])
        if audio == "無" and r.get("webcast_url"):
            return f"[Webcast]({r['webcast_url']})"
        return audio

    def _srt_cells(stock_id: str, year: str, quarter: str) -> tuple[str, str]:
        def _link_for(name: str, label: str) -> str:
            new_rel = f"data/{stock_id}/{name}"
            old_rel = f"{stock_id}/{name}"
            if (repo / new_rel).exists():
                return f"[{label}]({new_rel})"
            if (repo / old_rel).exists():
                return f"[{label}]({old_rel})"
            return "-"

        fin_name = f"{stock_id}_{year}_q{quarter}_FIN.srt"
        gt_name = f"{stock_id}_{year}_q{quarter}_GT.srt"
        return _link_for(fin_name, "📝"), _link_for(gt_name, "✅")

    def _call_transcript_cells(r: dict) -> tuple[str, str]:
        fin, gt = _srt_cells(r["stock_id"], r["year"], r["quarter"])
        if fin == "-" and r.get("transcript_pdf"):
            fin = f"[📝]({r['transcript_pdf']})"
        return fin, gt

    for ev in upcoming_ir:
        ev_name  = ev.get("事件名稱", "")
        ev_class = ev.get("類別", "")
        date     = ev.get("開始日期", "")
        remarks  = ev.get("備註", "")
        link1    = ev.get("Link1", "")
        # Support both numeric (2330) and alpha (TSM) IDs
        m = re.search(r'[（(](\w+)[）)]', ev_name)
        sid = m.group(1) if m else None

        # Prefer explicit year/quarter from CSV, but guard against stale/misclassified
        # US earnings-calendar rows. Calendar-year US companies such as Alphabet can
        # be mislabeled as FY Q1 even when the July event is the Q2 result.
        exp_year, exp_q = _csv_row_yq(ev_name, remarks, date)
        if ev_class == "財報公告" and sid and not str(sid).isdigit():
            date_year, date_q = expected_us_calendar_earnings_quarter(date)
            if (
                sid.upper() in KNOWN_US_CALENDAR_YEAR_EARNINGS
                and date_year and date_q
                and (exp_year, exp_q) != (date_year, date_q)
            ):
                print(
                    f"[README] WARNING: {sid} CSV quarter {exp_year} Q{exp_q} "
                    f"conflicts with event date {date} -> {date_year} Q{date_q}; "
                    "using date-based calendar quarter."
                )
                exp_year, exp_q = date_year, date_q

        # Check if this is an invited/forum investor conference rather than the regular quarterly earnings call.
        # Heuristic: If the event date is > 50 days after the quarter ends, it is an invited/forum conference.
        is_invited = False
        if ev_class != "財報公告" and exp_year and exp_q and date:
            try:
                ev_dt = _date.fromisoformat(date)
                y_int = int(exp_year)
                if exp_q == "1":
                    q_end = _date(y_int, 3, 31)
                elif exp_q == "2":
                    q_end = _date(y_int, 6, 30)
                elif exp_q == "3":
                    q_end = _date(y_int, 9, 30)
                elif exp_q == "4":
                    q_end = _date(y_int, 12, 31)
                else:
                    q_end = None
                
                if q_end:
                    is_invited = (ev_dt - q_end).days > 50
            except Exception:
                pass

        # We also check if this event is in the future.
        is_future = False
        try:
            ev_date = _date.fromisoformat(date)
            if ev_date > today:
                is_future = True
        except (ValueError, TypeError):
            pass

        # Use "類別" from CSV if available, map "財報公告" -> "財報"
        ev_type = ev_class
        if ev_type == "財報公告":
            ev_type = "財報"
        elif not ev_type:
            ev_type = "法說會"
        
        # Mark as invited forum/investor conference if applicable
        if is_invited:
            ev_type = "受邀法說"

        ingested = None
        # Associate with ingested files if available.
        if sid and exp_year:
            key = (sid, exp_year, exp_q)
            for r in rows:
                if (r["stock_id"], r["year"], r["quarter"]) == key:
                    # For financial reports, match event evidence to avoid a duplicate
                    # local-only row. If call materials also exist, a separate call row
                    # is added below.
                    if ev_type == "財報":
                        if r.get("report_cn") or r.get("report_en"):
                            ingested = r
                            matched_keys.add(key)
                            break
                    else:
                        ingested = r
                        matched_keys.add(key)
                        break

        # Normalise company name: prefer known lookups, else parse from event name
        if sid:
            sid_up = sid.upper()
            if sid_up in KNOWN_US_STOCKS:
                en, chi = KNOWN_US_STOCKS[sid_up]
                display_name = f"{sid_up} {en}" + (f" {chi}" if chi else "")
            else:
                chi = tw_company_names.get(sid) or KNOWN_TW_STOCKS.get(sid, ("", ""))[1]
                if not chi:
                    # e.g. "台積電(2330) 財報" -> "台積電"
                    chi = re.sub(r'[（(]\w+[）)].*', '', ev_name).strip()
                display_name = f"{sid} {chi}".strip()
        else:
            # Clean duplicate tickers e.g. "台積電(TSM)(TSM) 財報" -> "台積電(TSM) 財報"
            display_name = re.sub(r'\((\w+)\)\(\1\)', r'(\1)', ev_name)

        def _qstr(year, q, ticker=sid):
            """Format quarter string; append fiscal year label for US stocks."""
            base = f"{year} Q{q}"
            if ticker and not str(ticker).isdigit():
                fy_year, fy_q = calendar_to_fiscal(ticker, year, q)
                if fy_year:
                    return f"{base} / Q{fy_q}FY{fy_year}"
            return base

        if ingested:
            name   = display_name
            qstr   = _qstr(ingested['year'], ingested['quarter'])
            
            # If the event is a financial report, it should NOT display audio or transcripts.
            if ev_type == "財報":
                audio = "-"
                fin   = "-"
                gt    = "-"
                pdf_cn_file = ingested.get("report_cn")
                pdf_en_file = ingested.get("report_en")
                pdf_cn, pdf_en = _format_ir_cells(sid, pdf_cn_file, pdf_en_file)
                if ingested.get("financial_tables_en"):
                    tables = _format_pdf_cell(ingested.get("financial_tables_en"), "Tables")
                    pdf_en = tables if pdf_en == "-" else f"{pdf_en} / {tables}"
            else:
                audio   = _webcast_cell(ingested)
                fin, gt = _call_transcript_cells(ingested)
                pdf_cn_file = ingested.get("pdf_cn")
                pdf_en_file = ingested.get("pdf_en")
                pdf_cn, pdf_en = _format_ir_cells(sid, pdf_cn_file, pdf_en_file)

            digest = _digest_cell(sid, ingested['year'], ingested['quarter']) if ev_type != "財報" else "-"
        else:
            # CSV-only row (not yet ingested): only include if within next 4 weeks
            try:
                ev_date = _date.fromisoformat(date)
                if not (today <= ev_date <= two_weeks):
                    continue
            except (ValueError, TypeError):
                continue
            name   = display_name
            qstr   = _qstr(exp_year, exp_q) if exp_year and exp_q else "-"
            audio  = "-"
            fin    = "-"
            gt     = "-"
            pdf_cn = "-"
            pdf_en = "-"
            digest = "-"

        merged.append({
            "sid": sid, "year": exp_year if not ingested else ingested["year"], "q": exp_q if not ingested else ingested["quarter"],
            "name": name, "quarter": qstr, "date": date, "type": ev_type,
            "audio": audio, "fin": fin, "gt": gt, "pdf_cn": pdf_cn, "pdf_en": pdf_en,
            "digest": digest,
            "mops": _get_mops_link(sid, link1),
        })

        if ev_type == "財報" and sid and not str(sid).isdigit() and ingested and (ingested.get("audio_path") or ingested.get("webcast_url") or ingested.get("pdf_cn") or ingested.get("pdf_en") or ingested.get("transcript_pdf")):
            matched_keys.add((ingested["stock_id"], ingested["year"], ingested["quarter"]))
            call_audio = _webcast_cell(ingested)
            call_fin, call_gt = _call_transcript_cells(ingested)
            call_pdf_cn, call_pdf_en = _format_ir_cells(sid, ingested.get("pdf_cn"), ingested.get("pdf_en"))
            merged.append({
                "sid": sid, "year": ingested["year"], "q": ingested["quarter"],
                "name": name, "quarter": qstr, "date": date, "type": "法說會",
                "audio": call_audio, "fin": call_fin, "gt": call_gt,
                "pdf_cn": call_pdf_cn, "pdf_en": call_pdf_en,
                "digest": _digest_cell(sid, ingested['year'], ingested['quarter']),
                "mops": _get_mops_link(sid, link1),
            })


    # Add ingested entries with no CSV event (older quarters, etc.)
    for r in rows:
        key = (r["stock_id"], r["year"], r["quarter"])
        if key in matched_keys:
            continue
        sid = r["stock_id"]
        sid_up = sid.upper()

        # Check if this entry has any local InvestorConference files or SRTs
        has_audio = bool(r.get("audio_path"))
        has_ir_cn = bool(r.get("pdf_cn"))
        has_ir_en = bool(r.get("pdf_en"))
        has_local_report_cn = bool(r.get("report_cn") and not str(r.get("report_cn")).startswith("https://"))
        has_local_report_en = bool(r.get("report_en") and not str(r.get("report_en")).startswith("https://"))

        fin_name = f"{sid}_{r['year']}_q{r['quarter']}_FIN.srt"
        gt_name = f"{sid}_{r['year']}_q{r['quarter']}_GT.srt"
        has_srt = (repo / sid / fin_name).exists() or (repo / sid / gt_name).exists()

        has_financial_report = has_local_report_cn or has_local_report_en or bool(r.get("financial_tables_en"))
        if not (has_audio or has_ir_cn or has_ir_en or has_srt or has_financial_report):
            continue

        if sid_up in KNOWN_US_STOCKS:
            en, chi = KNOWN_US_STOCKS[sid_up]
            display = f"{sid_up} {en}" + (f" {chi}" if chi else "")
        else:
            chi = tw_company_names.get(sid) or KNOWN_TW_STOCKS.get(sid, ("", ""))[1]
            display = f"{sid} {chi}".strip()
        if has_financial_report and not (has_audio or has_ir_cn or has_ir_en or has_srt):
            audio = "-"
            fin = "-"
            gt = "-"
            pdf_cn, pdf_en = _format_ir_cells(sid, r.get("report_cn"), r.get("report_en"))
            if r.get("financial_tables_en"):
                tables = _format_pdf_cell(r.get("financial_tables_en"), "Tables")
                pdf_en = tables if pdf_en == "-" else f"{pdf_en} / {tables}"
            row_type = "財報"
            digest_cell = "-"
        else:
            audio  = _webcast_cell(r)
            fin, gt = _call_transcript_cells(r)
            pdf_cn, pdf_en = _format_ir_cells(sid, r["pdf_cn"], r["pdf_en"])
            row_type = "法說會"
            digest_cell = _digest_cell(sid, r['year'], r['quarter'])
        # Compute quarter string (with fiscal year for US stocks)
        fy_year, fy_q = calendar_to_fiscal(sid, r['year'], r['quarter'])
        qstr_r = f"{r['year']} Q{r['quarter']}"
        if fy_year:
            qstr_r += f" / Q{fy_q}FY{fy_year}"
        hist_key = f"{sid}_{r['year']}_q{r['quarter']}"
        date_val = historical_dates.get(hist_key, "")

        merged.append({
            "sid": sid, "year": r["year"], "q": r["quarter"],
            "name":    display,
            "quarter": qstr_r,
            "date":    date_val,
            "type":    row_type,
            "audio":   audio,
            "fin":     fin,
            "gt":      gt,
            "pdf_cn":  pdf_cn,
            "pdf_en":  pdf_en,
            "digest":  digest_cell,
            "mops":    _get_mops_link(sid),
        })

    # Deduplicate: remove rows with identical name, quarter, date, type, audio, fin, gt, and MOPS
    unique_merged = []
    seen_rows = set()
    for row in merged:
        row_key = (row["name"], row["quarter"], row["date"], row["type"], row["audio"], row["fin"], row["gt"], row["mops"])
        if row_key not in seen_rows:
            unique_merged.append(row)
            seen_rows.add(row_key)
    merged = unique_merged

    # Sort by date descending (newest first), then by year and quarter descending; entries without date sink to the bottom
    merged.sort(key=lambda x: (x["date"] != "", x["date"] or "", x["year"] or "", x["q"] or ""), reverse=True)

    # Build README
    lines = [
        "# InvestorConference",
        "",
        "台股及美股法人說明會（法說會）音檔與投資人關係資料收錄庫。",
        "",
        "## 法說會一覽",
        "",
        "| 公司 | 季度 | 類型 | 法說日期 | 音檔 | FIN | GT | IR (TW) | IR (EN) | Digest(TW) | MOPS |",
        "|:-----|:----:|:----:|:--------:|-----:|:---:|:--:|:-------:|:-------:|:----------:|:----:|",
    ]
    for m in merged:
        lines.append(
            f"| {m['name']} | {m['quarter']} | {m['type']} | {m['date']} "
            f"| {m['audio']} | {m['fin']} | {m['gt']} | {m['pdf_cn']} | {m['pdf_en']} | {m.get('digest', '-')} | {m['mops']} |"
        )

    lines.append("")

    readme_path = repo / "README.md"
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[README] OK Updated: {readme_path}")


# ── InvestorConference Commit/Push ───────────────────────────────────────────


# ── InvestorConference Commit/Push ───────────────────────────────────────────

def sync_all_audio_durations(repo: Path) -> None:
    """Scan all directories for audio files and rebuild audio_durations.json."""
    print("\n[durations] Running full sweep of audio files...")
    durations_file = repo / "audio_durations.json"
    manifest_file = repo / "audio_manifest.json"
    
    current_durations = {}
    if durations_file.exists():
        try:
            current_durations = json.loads(durations_file.read_text(encoding="utf-8"))
        except Exception: pass

    manifest_stems = set()
    if manifest_file.exists():
        try:
            manifest_stems = set(json.loads(manifest_file.read_text(encoding="utf-8")).keys())
        except Exception: pass

    new_durations = {}
    audio_extensions = {".m4a", ".mp3", ".mp4", ".wav"}
    
    # Scan all directories, excluding hidden and tool dirs
    exclude_dirs = {"web", "tmp", "tools", "spec", "definitions", ".git", ".github", "__pycache__"}
    
    found_count = 0
    updated_count = 0
    
    # 1. Check local files
    for p in (repo / "data").iterdir():
        if p.is_dir() and p.name not in exclude_dirs:
            for audio_file in p.glob("*"):
                if audio_file.suffix.lower() in audio_extensions:
                    found_count += 1
                    key = str(audio_file.relative_to(repo)).replace("\\", "/")
                    
                    if key in current_durations:
                        new_durations[key] = current_durations[key]
                    else:
                        print(f"  [new] Probing {key}...")
                        try:
                            r = subprocess.run(
                                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)],
                                capture_output=True, text=True, timeout=10
                            )
                            if r.returncode == 0:
                                val = int(float(r.stdout.strip()))
                                new_durations[key] = val
                                updated_count += 1
                            else:
                                print(f"  ⚠ ffprobe failed for {key}")
                        except Exception as e:
                            print(f"  ⚠ Error probing {key}: {e}")

    # 2. Keep entries from current_durations if they match the manifest (even if missing locally)
    for key, val in current_durations.items():
        stem = Path(key).stem
        if stem in manifest_stems:
            new_key = key
            if not key.startswith("data/"):
                new_key = f"data/{key}"
            if new_key not in new_durations:
                new_durations[new_key] = val

    # Write back
    durations_file.write_text(
        json.dumps(new_durations, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[durations] Sweep complete. Total: {found_count}, New/Updated: {updated_count}, Cleaned: {len(current_durations) - len(new_durations) + updated_count}")


def update_audio_durations(repo: Path, audio_path: Path) -> None:
    """Update audio_durations.json with the duration of the given audio file."""
    durations_file = repo / "audio_durations.json"
    duration = probe_audio_duration(audio_path)
    if duration is None:
        print("[durations] ffprobe failed")
        return
    duration_sec = int(duration)

    durations = {}
    if durations_file.exists():
        try:
            durations = json.loads(durations_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    key = str(audio_path.relative_to(repo)).replace("\\", "/")
    durations[key] = duration_sec
    durations_file.write_text(
        json.dumps(durations, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[durations] Updated {key} -> {duration_sec}s")


def fetch_alphaspread_transcript(stock_id: str, year: str, quarter: str, stem: str, save_dir: Path) -> list[Path]:
    """
    Fetch an AlphaSpread earnings transcript via Playwright.
    Supports TW (twse) and US (nasdaq/nyse).
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[AlphaSpread] playwright not installed; skipping transcript fetch.")
        return []

    save_dir.mkdir(parents=True, exist_ok=True)
    md_path = save_dir / f"{stem}_alphaspread_transcript.md"
    if md_path.exists() and md_path.stat().st_size > 1000:
        print(f"[AlphaSpread] OK Transcript already exists locally ({md_path.name}) - skipping download.")
        return [md_path]
    outputs: list[Path] = []

    def alphaspread_quarter_labels() -> list[tuple[str, str]]:
        labels = []
        if detect_market(stock_id) == "US":
            fy_year, fy_q = calendar_to_fiscal(stock_id, year, quarter)
            if fy_year and fy_q:
                labels.append((fy_year, fy_q))
        labels.append((year, quarter))
        deduped = []
        seen = set()
        for label in labels:
            if label not in seen:
                deduped.append(label)
                seen.add(label)
        return deduped

    def extracted_transcript_date(text: str) -> datetime.date | None:
        month_names = (
            "January|February|March|April|May|June|July|August|September|October|November|December"
        )
        patterns = [
            rf"\b({month_names})\s+(\d{{1,2}}),\s+(\d{{4}})\b",
            rf"\brecorded,?\s+({month_names})\s+(\d{{1,2}}),\s+(\d{{4}})\b",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if not match:
                continue
            try:
                return datetime.datetime.strptime(
                    " ".join(match.groups()), "%B %d %Y"
                ).date()
            except ValueError:
                continue
        match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
        if match:
            try:
                return datetime.date(
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                )
            except ValueError:
                return None
        return None

    def transcript_date_matches_target(text: str) -> tuple[bool, str]:
        event_date = extracted_transcript_date(text)
        if event_date is None:
            return True, "no transcript date found"
        target_year, month_min, month_max = _quarter_date_window(year, quarter)
        if event_date.year == int(target_year) and month_min <= event_date.month <= month_max:
            return True, event_date.isoformat()
        return (
            False,
            f"{event_date.isoformat()} outside expected {target_year}-{month_min:02d}..{target_year}-{month_max:02d}",
        )

    # Build potential URLs
    if detect_market(stock_id) == "US":
        symbol = stock_id.lower()
        bases = [
            f"https://www.alphaspread.com/security/nasdaq/{symbol}",
            f"https://www.alphaspread.com/security/nyse/{symbol}",
            f"https://www.alphaspread.com/stock/nasdaq/{symbol}",
            f"https://www.alphaspread.com/stock/nyse/{symbol}",
            f"https://www.alphaspread.com/stocks/nasdaq/{symbol}",
            f"https://www.alphaspread.com/stocks/nyse/{symbol}",
        ]
    else:
        bases = [
            f"https://www.alphaspread.com/security/twse/{stock_id}/investor-relations/earnings-call",
            f"https://www.alphaspread.com/security/twse/{stock_id}",
            f"https://www.alphaspread.com/stock/twse/{stock_id}",
            f"https://www.alphaspread.com/stocks/twse/{stock_id}",
        ]

    urls = []
    for b in bases:
        for label_year, label_q in alphaspread_quarter_labels():
            if "investor-relations" in b:
                urls.append(f"{b}/q{label_q}-{label_year}")
            else:
                urls.append(f"{b}/transcripts/q{label_q}-{label_year}")
                urls.append(f"{b}/earnings-calls/q{label_q}-{label_year}")
                urls.append(f"{b}/earnings-call/q{label_q}-{label_year}")
                urls.append(f"{b}/investor-relations/earnings-call/q{label_q}-{label_year}")

    def clean_noise(text: str) -> str:
        # Locate the real transcript start
        # Common AlphaSpread markers for the actual dialog
        markers = ["Earnings Call Transcript", "\nOperator\n", "\nOperator:\n"]
        start_idx = 0
        for m in markers:
            idx = text.find(m)
            if idx != -1:
                # If it's Operator, keep the word "Operator"
                if "Operator" in m:
                    start_idx = idx
                else:
                    start_idx = idx + len(m)
                break
        
        if start_idx > 0:
            text = text[start_idx:]
            
        # Remove footer noise
        if "OTHER EARNINGS CALLS" in text:
            text = text.split("OTHER EARNINGS CALLS")[0]
        
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        success = False
        
        for url in urls:
            print(f"[AlphaSpread] Trying: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
                
                # Try to find and click "Open Transcript" or "Transcript" tab if it exists
                try:
                    transcript_btn = page.get_by_text("Open Transcript", exact=False)
                    if transcript_btn.is_visible():
                        print("  [AlphaSpread] Clicking 'Open Transcript' button...")
                        transcript_btn.click()
                        page.wait_for_timeout(2000)
                except: pass

                body_text = page.locator("body").inner_text(timeout=10000)
                content = clean_noise(body_text)
                
                # More robust check: true transcript usually contains "Operator" or speaker names
                has_transcript_markers = any(x in content for x in ["Operator", "Question-and-Answer", "Prepared Remarks"])
                is_404 = any(x in content for x in ["Oops!", "can't find that page", "Page not found"])
                
                date_ok, date_reason = transcript_date_matches_target(content)
                if len(content) > 2000 and not is_404 and has_transcript_markers and date_ok: # Increased length requirement for full transcript
                    header = f"[METADATA]\nSource: {url}\nGenerated-At: {datetime.date.today().isoformat()}\n---\n\n"
                    md_path.write_text(header + content, encoding="utf-8")
                    print(f"[AlphaSpread] OK Saved transcript -> {md_path.name} ({len(content)} chars)")
                    success = True
                    outputs.append(md_path)
                    break
                else:
                    if is_404:
                        reason = "404 detected"
                    elif not has_transcript_markers:
                        reason = "transcript markers missing; page appears to be a summary"
                    elif not date_ok:
                        reason = f"wrong transcript date ({date_reason})"
                    else:
                        reason = f"content too short or summary only ({len(content)} chars)"
                    print(f"[AlphaSpread] ⚠ {reason} for {url} - trying next...")
            except Exception as e:
                print(f"[AlphaSpread] FAILED Failed for {url}: {str(e)[:100]}")
        
        browser.close()

    return outputs


def fetch_yahoo_transcript(yahoo_url: str, stem: str, save_dir: Path) -> list[Path]:
    """
    Fetch a Yahoo Finance earnings transcript via browser rendering.

    Saves:
      - {stem}_yahoo_transcript.md   : text transcript extracted from rendered page
      - {stem}_yahoo_transcript.html : rendered HTML snapshot
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[Yahoo] playwright not installed; skipping transcript fetch.")
        return []

    save_dir.mkdir(parents=True, exist_ok=True)
    md_path = save_dir / f"{stem}_yahoo_transcript.md"
    html_path = save_dir / f"{stem}_yahoo_transcript.html"
    outputs: list[Path] = []

    def normalize_text(text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"

    def extract_transcript_text(body: str) -> str:
        marker = "Powered by Yahoo Scout"
        idx = body.find(marker)
        if idx != -1:
            body = body[idx + len(marker):].strip()
        else:
            marker = "Powered by Quartr"
            idx = body.find(marker)
            if idx != -1:
                body = body[idx:].strip()
        body = re.sub(r"\nADVERTISEMENT\n", "\n", body)
        body = re.sub(r"\n{3,}", "\n\n", body)
        return normalize_text(body)

    print(f"[Yahoo] Fetching transcript: {yahoo_url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(yahoo_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(5000)
            body_text = page.locator("body").inner_text(timeout=15000)
            html = page.content()
        except PlaywrightTimeoutError as e:
            browser.close()
            print(f"[Yahoo] Timeout loading transcript page: {e}")
            return []
        finally:
            browser.close()

    transcript_md = extract_transcript_text(body_text)
    if transcript_md:
        md_path.write_text(transcript_md, encoding="utf-8")
        print(f"[Yahoo] Saved transcript markdown -> {md_path}")
        outputs.append(md_path)
    if html:
        html_path.write_text(html, encoding="utf-8")
        print(f"[Yahoo] Saved rendered HTML -> {html_path}")
        outputs.append(html_path)

    return outputs


def commit_push_files(stock_id: str, year: str, quarter: str,
                      audio_path: Path, pdf_paths: list = None,
                      extra_paths: list = None) -> str | None:
    """
    Move the downloaded audio (and optional PDFs) into InvestorConference/data/<stock_id>/,
    commit (git-lfs for .m4a), push, then remove local whisper-sandbox copies.

    Returns the new audio path inside InvestorConference, or None on failure.
    """
    repo = INVESTOR_CONFERENCE_REPO
    if not repo.exists():
        print(f"[git] InvestorConference repo not found at {repo}")
        return None

    target_dir = repo / "data" / stock_id
    target_dir.mkdir(parents=True, exist_ok=True)

    def git(*args):
        result = subprocess.run(
            ["git", "-C", str(repo)] + list(args),
            capture_output=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            # If nothing to commit, treat as success (returncode 1 is common for git commit with no changes)
            if "nothing to commit" in err or "nothing to commit" in result.stdout:
                return True
            if err:
                print(f"[git] {' '.join(args)}: {err}")
        return result.returncode == 0

    # Find and remove old audio formats with same stem
    stem = audio_path.stem
    for old_audio in target_dir.glob(f"{stem}.*"):
        if old_audio.suffix.lower() in [".mp3", ".m4a", ".wav"] and \
           old_audio.suffix.lower() != audio_path.suffix.lower():
            print(f"[git] Removing old audio format: {old_audio.name}")
            git("rm", str(old_audio.relative_to(repo)))
            if old_audio.exists():
                old_audio.unlink()

    # Move audio
    target_audio = target_dir / audio_path.name
    shutil.move(str(audio_path), str(target_audio))
    print(f"[git] Moved -> {target_audio}")
    # git("add", str(target_audio.relative_to(repo)))  # Audio now on GDrive

    # Move PDFs / transcript / other extras
    for pdf in (pdf_paths or []):
        target_pdf = target_dir / pdf.name
        shutil.move(str(pdf), str(target_pdf))
        print(f"[git] Moved -> {target_pdf}")
        git("add", str(target_pdf.relative_to(repo)))
    for extra in (extra_paths or []):
        target_extra = target_dir / extra.name
        if extra.resolve() != target_extra.resolve():
            shutil.move(str(extra), str(target_extra))
            print(f"[git] Moved -> {target_extra}")
        else:
            print(f"[git] Using existing file -> {target_extra}")
        git("add", str(target_extra.relative_to(repo)))

    # Update audio_durations.json
    update_audio_durations(repo, target_audio)
    git("add", "audio_durations.json")

    # Upload to GitHub Releases and update manifest
    release_url, _manifest_path = upload_to_gdrive_and_update_manifest(repo, stock_id, target_audio)
    git("add", "audio_manifest.json")

    # Persist checksum metadata after the final release URL is known.
    update_audio_metadata(repo, target_audio, release_url=release_url)
    git("add", "audio_metadata.json")

    # Regenerate README.md and stage it
    update_readme()
    git("add", "README.md")

    extras = []
    if pdf_paths:
        extras.append(f"{len(pdf_paths)} PDF(s)")
    if extra_paths:
        extras.append(f"{len(extra_paths)} extra file(s)")
    extras_str = f" + {', '.join(extras)}" if extras else ""
    msg = (f"feat: add {stock_id} {year} Q{quarter} earnings call audio (audio on GDrive){extras_str}\n\n"
           f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>")
    if not git("commit", "-m", msg):
        print(f"[git] commit failed")
        return str(target_audio)

    print(f"[git] Committed. Pushing (LFS upload may take a moment) ...")
    if git("push", "origin", "main"):
        print(f"[git] OK Pushed to InvestorConference/{stock_id}/")
    else:
        print(f"[git] push failed - committed locally, push manually.")

    return str(target_audio)


# ── Main Ingestion Function ───────────────────────────────────────────────────

def ingest_earnings_audio(stock_id: str, year: str, quarter: str,
                          auto_push: bool = False) -> str | None:
    """
    Main entry point. Pipeline per market:

    Taiwan:
      1. Company IR site -> webcast-eqs.com login -> Playwright HLS intercept -> yt-dlp
      2. MOPS (公開資訊觀測站) -> irconference MP4 or company-linked YouTube URL -> yt-dlp

    US:
      1. Known IR portal -> company-linked YouTube ID -> yt-dlp

    If auto_push=True: on success, moves audio to InvestorConference repo,
    commits via git-lfs, pushes, and removes local copy.
    """
    save_dir = INVESTOR_CONFERENCE_REPO / "tmp"
    save_dir.mkdir(exist_ok=True)

    market    = detect_market(stock_id)
    eng_name, chi_name = get_company_name(stock_id)

    print(f"=== Smart Ingestion v5.0 ===")
    print(f"Stock  : {stock_id} ({eng_name} / {chi_name})")
    print(f"Market : {market}")
    print(f"Target : {year} Q{quarter}")
    print(f"Push   : {'yes -> InvestorConference' if auto_push else 'no (local only)'}")
    print()

    output_path = save_dir / f"{stock_id}_{year}_q{quarter}.m4a"
    _conf_date: list = [None]   # mutable cell so inner functions can write it

    def verify_audio_length(path: Path, min_minutes: float = 10.0) -> bool:
        """Verify audio is at least min_minutes long using ffprobe."""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(path)],
                capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            )
            duration_sec = float(r.stdout.strip())
            minutes = duration_sec / 60
            print(f"[Verify] Audio length: {minutes:.1f} min", end="")
            if minutes < min_minutes:
                print(f" FAILED TOO SHORT (expected >={min_minutes:.0f} min) - rejecting")
                path.unlink(missing_ok=True)
                return False
            print(f" OK")
            return True
        except Exception as e:
            print(f"[Verify] ffprobe failed: {e} - skipping length check")
            return True  # don't reject if ffprobe unavailable

    def done() -> str:
        """Called after every successful audio download - also downloads PDFs."""
        print(f"\nOK SUCCESS: {output_path}")
        if not verify_audio_length(output_path):
            return None
        stem = f"{stock_id}_{year}_q{quarter}"
        duplicate = find_duplicate_audio(INVESTOR_CONFERENCE_REPO, output_path, stem)
        if duplicate:
            print(f"[checksum] Duplicate audio detected: {output_path.name} matches {duplicate}")
            print("[checksum] Rejecting this download to avoid registering audio under the wrong quarter.")
            output_path.unlink(missing_ok=True)
            return None
        pdf_paths = download_pdfs(stock_id, year, quarter, save_dir)
        extra_paths = []
        
        # --- Get External Transcripts ---
        transcript_dir = INVESTOR_CONFERENCE_REPO / "data" / stock_id
        
        # 1. AlphaSpread (Primary & Automatic)
        as_paths = fetch_alphaspread_transcript(stock_id, year, quarter, stem, transcript_dir)
        extra_paths.extend(as_paths)

        # 2. Yahoo (Secondary & Manual Map)
        if not as_paths:
            yahoo_url = KNOWN_YAHOO_TRANSCRIPTS_BY_QUARTER.get((stock_id, year, quarter))
            if yahoo_url:
                extra_paths.extend(fetch_yahoo_transcript(yahoo_url, stem, transcript_dir))

        # MOPS PDFs - use conf_date discovered during audio scraping
        if _conf_date[0]:
            mops_pdfs = download_mops_pdfs(
                stock_id, _conf_date[0], year, quarter, save_dir)
            pdf_paths = pdf_paths + [p for p in mops_pdfs if p not in pdf_paths]
            
        if auto_push:
            # Commit even if only audio exists (removed the strict pdf/extra check)
            pushed = commit_push_files(
                stock_id, year, quarter, output_path, pdf_paths, extra_paths
            )
            return pushed or str(output_path)
        return str(output_path)

    if output_path.exists():
        print(f"[Cache] Already downloaded: {output_path}")
        # Still resolve conf_date for MOPS PDF lookup
        if detect_market(stock_id) == "TW":
            direct_ir_url = KNOWN_TW_DIRECT_IR.get(stock_id)
            if direct_ir_url:
                _, conf_date = scrape_tw_direct_ir(stock_id, direct_ir_url, year, quarter)
                _conf_date[0] = conf_date
            else:
                hinted_conf_date = None
                if stock_id == "2454":
                    pw_ir_url, hinted_conf_date = discover_mediatek_hinet_page(year, quarter)
                else:
                    pw_ir_url = resolve_tw_playwright_ir_url(stock_id, year, quarter)
                if pw_ir_url:
                    _, conf_date = scrape_playwright_direct_ir(stock_id, pw_ir_url, year, quarter)
                    _conf_date[0] = conf_date or hinted_conf_date
        return done()

    target_url = None

    # ── Taiwan Pipeline ───────────────────────────────────────────────────────
    if market == "TW":

        direct_audio_url = KNOWN_TW_DIRECT_AUDIO_BY_QUARTER.get((stock_id, year, quarter))
        if direct_audio_url:
            print(f"\n[Direct-Audio] Downloading quarter-specific URL: {direct_audio_url[:80]}...")
            if download_audio(direct_audio_url, output_path, no_check_cert=True):
                return done()
            print(f"[Direct-Audio] yt-dlp failed. Falling back...")

        # Special handling for Novatek (3034) which uses YouTube with predictable titles
        if stock_id == "3034":
            search_query = f"ytsearch:Novatek {year} Q{quarter} Investor Conference"
            print(f"\n[Novatek-Search] Searching YouTube: {search_query}")
            if download_audio(search_query, output_path):
                # Try to get conf_date for MOPS PDF lookup
                try:
                    r = subprocess.run(
                        ["yt-dlp", "--get-description", "--no-warnings", search_query],
                        capture_output=True, text=True, timeout=10
                    )
                    # Look for date like 2025/11/06 or 2026/02/06
                    m = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', r.stdout)
                    if m:
                        _conf_date[0] = "".join(m.groups())
                except Exception:
                    pass
                return done()

        # Step 0a: Company direct IR site with hosted MP4 (simple requests, e.g. STI Liferay)
        direct_ir_url = KNOWN_TW_DIRECT_IR.get(stock_id)
        if direct_ir_url:
            mp4_url, conf_date = scrape_tw_direct_ir(stock_id, direct_ir_url, year, quarter)
            if mp4_url:
                _conf_date[0] = conf_date   # store for MOPS PDF lookup in done()
                print(f"\n[Direct-IR] Downloading: {mp4_url[:80]}...")
                if download_audio(mp4_url, output_path, no_check_cert=True):
                    return done()
                print(f"[Direct-IR] yt-dlp failed. Falling back...")

        # Step 0b: JS-rendered IR site (Playwright intercept, e.g. quantatw.com for 廣達)
        hinted_conf_date = None
        if stock_id == "2454":
            pw_ir_url, hinted_conf_date = discover_mediatek_hinet_page(year, quarter)
        else:
            pw_ir_url = resolve_tw_playwright_ir_url(stock_id, year, quarter)
        if pw_ir_url:
            mp4_url, conf_date = scrape_playwright_direct_ir(stock_id, pw_ir_url, year, quarter)
            if mp4_url:
                _conf_date[0] = conf_date or hinted_conf_date
                print(f"\n[PW-IR] Downloading: {mp4_url[:80]}...")
                if download_audio(mp4_url, output_path, no_check_cert=True):
                    return done()
                print(f"[PW-IR] yt-dlp failed. Falling back...")

        # Step 1: Company IR site -> webcast-eqs.com -> Playwright HLS intercept
        ir_url = KNOWN_TW_IR.get(stock_id)
        if ir_url:
            webcast_url = scrape_tw_ir(stock_id, ir_url, year, quarter)
            if webcast_url:
                hls_url = extract_webcast_eqs_stream(webcast_url)
                if hls_url:
                    print(f"\n[HLS] Downloading: {hls_url}")
                    if download_audio(hls_url, output_path, no_check_cert=True):
                        return done()
                    print(f"[HLS] yt-dlp failed on HLS stream.")
                else:
                    print(f"[webcast-eqs] Could not extract HLS. Falling back...")

        # Step 2: MOPS via Playwright (intercepts ajax_t100sb07_1 XHR)
        mops_data = scrape_mops_playwright(stock_id, year, quarter)
        if mops_data.get("video_url"):
            print(f"\n[MOPS-PW] Downloading video: {mops_data['video_url']}")
            if download_audio(mops_data["video_url"], output_path, no_check_cert=True):
                # Preserve PDFs discovered in the same MOPS response. The replay date
                # can differ from the PDF attachment date, so relying only on
                # download_mops_pdfs(conf_date) can miss valid decks.
                for fn, pdf_url in mops_data.get("pdfs", []):
                    lang = "ir_en" if fn[len(stock_id)+8] == "E" else "ir"
                    dest = save_dir / f"{stock_id}_{year}_q{quarter}_{lang}.pdf"
                    if dest.exists():
                        print(f"[MOPS-PW] PDF already exists: {dest.name}")
                        continue
                    try:
                        r = requests.get(pdf_url, headers={"User-Agent": UA,
                            "Referer": "https://mopsov.twse.com.tw/"}, timeout=30, verify=False)
                        if r.status_code == 200 and r.content[:4] == b"%PDF":
                            dest.write_bytes(r.content)
                            print(f"[MOPS-PW] OK {dest.name} ({len(r.content)//1024}KB)")
                        else:
                            print(f"[MOPS-PW] PDF invalid response: {fn} status={r.status_code}")
                    except Exception as e:
                        print(f"[MOPS-PW] PDF download failed: {e}")

                # Extract conf_date from irconference URL filename
                m = re.search(r'_(\d{8})_', mops_data["video_url"])
                if m:
                    _conf_date[0] = m.group(1)
                return done()
        elif mops_data.get("pdfs"):
            # No video but has PDFs - download them directly
            print(f"[MOPS-PW] No video, but found {len(mops_data['pdfs'])} PDF(s) - downloading.")
            for fn, pdf_url in mops_data["pdfs"]:
                # Infer lang suffix from filename (M=中文, E=英文)
                lang = "ir_en" if fn[len(stock_id)+8] == "E" else "ir"
                dest = save_dir / f"{stock_id}_{year}_q{quarter}_{lang}.pdf"
                if not dest.exists():
                    try:
                        r = requests.get(pdf_url, headers={"User-Agent": UA,
                            "Referer": "https://mopsov.twse.com.tw/"}, timeout=30, verify=False)
                        if r.status_code == 200 and r.content[:4] == b"%PDF":
                            dest.write_bytes(r.content)
                            print(f"[MOPS-PW] OK {dest.name} ({len(r.content)//1024}KB)")
                    except Exception as e:
                        print(f"[MOPS-PW] PDF download failed: {e}")
        else:
            # Fallback: original requests-based MOPS scraper
            mops_url = scrape_mops_tw(stock_id, year, quarter)
            if mops_url:
                target_url = mops_url

    # ── US Pipeline ───────────────────────────────────────────────────────────
    else:
        # Check quarter-specific direct URL first (choruscall VOD / YouTube etc.)
        direct_us_url = KNOWN_US_DIRECT_BY_QUARTER.get((stock_id.upper(), year, quarter))
        if direct_us_url:
            target_url = direct_us_url
        else:
            ir_url = KNOWN_US_IR.get(stock_id.upper())
            if ir_url:
                target_url = scrape_ir_site(ir_url, year, quarter)

    # ── Direct URL Download (MOPS / IR scraper result) ────────────────────────
    if target_url:
        print(f"\n[Download] {target_url}")
        if download_audio(target_url, output_path):
            return done()

    pdf_paths = download_pdfs(stock_id, year, quarter, save_dir)
    if pdf_paths:
        print(f"\nOK SUCCESS: found {len(pdf_paths)} official PDF material(s) for {stock_id} {year} Q{quarter}; audio remains unavailable.")
        if auto_push:
            commit_push_files(stock_id, year, quarter, output_path, pdf_paths, [])
        return str(pdf_paths[0])

    print(f"\nFAILED FAILED: Could not find audio or official PDF materials for {stock_id} {year} Q{quarter}")
    return None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart Ingestion v5.0 - Earnings Call Audio Downloader"
    )
    parser.add_argument("stock_id", nargs="?", help="Stock ID (e.g. 2357, NVDA)")
    parser.add_argument("year",     nargs="?", help="Year (e.g. 2025)")
    parser.add_argument("quarter",  nargs="?", help="Quarter (1-4)")
    parser.add_argument(
        "--push", action="store_true",
        help="After download, commit + push to InvestorConference repo",
    )
    parser.add_argument(
        "--update-readme", action="store_true",
        help="Regenerate README.md from repo state + raw_event_upcoming_earnings.csv, then exit",
    )
    parser.add_argument(
        "--sync-durations", action="store_true",
        help="Sync audio_durations.json with all audio files in the repo, then exit",
    )
    parser.add_argument(
        "--auto-todo", action="store_true",
        help="Scan raw_event_upcoming_earnings.csv and ingest any missing past events",
    )
    args = parser.parse_args()

    if args.auto_todo:
        ingest_from_todo(auto_push=args.push)
    elif args.sync_durations:
        sync_all_audio_durations(INVESTOR_CONFERENCE_REPO)
    elif args.update_readme:
        update_readme()
    elif args.stock_id and args.year and args.quarter:
        ingest_earnings_audio(args.stock_id, args.year, args.quarter,
                              auto_push=args.push)
    else:
        parser.print_help()
