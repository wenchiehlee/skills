#!/usr/bin/env python3
"""find_sources.py — 法說會資料來源解析 (skill-investorconference-digest)

依 SOP 優先序解析指定公司/季度的資料來源檔案，列出前一季檔案供財測、承諾與措辭比對。
可用 --json 輸出 machine-readable manifest，降低 agent 選錯季度或來源的風險。

用法:
    python find_sources.py 2357
    python find_sources.py 2357 2026 q1
    python find_sources.py 2357 2026 q1 --json
    python find_sources.py 2357 --root <InvestorConference 路徑>
"""
import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUARTER_RE = re.compile(r"^(?P<sid>[0-9A-Za-z]+)_(?P<year>\d{4})_q(?P<q>[1-4])")
SOURCE_SPEC = [
    ("_GT.srt", "人工校正字幕 (Ground Truth)", "字幕第一優先", "primary_transcript"),
    ("_FIN.srt", "Whisper 自動轉錄字幕", "字幕第二優先", "fallback_transcript"),
    (".md", "音檔逐字稿 (含時間戳)", "字幕第三優先", "plain_transcript"),
    ("_ir.md", "中文法說會簡報 (PDF→MD)", "財務數據第一優先", "ir_files"),
    ("_ir_en.md", "英文法說會簡報 (PDF→MD)", "財務數據補充", "ir_files"),
    ("_qa.md", "官方 Q&A 紀錄 (PDF→MD)", "Q&A 分析必讀", "qa_files"),
    ("_alphaspread_transcript.md", "第三方逐字稿 (AlphaSpread)", "補充來源", "supplemental_files"),
    ("_yahoo_transcript.md", "第三方逐字稿 (Yahoo Finance)", "補充來源", "supplemental_files"),
    ("_alphamemo_transcript.md", "第三方會議紀要 (AlphaMemo)", "補充來源", "supplemental_files"),
]
KEY_SUFFIXES = ("_GT.srt", "_ir.md", "_qa.md")


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "audio_durations.json").exists() or (
            (p / "README.md").exists() and any(d.is_dir() and d.name.isdigit() for d in p.iterdir())
        ):
            return p
    return start


def list_quarters(company_dir: Path, sid: str):
    quarters = set()
    for f in company_dir.iterdir():
        m = QUARTER_RE.match(f.name)
        if m and m.group("sid") == sid:
            quarters.add((int(m.group("year")), int(m.group("q"))))
    return sorted(quarters)


def prev_quarter(year: int, q: int):
    return (year - 1, 4) if q == 1 else (year, q - 1)


def resolve(company_dir: Path, sid: str, year: int, q: int):
    base = f"{sid}_{year}_q{q}"
    rows = []
    for suffix, desc, role, bucket in SOURCE_SPEC:
        path = company_dir / f"{base}{suffix}"
        rows.append({
            "name": path.name,
            "path": str(path),
            "description": desc,
            "role": role,
            "bucket": bucket,
            "exists": path.exists(),
        })
    return rows


def aliases(company_dir: Path, sid: str):
    names = set()
    skip_re = re.compile(r"^(?:<!--|#|##|>|•?\s*TODO|\d{1,2} [A-Za-z]+ \d{4}$)")
    noise_re = re.compile(r"投資人說明會|法人說明會|法說會|財報|Disclaimer|議程|PAGE|OCR|Results|Financial", re.I)
    for f in company_dir.glob(f"{sid}_*_ir*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")[:3000]
        except Exception:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[:20]:
            if skip_re.search(line):
                continue
            english = re.search(r"\b([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,4},?\s+(?:Inc\.|Corporation|Corp\.|Company|Co\.,? Ltd\.?|Limited))\b", line)
            if english:
                names.add(english.group(1).strip())
            chinese = re.search(r"([\u4e00-\u9fff]{2,12})(?:\d{4}年|第[一二三四1-4]季|股份有限公司|法人說明會)", line)
            if chinese:
                names.add(chinese.group(1).strip())
        for line in lines[:8]:
            if skip_re.search(line) or noise_re.search(line):
                continue
            candidate = line.lstrip("• ").strip()
            simple_name = (
                re.fullmatch(r"[\u4e00-\u9fff]{2,12}", candidate)
                or re.fullmatch(r"[A-Z][A-Za-z&., -]{1,38}", candidate)
            )
            if 2 <= len(candidate) <= 40 and simple_name and not re.search(r"\d{4}|[Qq][1-4]|[一二三四1-4]季", candidate):
                names.add(candidate)
                break
        if re.search(r"\bASUS\b|ASUSTeK", text, flags=re.I):
            names.add("ASUS")
        for m in re.finditer(r"(?:公司名稱|Company Name)[:：\s]+([^\n|]{2,40})", text):
            candidate = m.group(1).strip()
            if not re.search(r"risk|uncertain|statement|forward", candidate, flags=re.I):
                names.add(candidate)
    return sorted(names)


def build_manifest(root: Path, sid: str, year: int, q: int, quarters):
    company_dir = root / "data" / sid
    rows = resolve(company_dir, sid, year, q)
    py, pq = prev_quarter(year, q)
    previous_rows = resolve(company_dir, sid, py, pq) if (py, pq) in quarters else []

    def existing(bucket):
        return [r["path"] for r in rows if r["bucket"] == bucket and r["exists"]]

    missing = [r["name"] for r in rows if not r["exists"]]
    key_missing = [r["name"] for r in rows if not r["exists"] and r["name"].endswith(KEY_SUFFIXES)]
    manifest = {
        "stock_id": sid,
        "quarter": f"{year}_q{q}",
        "year": year,
        "q": q,
        "root": str(root),
        "primary_transcript": next(iter(existing("primary_transcript")), None),
        "fallback_transcript": next(iter(existing("fallback_transcript")), None),
        "plain_transcript": next(iter(existing("plain_transcript")), None),
        "ir_files": existing("ir_files"),
        "qa_files": existing("qa_files"),
        "supplemental_files": existing("supplemental_files"),
        "previous_quarter": {
            "quarter": f"{py}_q{pq}",
            "files": [r["path"] for r in previous_rows if r["exists"]],
        },
        "available_quarters": [f"{y}_q{n}" for y, n in quarters],
        "missing_files": missing,
        "key_missing_files": key_missing,
        "company_aliases": aliases(company_dir, sid),
        "source_rows": rows,
    }
    return manifest


def print_human(manifest):
    sid, year, q, root = manifest["stock_id"], manifest["year"], manifest["q"], manifest["root"]
    print(f"\n== {sid} {year} Q{q} 資料來源 (root: {root}) ==")
    for r in manifest["source_rows"]:
        mark = "✅" if r["exists"] else "❌"
        print(f"  {mark} {r['name']:<45} {r['description']}｜{r['role']}")

    print(f"\n== 前一季 ({manifest['previous_quarter']['quarter'].replace('_q', ' Q')})，供財測/承諾/措辭追蹤使用 ==")
    if manifest["previous_quarter"]["files"]:
        for f in manifest["previous_quarter"]["files"]:
            print(f"  ✅ {Path(f).name}")
    else:
        print("  ❌ 無前一季資料 → 報告第十節應載明資料不足")

    print("\n== 該公司所有可用季度 ==")
    print("  " + ", ".join(qtr.replace("_q", " Q") for qtr in manifest["available_quarters"]))
    if manifest["key_missing_files"]:
        print(f"\n[提醒] 關鍵檔案缺漏: {', '.join(manifest['key_missing_files'])}（依 SOP 評估是否回報 issue）")


def main():
    ap = argparse.ArgumentParser(description="法說會資料來源解析")
    ap.add_argument("stock_id")
    ap.add_argument("year", nargs="?", type=int)
    ap.add_argument("quarter", nargs="?", help="q1~q4")
    ap.add_argument("--root", type=Path, default=None, help="InvestorConference repo 根目錄")
    ap.add_argument("--json", action="store_true", help="輸出 machine-readable manifest JSON")
    args = ap.parse_args()

    root = (args.root or find_repo_root(Path.cwd())).resolve()
    company_dir = root / "data" / args.stock_id
    if not company_dir.is_dir():
        print(f"[錯誤] 找不到公司目錄: {company_dir}", file=sys.stderr)
        sys.exit(2)

    quarters = list_quarters(company_dir, args.stock_id)
    if not quarters:
        print(f"[錯誤] {company_dir} 內無任何季度檔案", file=sys.stderr)
        sys.exit(2)

    if args.year and args.quarter:
        year, q = args.year, int(str(args.quarter).lstrip("qQ"))
    else:
        year, q = quarters[-1]
        if not args.json:
            print(f"[資訊] 未指定季度，採用最新一季: {year} Q{q}")

    manifest = build_manifest(root, args.stock_id, year, q, quarters)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print_human(manifest)


if __name__ == "__main__":
    main()
