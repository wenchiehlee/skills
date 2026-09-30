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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
compare_references.py — 自動生成 TAIEX.TW issue 比對報告

Usage:
    python scripts/compare_references.py --issue 7
    python scripts/compare_references.py --symbol GOOGL --period "2026 Q1"
    python scripts/compare_references.py --issue 7 --close   # 比對後自動關閉 issue
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── paths ────────────────────────────────────────────────────────────────────
ROOT = Path(find_repo_root())
DATA_DIR = ROOT / "data"
REPORTS  = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

CS_RAW   = DATA_DIR / "ConceptStocks"
INCOME   = CS_RAW  / "raw_conceptstock_company_income.csv"
SEGMENTS = CS_RAW  / "raw_conceptstock_company_quarterly_segments.csv"
SUPPS    = DATA_DIR / "earnings_supplements.csv"

FB_REPO   = "wenchiehlee-money/Facebook.Fetch"
TAIEX_REPO = "wenchiehlee-money/TAIEX.TW"

# ── LLM client ───────────────────────────────────────────────────────────────
WORKSPACE = ROOT.parent
LLM_PATH  = WORKSPACE / "llm"
if str(LLM_PATH) not in sys.path:
    sys.path.insert(0, str(LLM_PATH))

try:
    from dotenv import load_dotenv
    load_dotenv(LLM_PATH / ".env", override=False)
    load_dotenv(ROOT / ".env", override=True)
    from llm import LLMClient
except ImportError:
    LLMClient = None


# ── GitHub API helpers ────────────────────────────────────────────────────────
def _gh_token() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("REPO_FILE_SYNC_WENCHIEHLEE_MONEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REPO_FILE_SYNC_WENCHIEHLEE_MONEY",
           os.environ.get("GITHUB_TOKEN", ""))


def _gh_get(url: str) -> dict:
    token = _gh_token()
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_issue(number: int) -> dict:
    import subprocess
    r = subprocess.run(
        ["gh", "issue", "view", str(number), "--repo", TAIEX_REPO, "--json", "title,body"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if r.returncode != 0:
        raise RuntimeError(f"gh issue view failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def parse_issue_body(body: str) -> dict:
    def extract(label: str) -> str:
        m = re.search(rf"###\s*{re.escape(label)}\s*\n+([^\n#]+)", body)
        return m.group(1).strip() if m else ""
    return {
        "symbol":    extract("股票代號"),
        "file_path": extract("貼文路徑（Facebook.Fetch repo）"),
        "period":    extract("財報期間"),
    }


def fetch_md_content(file_path: str) -> str:
    encoded = urllib.parse.quote(file_path, safe="/")
    url = f"https://api.github.com/repos/{FB_REPO}/contents/{encoded}"
    data = _gh_get(url)
    return base64.b64decode(data["content"]).decode("utf-8")


def download_image(image_url: str) -> Path | None:
    if not image_url:
        return None
    tmp = Path("/tmp") if Path("/tmp").exists() else Path(os.environ.get("TEMP", "."))
    fname = tmp / "compare_ref_image.jpg"
    try:
        req = urllib.request.Request(image_url,
              headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            fname.write_bytes(r.read())
        return fname
    except Exception as e:
        print(f"  [warn] image download failed: {e}")
        return None


# ── LLM extraction ────────────────────────────────────────────────────────────
EXTRACTION_PROMPT = """
你是財務數據提取助手。從以下 Facebook 財報貼文（文字 + 可能附圖）中，
提取所有財務關鍵數字，以 **JSON** 格式回傳，欄位如下：

{
  "symbol": "股票代號（如 GOOGL）",
  "fiscal_year": 2026,
  "period": "Q1",
  "revenue_actual_b": 109.9,          // 實際營收（十億美元）
  "revenue_estimate_b": 107.2,        // 分析師預期營收（十億美元）
  "revenue_surprise_pct": 2.5,        // 營收超標 %
  "revenue_yoy_pct": 22.0,            // 營收年增 %
  "eps_actual": 5.11,                 // 實際 EPS（美元）
  "eps_estimate": 2.63,               // 分析師預期 EPS
  "eps_surprise_pct": 94.0,           // EPS 超標 %
  "eps_yoy_pct": 82.0,                // EPS 年增 %
  "gross_margin_pct": null,           // 毛利率 %（找不到填 null）
  "operating_margin_pct": 36.1,       // 營業利益率 %
  "net_margin_pct": null,             // 淨利率 %
  "segments": [                       // 業務分部（可空陣列）
    {"name": "Google Cloud", "revenue_b": 20.03, "yoy_pct": 63.0, "pct_of_total": 18.0}
  ],
  "guidance": {                       // 下一季/全年展望（可空物件）
    "next_q_revenue_low_b": null,
    "next_q_revenue_high_b": null,
    "capex_b": null,
    "notes": ""
  },
  "notes": "任何需要注意的備註（如包含一次性收益等）"
}

只回傳 JSON，不要任何說明文字。
---
貼文內容：
{CONTENT}
"""


def extract_with_llm(md_text: str, image_path: Path | None) -> dict | None:
    if not LLMClient:
        print("  [warn] LLMClient not available, skipping LLM extraction")
        return None

    # Strip frontmatter and badge
    content = re.sub(r"^---\n.*?\n---\n", "", md_text, flags=re.DOTALL)
    content = re.sub(r"\[(?:📌|🔄|✅)[^\]]+\]\([^)]+\)\s*$", "", content).strip()
    # Limit length
    content = content[:6000]

    prompt = EXTRACTION_PROMPT.replace("{CONTENT}", content)

    # Attach image if available
    messages = None
    if image_path and image_path.exists():
        img_b64 = base64.b64encode(image_path.read_bytes()).decode()
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": img_b64,
                }},
            ]}
        ]

    try:
        client = LLMClient(app_name="TAIEX_Compare", providers=["codex"])
        # Attach image by embedding base64 in prompt if image available
        if image_path and image_path.exists():
            img_b64 = base64.b64encode(image_path.read_bytes()).decode()
            full_prompt = prompt + f"\n\n[IMAGE_BASE64_JPEG:{img_b64[:100]}...]"
        else:
            full_prompt = prompt
        raw = client.generate(full_prompt, max_tokens=2048)

        raw = re.sub(r"```(?:json)?\n?", "", raw).strip().rstrip("`")
        return json.loads(raw)
    except Exception as e:
        print(f"  [warn] LLM extraction failed: {e}")
        return None


def extract_with_regex(md_text: str, symbol: str, period: str) -> dict:
    """Regex fallback — covers the standard FinGuider post format."""
    text = md_text

    def first_float(pattern: str) -> float | None:
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                return None
        return None

    fy_match = re.search(r"(20\d\d)", period)
    fy = int(fy_match.group(1)) if fy_match else None
    q_match = re.search(r"Q([1-4])", period, re.IGNORECASE)
    q = f"Q{q_match.group(1)}" if q_match else period

    rev = first_float(r"營收.*?(\d[\d,.]*).*?億美元")
    rev_b = rev / 10 if rev and rev > 10 else rev      # 億 → B

    rev_est = first_float(r"(?:預期|預測|共識).*?(\d[\d,.]*).*?億")
    rev_est_b = rev_est / 10 if rev_est and rev_est > 10 else rev_est

    eps = first_float(r"EPS[^。]*?(\d[\d.]*)美元")
    eps_est = first_float(r"(?:預期|共識|預測)[^。]*?(\d[\d.]*)美元")

    yoy = first_float(r"年增.*?(\d+)%")
    om  = first_float(r"營益率.*?(\d+[\d.]*)%")
    gm  = first_float(r"毛利率.*?(\d+[\d.]*)%")

    # Segments
    segs = []
    for m in re.finditer(r"[「【]?([A-Za-z一-鿿 &]+)[」】]?\s*(?:營收)?\s*(\d[\d,.]*)億.*?(?:年增|YoY)\s*([+\-]?\d+)%", text):
        seg_rev = float(m.group(2).replace(",", "")) / 10
        segs.append({"name": m.group(1).strip(),
                     "revenue_b": seg_rev,
                     "yoy_pct": float(m.group(3))})

    return {
        "symbol": symbol,
        "fiscal_year": fy,
        "period": q,
        "revenue_actual_b": rev_b,
        "revenue_estimate_b": rev_est_b,
        "revenue_yoy_pct": yoy,
        "eps_actual": eps,
        "eps_estimate": eps_est,
        "operating_margin_pct": om,
        "gross_margin_pct": gm,
        "segments": segs,
        "guidance": {},
        "notes": "",
    }


# ── Internal data lookup ──────────────────────────────────────────────────────
def _fy_period(period_str: str) -> tuple[int | None, str]:
    fy_m = re.search(r"(20\d\d)", period_str)
    q_m  = re.search(r"Q([1-4])", period_str, re.IGNORECASE)
    fy   = int(fy_m.group(1)) if fy_m else None
    q    = f"Q{q_m.group(1)}" if q_m else period_str
    return fy, q


def get_internal_income(symbol: str, fiscal_year: int, period: str) -> dict:
    if not INCOME.exists():
        return {}
    df = pd.read_csv(INCOME)
    mask = ((df["symbol"] == symbol) &
            (df["fiscal_year"].astype(str) == str(fiscal_year)) &
            (df["period"] == period) &
            (df["source"] == "SEC"))
    rows = df[mask].sort_values("end_date", ascending=False)
    if rows.empty:
        return {}
    r = rows.iloc[0]
    return {
        "revenue_b":        float(r["total_revenue"]) / 1e9 if pd.notna(r.get("total_revenue")) else None,
        "gross_margin_pct": round(float(r["gross_margin"]) * 100, 2) if pd.notna(r.get("gross_margin")) else None,
        "operating_margin_pct": round(float(r["operating_margin"]) * 100, 2) if pd.notna(r.get("operating_margin")) else None,
        "net_margin_pct":   round(float(r["net_margin"]) * 100, 2) if pd.notna(r.get("net_margin")) else None,
        "eps":              float(r["eps"]) if pd.notna(r.get("eps")) else None,
        "non_gaap_eps":     float(r["non_gaap_eps"]) if pd.notna(r.get("non_gaap_eps")) else None,
    }


def get_internal_supplements(symbol: str, fiscal_year: int, period: str) -> dict:
    if not SUPPS.exists():
        return {}
    df = pd.read_csv(SUPPS)
    mask = ((df["symbol"] == symbol) &
            (df["fiscal_year"].astype(int) == fiscal_year) &
            (df["period"] == period))
    rows = df[mask]
    if rows.empty:
        return {}
    r = rows.iloc[0]
    out = {}
    for col in ["revenue_estimate", "revenue_surprise_pct",
                "non_gaap_eps", "eps_estimate", "eps_surprise_pct"]:
        v = r.get(col)
        if pd.notna(v) and str(v).strip():
            out[col] = float(v)
    return out


def get_internal_segments(symbol: str, fiscal_year: int, period: str) -> list[dict]:
    if not SEGMENTS.exists():
        return []
    df = pd.read_csv(SEGMENTS)
    mask = ((df["symbol"] == symbol) &
            (df["fiscal_year"].astype(str) == str(fiscal_year)) &
            (df["quarter"] == period))
    rows = df[mask]
    if rows.empty:
        return []
    total = rows["revenue"].astype(float).sum()
    out = []
    for _, r in rows.iterrows():
        rev = float(r["revenue"])
        out.append({"name": r["segment_name"],
                    "revenue_b": round(rev / 1e9, 2),
                    "pct": round(rev / total * 100, 1) if total > 0 else None})
    return out


# ── Comparison table builder ──────────────────────────────────────────────────
def _match(ref_val, int_val, tol: float = 0.02) -> str:
    """Return ✅/⚠️/❌ based on relative difference."""
    if ref_val is None and int_val is None:
        return "—"
    if ref_val is None:
        return "⚠️ ref缺"
    if int_val is None:
        return "❌ 內部缺"
    if abs(ref_val) < 1e-9:
        return "✅" if abs(int_val) < 1e-9 else "⚠️"
    diff = abs(ref_val - int_val) / abs(ref_val)
    if diff <= tol:
        return "✅"
    if diff <= 0.05:
        return "⚠️"
    return "❌"


def build_comparison_table(ref: dict, internal_income: dict,
                            internal_segs: list, internal_supps: dict) -> str:
    symbol = ref.get("symbol", "?")
    period = f"{ref.get('fiscal_year', '?')} {ref.get('period', '?')}"
    ts = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"## {symbol} {period} 比對報告（自動生成 {ts}）",
        "",
        "**參考來源**：Facebook.Fetch FinGuider 貼文（文字 + 附圖）",
        "**內部來源**：SEC EDGAR + earnings_supplements.csv",
        "",
        "---",
        "",
        "### 📊 損益表核心指標",
        "",
        "| 指標 | 參考值 | 內部值 | 狀態 |",
        "|------|--------|--------|------|",
    ]

    # Revenue
    ref_rev = ref.get("revenue_actual_b")
    int_rev = internal_income.get("revenue_b")
    lines.append(f"| 營收 | {_fmt_b(ref_rev)} | {_fmt_b(int_rev)} | {_match(ref_rev, int_rev)} |")

    # Revenue estimate
    ref_est = ref.get("revenue_estimate_b")
    int_est = internal_supps.get("revenue_estimate")
    int_est_b = int_est / 1e9 if int_est else None
    lines.append(f"| 營收預期 | {_fmt_b(ref_est)} | {_fmt_b(int_est_b)} | {_match(ref_est, int_est_b)} |")

    # Revenue YoY
    ref_yoy = ref.get("revenue_yoy_pct")
    lines.append(f"| 營收 YoY | {_fmt_pct(ref_yoy)} | — | {'✅' if ref_yoy else '❌ ref缺'} |")

    # EPS
    ref_eps = ref.get("eps_actual")
    int_eps = internal_income.get("non_gaap_eps") or internal_income.get("eps")
    lines.append(f"| EPS（報告） | {_fmt_v(ref_eps)} | {_fmt_v(int_eps)} | {_match(ref_eps, int_eps)} |")

    # EPS estimate
    ref_eps_est = ref.get("eps_estimate")
    int_eps_est = internal_supps.get("eps_estimate")
    lines.append(f"| EPS 預期 | {_fmt_v(ref_eps_est)} | {_fmt_v(int_eps_est)} | {_match(ref_eps_est, int_eps_est)} |")

    # Gross margin
    ref_gm = ref.get("gross_margin_pct")
    int_gm = internal_income.get("gross_margin_pct")
    lines.append(f"| 毛利率 | {_fmt_pct(ref_gm)} | {_fmt_pct(int_gm)} | {_match(ref_gm, int_gm, tol=0.5)} |")

    # Operating margin
    ref_om = ref.get("operating_margin_pct")
    int_om = internal_income.get("operating_margin_pct")
    lines.append(f"| 營業利益率 | {_fmt_pct(ref_om)} | {_fmt_pct(int_om)} | {_match(ref_om, int_om, tol=0.5)} |")

    # Notes
    if ref.get("notes"):
        lines += ["", f"> ⚠️ {ref['notes']}", ""]

    # Segments
    ref_segs = ref.get("segments", [])
    if ref_segs or internal_segs:
        lines += ["", "---", "", "### 🥧 業務分部", "",
                  "| 分部 | 參考金額 | 內部金額 | 狀態 |",
                  "|------|---------|---------|------|"]
        int_seg_map = {s["name"]: s for s in internal_segs}
        seen = set()
        for seg in ref_segs:
            name = seg["name"]
            seen.add(name)
            ref_rv = seg.get("revenue_b")
            int_s  = int_seg_map.get(name)
            int_rv = int_s["revenue_b"] if int_s else None
            lines.append(f"| {name} | {_fmt_b(ref_rv)} | {_fmt_b(int_rv)} | {_match(ref_rv, int_rv)} |")
        for name, s in int_seg_map.items():
            if name not in seen:
                lines.append(f"| {name} | ❌ ref缺 | {_fmt_b(s['revenue_b'])} ({s.get('pct','?')}%) | ⚠️ |")

    # Guidance
    g = ref.get("guidance", {})
    if g and (g.get("next_q_revenue_low_b") or g.get("notes")):
        lines += ["", "---", "", "### 📅 展望", ""]
        if g.get("next_q_revenue_low_b"):
            lo, hi = g.get("next_q_revenue_low_b"), g.get("next_q_revenue_high_b")
            lines.append(f"- Q4 營收指引：${lo}B ~ ${hi}B（未來期，不比對）")
        if g.get("capex_b"):
            lines.append(f"- 資本支出：${g['capex_b']}B")
        if g.get("notes"):
            lines.append(f"- {g['notes']}")

    return "\n".join(lines)


def _fmt_b(v) -> str:
    return f"${v:.2f}B" if v is not None else "❌ 缺"


def _fmt_pct(v) -> str:
    return f"{v:.1f}%" if v is not None else "❌ 缺"


def _fmt_v(v) -> str:
    return f"{v:.2f}" if v is not None else "❌ 缺"


# ── Post to GitHub issue ──────────────────────────────────────────────────────
def post_issue_comment(issue_number: int, body: str):
    import subprocess
    result = subprocess.run(
        ["gh", "issue", "comment", str(issue_number),
         "--repo", TAIEX_REPO, "--body", body],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  Posted comment: {result.stdout.strip()}")
    else:
        print(f"  [error] {result.stderr.strip()}")


def close_issue(issue_number: int, comment: str = "✅ 比對完成，已自動關閉。"):
    import subprocess
    subprocess.run(
        ["gh", "issue", "close", str(issue_number),
         "--repo", TAIEX_REPO, "--comment", comment],
        capture_output=True, text=True
    )
    print(f"  Closed issue #{issue_number}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run(issue_number: int | None = None,
        symbol: str = "", period: str = "",
        file_path: str = "",
        auto_close: bool = False):

    # 1. Resolve symbol / period / file_path
    if issue_number:
        print(f"Fetching issue #{issue_number}...")
        issue = fetch_issue(issue_number)
        parsed = parse_issue_body(issue.get("body", ""))
        symbol    = symbol    or parsed["symbol"]
        file_path = file_path or parsed["file_path"]
        period    = period    or parsed["period"]

    if not symbol or not file_path:
        print("Error: need --issue or both --symbol and --file-path")
        return

    fy, q = _fy_period(period)
    print(f"Symbol: {symbol}  Period: {fy} {q}")

    # 2. Fetch .md content
    print("Fetching .md from Facebook.Fetch...")
    md_text = fetch_md_content(file_path)

    # 3. Download image
    img_url = ""
    m = re.search(r"image_url:\s*\"?([^\"'\n]+)\"?", md_text)
    if m:
        img_url = m.group(1).strip()
    image_path = download_image(img_url) if img_url else None

    # 4. Extract reference numbers (LLM → regex fallback)
    print("Extracting reference numbers...")
    ref = None
    if LLMClient:
        ref = extract_with_llm(md_text, image_path)
    if not ref:
        print("  Using regex fallback")
        ref = extract_with_regex(md_text, symbol, period)
    if not ref.get("symbol"):
        ref["symbol"] = symbol
    if not ref.get("fiscal_year"):
        ref["fiscal_year"] = fy
    if not ref.get("period"):
        ref["period"] = q

    # 5. Query internal data
    print("Querying internal CSVs...")
    int_income = get_internal_income(symbol, fy, q)
    int_segs   = get_internal_segments(symbol, fy, q)
    int_supps  = get_internal_supplements(symbol, fy, q)

    if not int_income:
        print(f"  [warn] No internal income data for {symbol} {fy} {q}")

    # 6. Build comparison table
    table = build_comparison_table(ref, int_income, int_segs, int_supps)

    # 7. Save to reports/
    fname = REPORTS / f"{symbol.lower()}_{fy}{q}_comparison.md"
    fname.write_text(table, encoding="utf-8")
    print(f"  Saved: {fname}")
    print()
    print(table)

    # 8. Post to issue / close
    if issue_number:
        post_issue_comment(issue_number, table)
        if auto_close:
            # Check if any ❌ in table
            has_errors = "❌ 內部缺" in table
            if has_errors:
                print("  Has missing internal data — not auto-closing")
            else:
                close_issue(issue_number)


def main():
    parser = argparse.ArgumentParser(description="Generate comparison table for earnings-tag issue")
    parser.add_argument("--issue",     type=int,   help="GitHub issue number")
    parser.add_argument("--symbol",    default="", help="Stock symbol (e.g. GOOGL)")
    parser.add_argument("--period",    default="", help='Report period (e.g. "2026 Q1")')
    parser.add_argument("--file-path", default="", help="Facebook.Fetch file path")
    parser.add_argument("--close",     action="store_true", help="Auto-close issue if no missing data")
    args = parser.parse_args()

    run(issue_number=args.issue,
        symbol=args.symbol,
        period=args.period,
        file_path=args.file_path,
        auto_close=args.close)


if __name__ == "__main__":
    main()