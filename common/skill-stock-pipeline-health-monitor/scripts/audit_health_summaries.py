"""
audit_health_summaries.py
--------------------------
Composite-skill helper for skill-stock-pipeline-health-monitor.

Does NOT fetch or regenerate any *_health_summary.csv itself. Each file below is
owned and produced by its corresponding skill-*-fetch skill (see the Delegation
Map in SKILL.md). This script only checks whether those files exist and are
fresh enough to back README.md's Data Health Dashboard table 2, and tells the
caller which skill to delegate to when a file is missing or stale.
"""

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TAIPEI_TZ = timezone(timedelta(hours=8))

# (label, csv path relative to ROOT, checked_at column name, stale_after_days, delegate skill)
SOURCES = [
    ("MOPS 財報 PDF 轉 MD", "data/MOPS/mops_health_summary.csv", "checked_at", 3, "skill-mops-fetch"),
    ("Google Alerts 新聞情緒分析", "data/GoogleAlertManager/google_alert_health_summary.csv", "checked_at", 3, "skill-google-alert-fetch"),
    ("法說會/財報 Ingestion", "data/InvestorConference/investor_conference_health_summary.csv", "checked_at", 7, "skill-company-investorconference-ingest"),
    ("GoodInfo 上游下載", "data/Python-Actions.GoodInfo/goodinfo_download_health_summary.csv", "checked_at", 7, "skill-goodinfo-fetch"),
    ("GoodInfo Stage1 轉檔", "data/Python-Actions.GoodInfo.Analyzer/stage1_goodinfo_health_summary.csv", "checked_at", 3, "skill-goodinfo-fetch"),
]


def parse_checked_at(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def audit_one(label, rel_path, checked_at_col, stale_after_days, delegate_skill):
    path = os.path.join(ROOT, rel_path)
    now = datetime.now(TAIPEI_TZ)

    if not os.path.exists(path):
        return {
            "label": label,
            "path": rel_path,
            "status": "MISSING",
            "detail": f"檔案不存在，需委派 {delegate_skill} 產生",
            "delegate": delegate_skill,
        }

    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "label": label,
            "path": rel_path,
            "status": "BROKEN",
            "detail": f"讀取失敗：{exc}",
            "delegate": delegate_skill,
        }

    if not rows or checked_at_col not in rows[0]:
        return {
            "label": label,
            "path": rel_path,
            "status": "BROKEN",
            "detail": f"缺少 {checked_at_col} 欄位或無資料列",
            "delegate": delegate_skill,
        }

    checked_at_values = [parse_checked_at(r.get(checked_at_col)) for r in rows]
    checked_at_values = [v for v in checked_at_values if v is not None]
    if not checked_at_values:
        return {
            "label": label,
            "path": rel_path,
            "status": "BROKEN",
            "detail": f"{checked_at_col} 欄位無法解析為時間",
            "delegate": delegate_skill,
        }

    latest = max(checked_at_values)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=TAIPEI_TZ)
    age_days = (now - latest).total_seconds() / 86400.0

    if age_days > stale_after_days:
        return {
            "label": label,
            "path": rel_path,
            "status": "STALE",
            "detail": f"最新 checked_at 已 {age_days:.1f} 天前（門檻 {stale_after_days} 天），需委派 {delegate_skill}",
            "delegate": delegate_skill,
        }

    return {
        "label": label,
        "path": rel_path,
        "status": "OK",
        "detail": f"最新 checked_at 為 {age_days:.1f} 天前",
        "delegate": None,
    }


def main():
    results = [audit_one(*source) for source in SOURCES]

    print("=== README Data Health Dashboard 表二來源稽核 ===")
    ok = 0
    for r in results:
        marker = "OK" if r["status"] == "OK" else r["status"]
        print(f"[{marker}] {r['label']} ({r['path']}) - {r['detail']}")
        if r["status"] == "OK":
            ok += 1

    print(f"\n{ok}/{len(results)} 個健康度來源正常。")

    problems = [r for r in results if r["status"] != "OK"]
    if problems:
        print("\n建議委派：")
        for r in problems:
            print(f"- {r['label']}：呼叫 {r['delegate']}（{r['detail']}）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
