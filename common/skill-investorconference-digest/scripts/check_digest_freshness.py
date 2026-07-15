#!/usr/bin/env python3
"""check_digest_freshness.py — digest 覆蓋率掃描 (skill-conference-digest)

掃描 InvestorConference 全庫，列出「已有法說會資料但尚未產出 digest 報告」的季度，
方便批次補做。digest 報告位置: Conference-digest/{sid}_{year}_q{n}_digest.md

用法:
    python check_digest_freshness.py [--root <InvestorConference 路徑>] [--srt-only]

選項:
    --srt-only   只列出「有字幕（GT 或 FIN）」的季度（有字幕才具備完整分析條件）
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUARTER_RE = re.compile(r"^(?P<sid>[0-9A-Za-z]+)_(?P<year>\d{4})_q(?P<q>[1-4])")


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "audio_durations.json").exists():
            return p
    return start


def main():
    ap = argparse.ArgumentParser(description="digest 覆蓋率掃描")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--srt-only", action="store_true",
                    help="只列出有字幕 (GT/FIN) 的季度")
    args = ap.parse_args()

    root = (args.root or find_repo_root(Path.cwd())).resolve()
    digest_dir = root / "Conference-digest"

    rows = []  # (sid, year, q, has_srt, has_ir, has_digest)
    for company in sorted(root.iterdir()):
        if not (company.is_dir() and re.fullmatch(r"[0-9A-Z]{2,6}", company.name)):
            continue
        sid = company.name
        quarters = {}
        for f in company.iterdir():
            m = QUARTER_RE.match(f.name)
            if not m or m.group("sid") != sid:
                continue
            key = (int(m.group("year")), int(m.group("q")))
            info = quarters.setdefault(key, {"srt": False, "ir": False})
            if f.name.endswith(("_GT.srt", "_FIN.srt")):
                info["srt"] = True
            if f.name.endswith("_ir.md"):
                info["ir"] = True
        for (year, q), info in quarters.items():
            digest = digest_dir / f"{sid}_{year}_q{q}_digest.md"
            rows.append((sid, year, q, info["srt"], info["ir"], digest.exists()))

    missing = [r for r in rows
               if not r[5] and (r[3] or (not args.srt_only and r[4]))]
    done = [r for r in rows if r[5]]

    print(f"root: {root}")
    print(f"已產出 digest: {len(done)} 季｜待產出: {len(missing)} 季\n")

    if done:
        print("== 已完成 ==")
        for sid, year, q, *_ in sorted(done):
            print(f"  ✅ {sid} {year} Q{q}")

    if missing:
        print("\n== 待產出（有資料、無 digest）==")
        print(f"  {'公司':<8}{'季度':<10}{'字幕':<6}{'簡報MD':<8}")
        for sid, year, q, has_srt, has_ir, _ in sorted(missing, key=lambda r: (-r[1], -r[2], r[0])):
            print(f"  {sid:<8}{year} Q{q:<6}{'✅' if has_srt else '❌':<5}{'✅' if has_ir else '❌':<7}")
        print("\n提示: 字幕+簡報俱全者優先分析；僅簡報無字幕者無法做 Q&A 分析（第九節）。")
    else:
        print("\n所有具備資料的季度皆已產出 digest。")


if __name__ == "__main__":
    main()
