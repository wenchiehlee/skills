#!/usr/bin/env python3
"""find_sources.py — 法說會資料來源解析 (skill-conference-digest)

依 SOP 優先序解析指定公司/季度的資料來源檔案，並列出前一季檔案供財測比對。

用法:
    python find_sources.py 2357                # 自動選最新一季
    python find_sources.py 2357 2026 q1        # 指定季度
    python find_sources.py 2357 --root <InvestorConference 路徑>
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUARTER_RE = re.compile(r"^(?P<sid>[0-9A-Za-z]+)_(?P<year>\d{4})_q(?P<q>[1-4])")

# (檔尾, 說明, 角色)
SOURCE_SPEC = [
    ("_GT.srt", "人工校正字幕 (Ground Truth)", "字幕第一優先"),
    ("_FIN.srt", "Whisper 自動轉錄字幕", "字幕第二優先"),
    (".md", "音檔逐字稿 (含時間戳)", "字幕第三優先"),
    ("_ir.md", "中文法說會簡報 (PDF→MD)", "財務數據第一優先"),
    ("_ir_en.md", "英文法說會簡報 (PDF→MD)", "財務數據補充"),
    ("_qa.md", "官方 Q&A 紀錄 (PDF→MD)", "Q&A 分析必讀"),
    ("_alphaspread_transcript.md", "第三方逐字稿", "補充來源"),
]


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
    for suffix, desc, role in SOURCE_SPEC:
        path = company_dir / f"{base}{suffix}"
        rows.append((path.name, desc, role, path.exists()))
    return rows


def main():
    ap = argparse.ArgumentParser(description="法說會資料來源解析")
    ap.add_argument("stock_id")
    ap.add_argument("year", nargs="?", type=int)
    ap.add_argument("quarter", nargs="?", help="q1~q4")
    ap.add_argument("--root", type=Path, default=None, help="InvestorConference repo 根目錄")
    args = ap.parse_args()

    root = (args.root or find_repo_root(Path.cwd())).resolve()
    company_dir = root / args.stock_id
    if not company_dir.is_dir():
        print(f"[錯誤] 找不到公司目錄: {company_dir}")
        sys.exit(2)

    quarters = list_quarters(company_dir, args.stock_id)
    if not quarters:
        print(f"[錯誤] {company_dir} 內無任何季度檔案")
        sys.exit(2)

    if args.year and args.quarter:
        year, q = args.year, int(str(args.quarter).lstrip("qQ"))
    else:
        year, q = quarters[-1]
        print(f"[資訊] 未指定季度，採用最新一季: {year} Q{q}")

    print(f"\n== {args.stock_id} {year} Q{q} 資料來源 (root: {root}) ==")
    missing_key = []
    for name, desc, role, exists in resolve(company_dir, args.stock_id, year, q):
        mark = "✅" if exists else "❌"
        print(f"  {mark} {name:<45} {desc}｜{role}")
        if not exists and ("GT" in name or "_ir.md" in name or "_qa.md" in name):
            missing_key.append(name)

    py, pq = prev_quarter(year, q)
    print(f"\n== 前一季 ({py} Q{pq})，供「與前次財測比較」使用 ==")
    if (py, pq) in quarters:
        for name, desc, _, exists in resolve(company_dir, args.stock_id, py, pq):
            if exists:
                print(f"  ✅ {name:<45} {desc}")
    else:
        print("  ❌ 無前一季資料 → 報告第十節應載明「本次資料不足，無法比較前次財測」")

    print(f"\n== 該公司所有可用季度 ==")
    print("  " + ", ".join(f"{y} Q{n}" for y, n in quarters))

    if missing_key:
        print(f"\n[提醒] 關鍵檔案缺漏: {', '.join(missing_key)}（依 SOP 第 7 節評估是否回報 issue）")


if __name__ == "__main__":
    main()
