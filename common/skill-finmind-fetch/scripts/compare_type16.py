#!/usr/bin/env python3
import argparse
import csv

def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("generated")
    p.add_argument("analyzer")
    p.add_argument("--stock-id", default="2330")
    p.add_argument("--tolerance", type=float, default=0.01)
    args = p.parse_args()
    generated = {r["季度"]: r for r in load(args.generated)}
    analyzer = {r["季度"].split()[0]: r for r in load(args.analyzer) if r.get("stock_code") == args.stock_id}
    common = sorted(set(generated) & set(analyzer))
    compared = exact = within = 0
    differences = []
    for quarter in common:
        for key in generated[quarter]:
            if key in {"stock_code", "company_name", "季度", "file_type", "source_file", "download_success", "download_timestamp"}:
                continue
            left, right = generated[quarter].get(key, ""), analyzer[quarter].get(key, "")
            if not left or not right:
                continue
            try:
                left, right = float(left), float(right)
            except ValueError:
                continue
            compared += 1
            delta = abs(left - right)
            exact += delta == 0
            within += delta <= args.tolerance
            if delta > args.tolerance:
                differences.append((delta, quarter, key, right, left))
    print(f"common_quarters={len(common)} compared={compared} exact={exact} within_tolerance={within}")
    for delta, quarter, key, expected, actual in sorted(differences, reverse=True)[:20]:
        print(f"DIFF {quarter} {key}: analyzer={expected} generated={actual} delta={delta:.4f}")
    return 1 if differences else 0

if __name__ == "__main__":
    raise SystemExit(main())
