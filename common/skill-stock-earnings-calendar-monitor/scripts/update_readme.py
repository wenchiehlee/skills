
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
"""Update README.md with earnings schedule and SVG report status."""
import csv
import glob
import os
import re
import subprocess
from datetime import date, timedelta

ROOT = find_repo_root()
EARNINGS_CSV = os.path.join(ROOT, "data", "raw_event_upcoming_earnings.csv")
INCOME_CSV = os.path.join(ROOT, "data", "ConceptStocks", "raw_conceptstock_company_income.csv")
SEGMENTS_CSV = os.path.join(ROOT, "data", "ConceptStocks", "raw_conceptstock_company_quarterly_segments.csv")
TW_PERF_CSV = os.path.join(ROOT, "data", "Python-Actions.GoodInfo.Analyzer", "raw_performance1.csv")
# Curated TW watchlist from biztrends.TW (Get觀察名單.py -> StockID_TWSE_TPEX_focus.csv).
# Used to filter TW earnings events down to companies actually tracked there;
# US tickers are unaffected (biztrends.TW's watchlist is TW-only).
TW_WATCHLIST_CSV = os.path.join(ROOT, "data", "biztrends.TW", "StockID_TWSE_TPEX_focus.csv")
# US ticker allowlist -- ConceptStocks' own curated company metadata.
US_WATCHLIST_CSV = os.path.join(ROOT, "data", "ConceptStocks", "raw_conceptstock_company_metadata.csv")
VISUALS_DIR = os.path.join(ROOT, "output", "visuals")
README_PATH = os.path.join(ROOT, "README.md")

SECTION_START = "<!-- EARNINGS_TABLE_START -->"
SECTION_END = "<!-- EARNINGS_TABLE_END -->"

THUMB_WIDTH = 1000


def get_committed_svgs() -> set:
    try:
        result = subprocess.run(
            ["git", "ls-files", "output/visuals/"],
            cwd=ROOT, capture_output=True, text=True
        )
        return {
            os.path.basename(p.strip())
            for p in result.stdout.splitlines()
            if p.strip().endswith(".svg")
        }
    except Exception:
        return set()


_TW_QUARTER_ENDS = {"Q1": "-03-31", "Q2": "-06-30", "Q3": "-09-30", "Q4": "-12-31"}


def _tw_quarter_to_date(quarter: str) -> str:
    """Convert '2026Q1' → '2026-03-31'."""
    m = re.match(r"(\d{4})Q([1-4])", quarter)
    if not m:
        return ""
    return m.group(1) + _TW_QUARTER_ENDS[f"Q{m.group(2)}"]


def load_data_index() -> dict:
    """Return {ticker: latest_end_date} from income + segments + tw_raw CSVs."""
    index = {}

    if os.path.exists(INCOME_CSV):
        with open(INCOME_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("symbol", "")
                end_date = row.get("end_date", "")
                period = row.get("period", "")
                if ticker and end_date and re.match(r"Q[1-4]", period):
                    if ticker not in index or end_date > index[ticker]:
                        index[ticker] = end_date

    if os.path.exists(SEGMENTS_CSV):
        with open(SEGMENTS_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("symbol", "")
                end_date = row.get("end_date", "")
                if ticker and end_date:
                    if ticker not in index or end_date > index[ticker]:
                        index[ticker] = end_date

    if os.path.exists(TW_PERF_CSV):
        with open(TW_PERF_CSV, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("stock_code", "").strip()
                quarter = row.get("季度", "").strip()
                if not ticker or not quarter:
                    continue
                end_date = _tw_quarter_to_date(quarter)
                if end_date and (ticker not in index or end_date > index[ticker]):
                    index[ticker] = end_date

    return index


def data_status(ticker: str, earnings_date: str, data_index: dict) -> str:
    """Return a data-readiness label for the ticker."""
    latest = data_index.get(ticker)
    if not latest:
        return "❌ 無資料"

    # Expected quarter end: ~3 months before earnings date
    try:
        ed = date.fromisoformat(earnings_date)
        expected = (ed - timedelta(days=60)).isoformat()  # at least 2 months before report
        if latest >= expected:
            return f"✅ 資料至 {latest}"
        else:
            return f"⚠️ 資料至 {latest}"
    except Exception:
        return f"❓ {latest}"


def extract_ticker(event_name: str) -> str:
    # US stocks: (GOOGL) / TW stocks: (2330)
    m = re.search(r"\(([A-Z]{1,5}|\d{4,6})\)", event_name)
    return m.group(1) if m else ""


def extract_period(event_name: str) -> str:
    m = re.search(r"(\d{4}\s+Q\d|FY\d{4}\s+Q\d)", event_name)
    return m.group(1) if m else ""


def find_svgs(ticker: str, suffix: str = "finguider_report.svg") -> list:
    pattern = os.path.join(VISUALS_DIR, f"{ticker}*{suffix}")
    return sorted(glob.glob(pattern))


def _svg_period(fname: str) -> str:
    """Extract period from SVG filename, e.g. 'MSFT_codex_cli_2026_Q1_...' → '2026_Q1'."""
    m = re.search(r"(\d{4}_Q\d|FY\d{4}_Q\d)", fname)
    return m.group(1) if m else ""


def _normalize_period(period: str) -> str:
    """Normalize earnings period to match SVG period format.
    '2026 Q1' → '2026_Q1', 'FY2026 Q2' → 'FY2026_Q2'
    """
    return period.strip().replace(" ", "_")


def svg_cells(ticker: str, committed: set, entry_period: str = "", suffix: str = "finguider_report.svg") -> tuple:
    """Return (thumbnail_cell, status_cell).
    Only show SVGs whose filename period matches entry_period.
    """
    svgs = find_svgs(ticker, suffix)
    if not svgs:
        return ("—", None)

    norm_entry = _normalize_period(entry_period)
    thumbs, links = [], []
    for path in svgs:
        fname = os.path.basename(path)
        svg_per = _svg_period(fname)

        # Skip SVGs that belong to a different period. Also skip (rather than
        # blindly show) when we know which period this row wants but can't tell
        # which period the file actually is -- a malformed filename (e.g. a
        # missing "_" between year and quarter) previously fell through this
        # check and got shown on every row for that ticker regardless of period.
        if norm_entry and norm_entry != svg_per:
            continue

        # Extract label part
        pattern = rf"{ticker}_(.+)_{suffix.replace('.', r'\.')}"
        m = re.match(pattern, fname)
        label = m.group(1) if m else "report"
        rel = os.path.relpath(path, ROOT).replace("\\", "/")

        if fname in committed:
            thumbs.append(f'<img src="{rel}" width="{THUMB_WIDTH}" alt="{label}"/>')
            links.append(f"✅ [{label}]({rel})")
        else:
            links.append(f"📝 {label} *(未提交)*")

    if not thumbs and not links:
        return ("—", None)

    thumb_cell = " ".join(thumbs) if thumbs else "—"
    status_cell = " · ".join(links) if links else None
    return (thumb_cell, status_cell)


def load_tw_watchlist() -> set:
    """TW tickers curated in biztrends.TW (Get觀察名單.py -> StockID_TWSE_TPEX_focus.csv).
    Empty set (no filtering) if the snapshot isn't present."""
    if not os.path.exists(TW_WATCHLIST_CSV):
        return set()
    with open(TW_WATCHLIST_CSV, newline="", encoding="utf-8-sig") as f:
        return {row["代號"].strip() for row in csv.DictReader(f) if row.get("代號")}


def load_us_watchlist() -> set:
    """US tickers curated in ConceptStocks' raw_conceptstock_company_metadata.csv.
    Empty set (no filtering) if the file isn't present."""
    if not os.path.exists(US_WATCHLIST_CSV):
        return set()
    with open(US_WATCHLIST_CSV, newline="", encoding="utf-8-sig") as f:
        return {
            row["Ticker"].strip()
            for row in csv.DictReader(f)
            if row.get("Ticker") and row["Ticker"].strip() != "-"
        }


def load_earnings() -> list:
    if not os.path.exists(EARNINGS_CSV):
        return []
    tw_watchlist = load_tw_watchlist()
    us_watchlist = load_us_watchlist()
    rows = {}
    with open(EARNINGS_CSV, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("類別") not in ("財報公告", "法說會"):
                continue
            if row.get("子類別") not in ("美股", "台股"):
                continue
            ticker = extract_ticker(row["事件名稱"])
            if not ticker:
                continue
            # Restrict coverage to each market's curated watchlist:
            # TW -> biztrends.TW 專注名單, US -> ConceptStocks company metadata.
            if row.get("子類別") == "台股" and tw_watchlist and ticker not in tw_watchlist:
                continue
            if row.get("子類別") == "美股" and us_watchlist and ticker not in us_watchlist:
                continue
            dt = row.get("開始日期", "")
            period = extract_period(row["事件名稱"])
            key = (ticker, period, row.get("類別", ""))
            if key not in rows or dt > rows[key]["date"]:
                rows[key] = {
                    "date": dt,
                    "name": row["事件名稱"],
                    "ticker": ticker,
                    "period": period,
                    "market": row.get("子類別", ""),
                    "category": row.get("類別", ""),
                }
    return sorted(rows.values(), key=lambda r: r["date"])


try:
    import scripts.assembler_finguider as ag
except ModuleNotFoundError:
    import assembler_finguider as ag


def build_table(earnings: list, committed: set, data_index: dict) -> str:
    today_dt = date.today()
    cutoff = (today_dt + timedelta(weeks=3)).isoformat()
    today = today_dt.isoformat()
    past_start = (today_dt - timedelta(weeks=16)).isoformat()
    earnings = [e for e in earnings if past_start <= e["date"] <= cutoff]
    earnings = sorted(earnings, key=lambda r: r["date"], reverse=True)

    lines = [
        "| 財報日期 | 市場 | 公司（Ticker） | 期別 / 類別 | 縮圖 | 營收縮圖 |",
        "|:---:|:---:|:---|:---:|:---:|:---:|",
    ]
    for e in earnings:
        dt = e["date"]
        is_future = dt > today
        category = e.get("category", "財報公告")
        if category == "法說會":
            icon = "🗣️" if is_future else "💬"
        else:
            icon = "📅" if is_future else "📋"
        company = re.sub(r"\s*\([^)]+\).*", "", e["name"]).strip()
        ticker = e["ticker"]
        period = e["period"]
        norm_period = period.replace(" ", "")
        period_display = f"{period}<br/>{category}"
        market = "🇺🇸" if e.get("market") == "美股" else "🇹🇼"
        
        # Data Readiness Check (Verification)
        is_lagging = False
        if not is_future:  # Only verify for past or today's events
            try:
                # We use the norm_period (e.g. 2026Q1) to verify
                stock_data = ag.get_company_data(ticker, target_period=norm_period)
                ready, _ = ag._is_data_ready(ticker, stock_data, target_period=norm_period)
                if not ready:
                    is_lagging = True
            except:
                pass

        # Column 5: Finguider Report
        thumb, _ = svg_cells(ticker, committed, period, suffix="finguider_report.svg")
        if thumb == "—" and is_lagging:
            thumb = "`⚠️ 數據滯後`"

        # Column 6: Revenue History
        rev_thumb, _ = svg_cells(ticker, committed, period, suffix="revenue_history.svg")
        if rev_thumb == "—" and is_lagging:
            rev_thumb = "`⚠️ 數據滯後`"

        lines.append(f"| {icon} {dt} | {market} | {company} ({ticker}) | {period_display} | {thumb} | {rev_thumb} |")

    return "\n".join(lines)


def update_readme(table: str, count: int):
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    section = f"{SECTION_START}\n{table}\n{SECTION_END}"

    if SECTION_START in content:
        content = re.sub(
            rf"{re.escape(SECTION_START)}.*?{re.escape(SECTION_END)}",
            section,
            content,
            flags=re.DOTALL,
        )
    else:
        content = content.rstrip() + f"\n\n## 財報行事曆 & 報告狀態\n\n{section}\n"

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"README.md updated ({count} earnings entries)")


if __name__ == "__main__":
    earnings = load_earnings()
    if not earnings:
        print("No earnings data found — check data/raw_event_upcoming_earnings.csv")
    else:
        committed = get_committed_svgs()
        data_index = load_data_index()
        table = build_table(earnings, committed, data_index)
        update_readme(table, len(earnings))