#!/usr/bin/env python3
"""Build quarterly actual EPS and trailing TTM EPS series for PE-band inputs.

This script intentionally separates source quarterly EPS facts from derived TTM EPS.
It can ingest a GoodInfo-style quarterly ratio CSV and optional official overlay rows.
"""
from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from pathlib import Path

EPS_COLUMN = "每股稅後盈餘 (元)稅後淨利 / 發行股數"


def quarter_end(year: int, quarter: int) -> str:
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    return f"{year}-{month_day}"


def parse_float(value: str):
    value = (value or "").strip().replace(",", "")
    if value in {"", "-", "--", "N/A", "nan"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_goodinfo_rows(path: Path, stock_code: str) -> dict[tuple[int, int], dict]:
    rows = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("stock_code") != stock_code:
                continue
            match = re.search(r"(\d{4})Q([1-4])", row.get("季度", ""))
            if not match:
                continue
            year = int(match.group(1))
            quarter = int(match.group(2))
            eps = parse_float(row.get(EPS_COLUMN, ""))
            if eps is None:
                continue
            key = (year, quarter)
            # Keep the first row for duplicate historical rows; the file is newest-first.
            rows.setdefault(key, {
                "stock_code": stock_code,
                "company_name": row.get("company_name", ""),
                "fiscal_year": str(year),
                "fiscal_quarter": f"Q{quarter}",
                "period_end_date": quarter_end(year, quarter),
                "actual_eps": f"{eps:.2f}",
                "currency": "TWD",
                "eps_basis": "diluted_or_reported_eps_as_source",
                "source_type": "sibling_goodinfo_fin_ratio_quarter",
                "source_path": str(path),
                "source_field": EPS_COLUMN,
                "source_quality": "secondary_structured_financial_dataset",
                "disclosure_date": "",
                "date_policy": "period_end_effective_for_historical_band_until_disclosure_dates_available",
            })
    return rows


def load_overlay_rows(path: Path | None, stock_code: str) -> dict[tuple[int, int], dict]:
    rows = {}
    if not path or not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("stock_code") != stock_code:
                continue
            year = int(row["fiscal_year"])
            quarter = int(row["fiscal_quarter"].replace("Q", ""))
            rows[(year, quarter)] = row
    return rows


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_ttm_rows(quarter_rows: list[dict]) -> list[dict]:
    ordered = sorted(quarter_rows, key=lambda r: (int(r["fiscal_year"]), int(r["fiscal_quarter"].replace("Q", ""))))
    out = []
    for idx in range(3, len(ordered)):
        window = ordered[idx - 3:idx + 1]
        eps_values = [float(r["actual_eps"]) for r in window]
        latest = window[-1]
        disclosure_date = latest.get("disclosure_date", "")
        effective_date = disclosure_date or latest["period_end_date"]
        date_policy = "disclosure_date" if disclosure_date else "period_end_effective_for_historical_band_until_disclosure_dates_available"
        out.append({
            "stock_code": latest["stock_code"],
            "company_name": latest.get("company_name", ""),
            "date": effective_date,
            "fiscal_period": f'{latest["fiscal_year"]}{latest["fiscal_quarter"]}',
            "period_end_date": latest["period_end_date"],
            "trailing_ttm_eps": f"{sum(eps_values):.2f}",
            "currency": latest.get("currency", "TWD"),
            "eps_scope": "trailing_eps",
            "eps_horizon": "TTM",
            "window_quarters": ";".join(f'{r["fiscal_year"]}{r["fiscal_quarter"]}:{r["actual_eps"]}' for r in window),
            "source_paths": ";".join(sorted(set(r.get("source_path", "") for r in window if r.get("source_path")))),
            "date_policy": date_policy,
            "derived_from": "quarterly_actual_eps_sum_last_four_quarters",
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-code", default="2330")
    parser.add_argument("--goodinfo-csv", default="../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_fin_ratio_quarter.csv")
    parser.add_argument("--overlay-csv", default="data/company_facts/2330/quarterly_eps_official_overlay.csv")
    parser.add_argument("--quarterly-output", default="data/company_facts/2330/quarterly_actual_eps.csv")
    parser.add_argument("--ttm-output", default="data/derived/2330/trailing_ttm_eps_series.csv")
    args = parser.parse_args()

    rows = load_goodinfo_rows(Path(args.goodinfo_csv), args.stock_code)
    rows.update(load_overlay_rows(Path(args.overlay_csv), args.stock_code))
    quarter_rows = sorted(rows.values(), key=lambda r: (int(r["fiscal_year"]), int(r["fiscal_quarter"].replace("Q", ""))))

    q_fields = [
        "stock_code", "company_name", "fiscal_year", "fiscal_quarter", "period_end_date",
        "actual_eps", "currency", "eps_basis", "source_type", "source_path", "source_field",
        "source_quality", "disclosure_date", "date_policy",
    ]
    write_csv(Path(args.quarterly_output), quarter_rows, q_fields)

    ttm_fields = [
        "stock_code", "company_name", "date", "fiscal_period", "period_end_date", "trailing_ttm_eps",
        "currency", "eps_scope", "eps_horizon", "window_quarters", "source_paths", "date_policy", "derived_from",
    ]
    ttm_rows = build_ttm_rows(quarter_rows)
    write_csv(Path(args.ttm_output), ttm_rows, ttm_fields)
    print(f"wrote {len(quarter_rows)} quarterly EPS rows to {args.quarterly_output}")
    print(f"wrote {len(ttm_rows)} trailing TTM EPS rows to {args.ttm_output}")


if __name__ == "__main__":
    main()
