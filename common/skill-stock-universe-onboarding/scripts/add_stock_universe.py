#!/usr/bin/env python3
"""Update upstream stock universe CSVs for ConceptStocks and TAIEX lists."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable


def read_csv(path: Path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return fieldnames, rows


def detect_file_style(path: Path) -> tuple[str, str]:
    try:
        sample = path.read_bytes()[:65536]
    except FileNotFoundError:
        return 'utf-8-sig', '\n'
    encoding = 'utf-8-sig' if sample.startswith(b'\xef\xbb\xbf') else 'utf-8'
    lineterminator = '\r\n' if b'\r\n' in sample else '\n'
    return encoding, lineterminator


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    encoding, lineterminator = detect_file_style(path)
    with path.open('w', encoding=encoding, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator=lineterminator)
        writer.writeheader()
        writer.writerows(rows)


def parse_stock_pair(value: str) -> tuple[str, str]:
    if ',' in value:
        code, name = value.split(',', 1)
    elif ':' in value:
        code, name = value.split(':', 1)
    else:
        raise ValueError(f"Stock pair must be '代號,名稱' or '代號:名稱': {value}")
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError(f"Invalid stock pair: {value}")
    return code, name


def parse_codes(value: str) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(',') if part.strip()}


def ensure_list_rows(path: Path, stock_pairs: Iterable[str]) -> list[str]:
    if not stock_pairs:
        return []
    fieldnames, rows = read_csv(path)
    if fieldnames[:2] != ['代號', '名稱']:
        raise ValueError(f"{path} must start with columns 代號,名稱; got {fieldnames[:2]}")
    by_code = {row.get('代號', '').strip(): row for row in rows}
    changes = []
    for raw in stock_pairs:
        code, name = parse_stock_pair(raw)
        existing = by_code.get(code)
        if existing:
            existing_name = existing.get('名稱', '').strip()
            if existing_name != name:
                changes.append(f"WARN {path}: {code} already exists as {existing_name}, requested {name}")
            else:
                changes.append(f"SKIP {path}: {code} {name} already exists")
            continue
        row = {field: '' for field in fieldnames}
        row['代號'] = code
        row['名稱'] = name
        rows.append(row)
        by_code[code] = row
        changes.append(f"ADD {path}: {code} {name}")
    write_csv(path, fieldnames, rows)
    return changes


def insert_concept_field(fieldnames: list[str], concept_field: str) -> list[str]:
    if concept_field in fieldnames:
        return fieldnames
    insert_before = '相關集團' if '相關集團' in fieldnames else None
    if insert_before is None:
        for candidate in ['download_timestamp', 'process_timestamp']:
            if candidate in fieldnames:
                insert_before = candidate
                break
    if insert_before and insert_before in fieldnames:
        idx = fieldnames.index(insert_before)
        return fieldnames[:idx] + [concept_field] + fieldnames[idx:]
    return fieldnames + [concept_field]


def update_companyinfo(path: Path, concept_field: str, exposed_codes: set[str]) -> list[str]:
    if not concept_field:
        return []
    fieldnames, rows = read_csv(path)
    fieldnames = insert_concept_field(fieldnames, concept_field)
    changes = []
    added = concept_field not in (read_csv(path)[0])
    for row in rows:
        code = row.get('代號', '').strip()
        old = row.get(concept_field, '')
        new = '1' if code in exposed_codes else (old if old in {'0', '1'} else '0')
        row[concept_field] = new
        if old != new and code in exposed_codes:
            changes.append(f"SET {path}: {code} {concept_field}=1")
    if added:
        changes.insert(0, f"ADD COLUMN {path}: {concept_field}")
    write_csv(path, fieldnames, rows)
    return changes


def update_metadata(
    path: Path,
    concept_field: str,
    ticker: str,
    company: str,
    cik: str,
    latest_report: str,
    upcoming: str,
    release_time: str,
    segments: str,
) -> list[str]:
    if not concept_field and not ticker and not company:
        return []
    if not (concept_field and ticker and company):
        raise ValueError('Concept metadata requires --concept-field, --concept-ticker, and --concept-company')
    fieldnames, rows = read_csv(path)
    required = ['概念欄位', '公司名稱', 'Ticker']
    if any(col not in fieldnames for col in required):
        raise ValueError(f"{path} missing required metadata columns: {required}")
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S CST')
    by_field = {row.get('概念欄位', '').strip(): row for row in rows}
    row = by_field.get(concept_field)
    changes = []
    if row is None:
        row = {field: '' for field in fieldnames}
        row['概念欄位'] = concept_field
        rows.append(row)
        changes.append(f"ADD {path}: {concept_field} -> {ticker}")
    else:
        changes.append(f"UPDATE {path}: {concept_field} -> {ticker}")
    updates = {
        '公司名稱': company,
        'Ticker': ticker,
        'CIK': cik,
        '最新財報': latest_report,
        '即將發布': upcoming,
        '發布時間': release_time,
        '產品區段': segments,
        'process_timestamp': now,
    }
    if not row.get('download_timestamp'):
        updates['download_timestamp'] = now
    for key, value in updates.items():
        if key in fieldnames and value:
            row[key] = value
    write_csv(path, fieldnames, rows)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--concept-companyinfo', default='../ConceptStocks/raw_companyinfo.csv')
    parser.add_argument('--concept-metadata', default='../ConceptStocks/raw_conceptstock_company_metadata.csv')
    parser.add_argument('--monitor-list', default='../Selenium-Actions.Auction/觀察名單.csv')
    parser.add_argument('--focus-list', default='../Selenium-Actions.Auction/專注名單.csv')
    parser.add_argument('--concept-field', default='')
    parser.add_argument('--concept-ticker', default='')
    parser.add_argument('--concept-company', default='')
    parser.add_argument('--concept-cik', default='')
    parser.add_argument('--concept-latest-report', default='')
    parser.add_argument('--concept-upcoming', default='')
    parser.add_argument('--concept-release-time', default='')
    parser.add_argument('--concept-segments', default='')
    parser.add_argument('--concept-exposed', default='', help='Comma-separated Taiwan stock IDs to mark as 1')
    parser.add_argument('--monitor-stock', action='append', default=[], help="Repeatable '代號,名稱' pair")
    parser.add_argument('--focus-stock', action='append', default=[], help="Repeatable '代號,名稱' pair")
    args = parser.parse_args()

    changes: list[str] = []
    changes += update_companyinfo(Path(args.concept_companyinfo), args.concept_field, parse_codes(args.concept_exposed))
    changes += update_metadata(
        Path(args.concept_metadata),
        args.concept_field,
        args.concept_ticker,
        args.concept_company,
        args.concept_cik,
        args.concept_latest_report,
        args.concept_upcoming,
        args.concept_release_time,
        args.concept_segments,
    )
    changes += ensure_list_rows(Path(args.monitor_list), args.monitor_stock)
    changes += ensure_list_rows(Path(args.focus_list), args.focus_stock)

    if changes:
        for change in changes:
            print(change)
    else:
        print('No changes requested')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
