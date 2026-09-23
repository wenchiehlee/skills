"""
select_data_source.py
----------------------
Composite-skill helper for skill-stock-pipeline-health-monitor.

GoodInfo (via skill-goodinfo-fetch) and FinMind (via skill-finmind-fetch) can
produce the SAME stage1 raw CSV schema for a subset of GoodInfo "Type" numbers
(see skill-finmind-fetch/SKILL.md). This script does not fetch anything itself;
it reads the per-type health status already synced into this repo
(data/Python-Actions.GoodInfo.Analyzer/stage1_goodinfo_health.csv) and
recommends which skill to delegate the fetch to when a type is stale/broken.
"""

import argparse
import csv
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HEALTH_CSV = os.path.join(ROOT, "data", "Python-Actions.GoodInfo.Analyzer", "stage1_goodinfo_health.csv")

# GoodInfo Type -> (FinMind adapter script, example command), per skill-finmind-fetch/SKILL.md.
# Only types with a confirmed FinMind adapter are listed; unlisted types have no
# known FinMind equivalent and must stay on the skill-goodinfo-fetch path.
FINMIND_ADAPTERS = {
    "1": ("fetch_type1.py", "股利政策"),
    "4": ("fetch_type4.py", "年度營運績效"),
    "5": ("fetch_type5.py", "每月營收"),
    "6": ("fetch_type6.py", "股權分散表"),
    "7": ("fetch_type7.py", "季度營運績效"),
    "8": ("fetch_k_chart_flow.py --type 8", "週 K 線/資金流向"),
    "9": ("fetch_type9.py", "季度股價"),
    "11": ("fetch_type11.py", "每週交易資料（含法人）"),
    "12": ("fetch_k_chart_flow.py --type 12", "月 K 線/資金流向"),
    "13": ("fetch_to_csv.py", "每日融資融券"),
    "14": ("fetch_type14.py", "每週融資融券"),
    "15": ("fetch_type15.py", "每月融資融券"),
    "16": ("fetch_type16.py", "季度財務比率"),
    "17": ("fetch_k_chart_flow.py --type 17", "週 K 線/PER 資金流向"),
    "18": ("fetch_k_chart_flow.py --type 18", "日 K 線/資金流向"),
    "19": ("fetch_type19.py", "除權息日程"),
}

HEALTHY_STATUSES = {"healthy", "warning"}
UNHEALTHY_STATUSES = {"stale", "broken", "missing"}


def load_rows():
    if not os.path.exists(HEALTH_CSV):
        print(f"找不到 {HEALTH_CSV}；請先確認 Python-Actions.GoodInfo.Analyzer 已同步 stage1_goodinfo_health.csv。")
        return []
    with open(HEALTH_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def recommend(row):
    data_type = (row.get("data_type") or "").strip()
    dest_path = (row.get("dest_path") or "").strip()
    status = (row.get("stage1_health_status") or "").strip().lower() or "unknown"

    if status in HEALTHY_STATUSES:
        return {
            "type": data_type,
            "dest_path": dest_path,
            "status": status,
            "action": "keep",
            "detail": "現狀健康，不需要委派。",
        }

    adapter = FINMIND_ADAPTERS.get(data_type)
    if adapter:
        script, label = adapter
        return {
            "type": data_type,
            "dest_path": dest_path,
            "status": status,
            "action": "delegate:skill-finmind-fetch",
            "detail": (
                f"{label}（Type {data_type}）status={status}；"
                f"建議委派 skill-finmind-fetch，參考指令："
                f"python skills/skill-finmind-fetch/scripts/{script} --stock-id <STOCK> --company-name <NAME> "
                f"--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> --output {dest_path}"
            ),
        }

    return {
        "type": data_type,
        "dest_path": dest_path,
        "status": status,
        "action": "delegate:skill-goodinfo-fetch",
        "detail": (
            f"Type {data_type} status={status}，沒有已知 FinMind adapter；"
            f"建議委派 skill-goodinfo-fetch 重跑下載，參考指令："
            f"python scripts/goodinfo_pipeline.py download {data_type}（於 Python-Actions.GoodInfo 執行）"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="判斷過期的 GoodInfo Type 該委派 FinMind 還是 GoodInfo 補資料")
    parser.add_argument("--type", help="只檢查特定 GoodInfo Type 編號", default=None)
    args = parser.parse_args()

    rows = load_rows()
    if not rows:
        return 1

    if args.type:
        rows = [r for r in rows if (r.get("data_type") or "").strip() == args.type]
        if not rows:
            print(f"stage1_goodinfo_health.csv 中找不到 Type {args.type}。")
            return 1

    recommendations = [recommend(r) for r in rows]

    keep = [r for r in recommendations if r["action"] == "keep"]
    delegate = [r for r in recommendations if r["action"] != "keep"]

    print(f"=== GoodInfo vs FinMind 智慧選源建議（{len(recommendations)} 筆 Type） ===")
    print(f"健康、維持現況：{len(keep)}")
    for r in delegate:
        print(f"\n[Type {r['type']}] {r['dest_path']} status={r['status']}")
        print(f"  -> {r['detail']}")

    if not delegate:
        print("\n所有已知 Type 皆健康，不需要委派。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
