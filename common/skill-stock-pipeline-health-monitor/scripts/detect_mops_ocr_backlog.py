"""
detect_mops_ocr_backlog.py
---------------------------
Composite-skill helper for skill-stock-pipeline-health-monitor.

Table 2's MOPS row (mops_pdf_sync) reports an `ocr_needed_count` aggregate but
this skill does not run OCR itself -- that belongs to skill-mops-fetch (see the
Delegation Map in SKILL.md). This script reads the synced summary, lists the
specific pending files by scanning the sibling MOPS repo's downloads/ tree
(same TODO:OCR marker skill-mops-fetch's own refine_pending_ocr.py uses), and
prints the exact command to delegate the fix.
"""

import csv
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MOPS_HEALTH_SUMMARY_CSV = os.path.join(ROOT, "data", "MOPS", "mops_health_summary.csv")
MOPS_REPO_DIR = os.path.normpath(os.path.join(ROOT, "..", "MOPS"))
MOPS_DOWNLOADS_DIR = os.path.join(MOPS_REPO_DIR, "downloads")


def load_ocr_needed_count():
    if not os.path.exists(MOPS_HEALTH_SUMMARY_CSV):
        return None
    with open(MOPS_HEALTH_SUMMARY_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None
    try:
        return int(rows[-1].get("ocr_needed_count") or 0)
    except (TypeError, ValueError):
        return None


def find_pending_files():
    """Scan the sibling MOPS repo's downloads/<company>/*.md for TODO:OCR
    markers. Returns [] (not an error) if the MOPS repo isn't checked out
    alongside biztrends.TW at this NAS location."""
    if not os.path.isdir(MOPS_DOWNLOADS_DIR):
        return None
    pending = []
    for company_id in sorted(os.listdir(MOPS_DOWNLOADS_DIR)):
        company_dir = os.path.join(MOPS_DOWNLOADS_DIR, company_id)
        if not os.path.isdir(company_dir):
            continue
        for name in sorted(os.listdir(company_dir)):
            if not name.endswith(".md"):
                continue
            path = os.path.join(company_dir, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    count = f.read().count("TODO:OCR")
            except OSError:
                continue
            if count:
                pending.append((os.path.relpath(path, MOPS_REPO_DIR), count))
    return pending


def main():
    ocr_needed = load_ocr_needed_count()
    if ocr_needed is None:
        print("找不到 data/MOPS/mops_health_summary.csv 或欄位缺失，無法判斷 OCR 待補數量。")
        return 1

    print(f"=== MOPS PDF→MD OCR 待補清單 ===")
    print(f"Dashboard 表二回報 ocr_needed_count = {ocr_needed}")

    if ocr_needed == 0:
        print("目前沒有待補 OCR 的 PDF，不需要委派。")
        return 0

    pending = find_pending_files()
    if pending is None:
        print(
            f"\n本機找不到 MOPS repo（預期路徑：{MOPS_DOWNLOADS_DIR}），"
            "無法列出逐檔明細；直接委派 skill-mops-fetch 即可，它會自己重新掃描。"
        )
    else:
        print(f"\n本機掃描到 {len(pending)} 個 Markdown 檔案仍有 TODO:OCR 標記：")
        for rel_path, count in pending:
            print(f"- {rel_path} (TODO:OCR x{count})")
        if len(pending) != ocr_needed:
            print(
                f"\n注意：本機掃描到的檔案數（{len(pending)}）跟 Dashboard 回報的 "
                f"ocr_needed_count（{ocr_needed}）對不上——可能是本機 MOPS repo 還沒同步到最新，"
                "或健康度統計口徑不同（例如涵蓋本機沒有的股票）。委派前建議先在 MOPS repo 內 `git pull`。"
            )

    print(
        "\n建議委派 skill-mops-fetch 批次修復（於 MOPS repo 執行）：\n"
        "  python skills/skill-mops-fetch/scripts/refine_pending_ocr.py --dry-run   # 先確認清單\n"
        "  python skills/skill-mops-fetch/scripts/refine_pending_ocr.py             # 實際呼叫 Mac-mini OCR API 修補"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
