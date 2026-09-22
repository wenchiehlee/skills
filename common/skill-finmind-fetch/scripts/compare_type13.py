#!/usr/bin/env python3
"""Compare a FinMind Type 13 CSV with GoodInfo Analyzer raw_margin_daily.csv."""
import argparse
import csv

META = {"stock_code", "company_name", "期別", "file_type", "source_file", "download_success", "download_timestamp", "process_timestamp", "stage1_process_timestamp"}

def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("generated")
    parser.add_argument("analyzer")
    parser.add_argument("--stock-id", default="2330")
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    generated = {(r["stock_code"], r["期別"]): r for r in load(args.generated) if r.get("stock_code") == args.stock_id}
    analyzer = {(r["stock_code"], r["期別"]): r for r in load(args.analyzer) if r.get("stock_code") == args.stock_id}
    common = sorted(set(generated) & set(analyzer))
    compared = exact = within = missing = 0
    differences = []
    missing_fields = {}
    for key in common:
        for field in generated[key]:
            if field in META:
                continue
            left, right = generated[key].get(field, ""), analyzer[key].get(field, "")
            if not left or not right:
                if left != right:
                    missing_fields[field] = missing_fields.get(field, 0) + 1
                missing += 1
                continue
            left_n, right_n = number(left), number(right)
            if left_n is None or right_n is None:
                if left != right:
                    differences.append((key[1], field, right, left, None))
                continue
            compared += 1
            delta = abs(left_n - right_n)
            exact += delta == 0
            within += delta <= args.tolerance
            if delta > args.tolerance:
                differences.append((key[1], field, right_n, left_n, delta))
    print(f"common_dates={len(common)} numeric_comparisons={compared} exact={exact} within_tolerance={within} missing_or_blank={missing}")
    if missing_fields:
        print("SOURCE_MISSING_OR_BLANK:")
        for field, count in sorted(missing_fields.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {field}: {count}")
    for date, field, expected, actual, delta in differences[:20]:
        print(f"DIFF {date} {field}: analyzer={expected} generated={actual} delta={delta}")
    return 1 if differences else 0

if __name__ == "__main__":
    raise SystemExit(main())
