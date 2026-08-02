#!/usr/bin/env python3
"""Render canonical enrichment JSON back to preview Markdown and compare coverage.

Rendering is JSON-only and never overwrites Pilot_Reports. When source Markdown is
available, the compare CSV uses it as validation context only.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
ENTITY_BADGE_RE = re.compile(r"\[!\[([^\]]+)\]\(https://img\.shields\.io/badge/[^)]*\)\]\([^)]*\.md\)")
THEME_BADGE_COLOR = "blue"

ENTITY_ALIAS_BY_COMPANY = {
    "中華電": ["中華電信"],
    "台灣大": ["台灣大哥大"],
    "遠傳": ["遠傳電信"],
    "世界": ["世界先進"],
    "光寶科": ["光寶科技"],
    "台達電": ["台達電子"],
    "臻鼎-KY": ["臻鼎"],
    "鈺齊-KY": ["鈺齊"],
    "鴻華先進-創": ["鴻華先進"],
    "友達": ["友達光電"],
    "群創": ["群創光電"],
    "日月光投控": ["日月光"],
    "LINEPAY": ["LINE Pay"],
}

FINANCIAL_HEADING = "## 財務概況"
PLATFORM_REVENUE_HEADING = "### 營收平台佔比 (Revenue by Platform %)"
PLATFORM_REVENUE_ANCHOR = "營收平台佔比-revenue-by-platform-"
QUARTERLY_HEADING = "### 季度關鍵財務數據 (近 4 季)"
COMPETITOR_FINANCIAL_HEADING = "### 競爭同業 Revenue/Profit/GM"
H3_RE = re.compile(r"(?m)^### .*$")
DEFAULT_UPDATED_AT = "2026-08-01 17:32 CST"
REQUIRED_RENDER_DATA = {
    "data/ConceptStocks/raw_conceptstock_company_income.csv",
    "data/ConceptStocks/raw_conceptstock_daily.csv",
    "data/InvestorConference/raw_ir_quarterly_financials.csv",
    "data/InvestorEvents/raw_event_upcoming_earnings.csv",
    "data/Python-Actions.GoodInfo.Analyzer/raw_daily_k_chart_flow.csv",
    "data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv",
    "data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv",
    "data/company_segment_weights.csv",
}



def period_sort_key(period: str) -> tuple[int, int, str]:
    match = re.match(r"^(\d{4})(?:[-/]?Q([1-4])|-FY)?$", period.strip(), re.IGNORECASE)
    if not match:
        return (0, 0, period)
    year = int(match.group(1))
    quarter = int(match.group(2) or 5)
    return (year, quarter, period)


def format_pct(value: str) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "-"


def format_approx_pct(value: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:g}%"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(":---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def read_dict_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def render_data_health_summary(biztrends_root: Path) -> tuple[str, list[str]]:
    status_path = biztrends_root / "data/data_freshness_status.csv"
    rows = read_dict_rows(status_path)
    by_dest = {str(row.get("dest_path", "")).strip(): row for row in rows}
    missing: list[str] = []
    unhealthy: list[str] = []
    warnings: list[str] = []
    for dest in sorted(REQUIRED_RENDER_DATA):
        row = by_dest.get(dest)
        if row is None:
            if (biztrends_root / dest).is_file():
                warnings.append(f"{dest}: no freshness row")
            else:
                missing.append(dest)
            continue
        if str(row.get("file_exists", "")).strip().lower() != "true":
            unhealthy.append(f"{dest}: missing")
            continue
        timestamp_status = str(row.get("timestamp_health_status", "")).strip().lower()
        freshness_status = str(row.get("freshness_status", "")).strip().lower()
        if timestamp_status in {"broken", "missing", "missing_file"} or freshness_status in {"broken", "missing", "missing_file"}:
            unhealthy.append(f"{dest}: timestamp={timestamp_status or '-'} freshness={freshness_status or '-'}")
        elif timestamp_status != "healthy" or freshness_status != "ok":
            warnings.append(f"{dest}: timestamp={timestamp_status or '-'} freshness={freshness_status or '-'}")
    issues = [f"missing health row: {item}" for item in missing] + unhealthy
    summary = f"Data health: required={len(REQUIRED_RENDER_DATA)} blocking={len(issues)} warnings={len(warnings)}"
    if warnings:
        summary += " | warnings: " + "; ".join(warnings[:5])
        if len(warnings) > 5:
            summary += f"; +{len(warnings) - 5} more"
    return summary, issues


def load_competitor_financial_adapter(coverage_root: Path):
    adapter_path = coverage_root / "skills/skill-company-competitor-analysis/scripts/render_competitor_financial_section.py"
    if not adapter_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("my_tw_competitor_financial_section", adapter_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def collect_segment_weight_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.is_file():
        return {}
    by_ticker: dict[str, list[dict[str, str]]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("status", "")).strip() != "active":
                continue
            ticker = str(row.get("stock_code", "")).strip()
            segment = str(row.get("segment_name", "")).strip()
            period = str(row.get("source_period", "")).strip()
            weight = str(row.get("weight_pct", "")).strip()
            if not ticker or not segment or not period or not weight:
                continue
            by_ticker.setdefault(ticker, []).append(row)
    return by_ticker


def latest_segment_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    latest_period = max((str(r.get("source_period", "")).strip() for r in rows), key=period_sort_key)
    return [r for r in rows if str(r.get("source_period", "")).strip() == latest_period]


def sorted_segment_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: float(r.get("weight_pct") or 0), reverse=True)


def load_segment_weight_tables(path: Path) -> dict[str, str]:
    tables: dict[str, str] = {}
    for ticker, rows in collect_segment_weight_rows(path).items():
        latest_rows = latest_segment_rows(rows)
        segments = [str(r.get("segment_name", "")).strip() for r in sorted_segment_rows(latest_rows)]
        periods = sorted({str(r.get("source_period", "")).strip() for r in rows}, key=period_sort_key, reverse=True)
        value_by_key = {
            (str(r.get("source_period", "")).strip(), str(r.get("segment_name", "")).strip()): format_pct(str(r.get("weight_pct", "")).strip())
            for r in rows
        }
        table_rows = [[period] + [value_by_key.get((period, segment), "-") for segment in segments] for period in periods]
        tables[ticker] = PLATFORM_REVENUE_HEADING + "\n" + markdown_table(["期間"] + segments, table_rows)
    return tables


def format_num(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.1f}"


def evidence_anchor(evidence_item: dict[str, Any]) -> str:
    render_section = evidence_item.get("render_section", {}) if isinstance(evidence_item, dict) else {}
    anchor = str(render_section.get("anchor") or PLATFORM_REVENUE_ANCHOR).lstrip("#")
    return "#" + quote(anchor, safe="")


def render_annotation_badge(annotation: dict[str, Any], data: dict[str, Any]) -> str:
    render = annotation.get("render", {}) if isinstance(annotation, dict) else {}
    if not render.get("badge"):
        return ""
    if annotation.get("status") not in {"linked_supported", "linked_partial"}:
        return ""
    label = str(render.get("label") or "Evidence").strip()
    color = str(render.get("color") or "blue").strip()
    evidence_ref = str(annotation.get("evidence_ref", "")).strip()
    evidence_item: Any = data
    for part in evidence_ref.split("."):
        if not part:
            continue
        evidence_item = evidence_item.get(part, {}) if isinstance(evidence_item, dict) else {}
    if not isinstance(evidence_item, dict):
        evidence_item = {}
    alt = str(render.get("alt") or label).strip()
    badge_label = badge_label_text(label)
    badge_url = f"https://img.shields.io/badge/{badge_label}-{quote(color, safe='')}"
    return f"[![{alt}]({badge_url})]({evidence_anchor(evidence_item)})"


def apply_annotations(markdown: str, data: dict[str, Any]) -> str:
    annotations = data.get("annotations", []) or []
    if not annotations:
        return markdown
    lines = markdown.splitlines()
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        match = str(annotation.get("presentation_match", "")).strip()
        badge = render_annotation_badge(annotation, data)
        if not match or not badge:
            continue
        for idx, line in enumerate(lines):
            if match in line and badge not in line:
                lines[idx] = line.rstrip() + " " + badge
                break
    return "\n".join(lines)


def render_segment_revenue_platforms_from_evidence(data: dict[str, Any]) -> str:
    evidence = data.get("evidence", {}).get("segment_revenue_platforms", {}) if isinstance(data.get("evidence"), dict) else {}
    if not evidence:
        return ""
    rows = evidence.get("rows", []) or []
    if not rows:
        return ""
    heading = str(evidence.get("render_section", {}).get("heading") or PLATFORM_REVENUE_HEADING).strip()
    segment_order = [str(s).strip() for s in evidence.get("segment_order", []) if str(s).strip()]
    if not segment_order:
        seen: list[str] = []
        for row in rows:
            for segment in (row.get("segments", {}) or {}).keys():
                if segment not in seen:
                    seen.append(segment)
        segment_order = seen
    table_rows = []
    for row in sorted(rows, key=lambda r: period_sort_key(str(r.get("period", ""))), reverse=True):
        segments = row.get("segments", {}) or {}
        rendered = [str(row.get("period", "")).strip()]
        for segment in segment_order:
            item = segments.get(segment, {}) or {}
            weight = format_pct(str(item.get("weight_pct", "")).strip())
            revenue = item.get("revenue_m_twd")
            rendered.append(f"{weight} ({format_num(revenue)})" if weight != "-" and revenue not in (None, "") else weight)
        table_rows.append(rendered)
    return heading + "\n" + markdown_table(["期間"] + segment_order, table_rows)


def load_segment_weight_summaries(path: Path) -> dict[str, str]:
    summaries: dict[str, str] = {}
    for ticker, rows in collect_segment_weight_rows(path).items():
        parts = []
        for row in sorted_segment_rows(latest_segment_rows(rows)):
            segment = str(row.get("segment_name", "")).strip()
            weight = format_approx_pct(str(row.get("weight_pct", "")).strip())
            if segment and weight != "-":
                parts.append(f"{segment} (~{weight})")
        if parts:
            summaries[ticker] = "- **主要平台:** " + ", ".join(parts) + "."
    return summaries

def insert_platform_revenue_section(financial: str, platform_section: str, replace_existing: bool = False) -> str:
    financial = financial.strip()
    platform_section = platform_section.strip()
    if not financial or not platform_section:
        return financial
    if PLATFORM_REVENUE_HEADING in financial and not replace_existing:
        return financial

    heading = ""
    body = financial
    if financial.startswith("## "):
        lines = financial.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()

    preface, sections = split_h3_sections(body)
    if replace_existing:
        sections = [(h, section) for h, section in sections if h != PLATFORM_REVENUE_HEADING]
    if not sections:
        parts = [part for part in [heading, body, platform_section] if part]
        return "\n\n".join(parts).strip()

    reordered: list[str] = []
    inserted = False
    for h, section in sections:
        reordered.append(section)
        if h == QUARTERLY_HEADING:
            reordered.append(platform_section)
            inserted = True
    if not inserted:
        reordered.append(platform_section)

    parts = [part for part in [heading, preface, "\n\n".join(reordered).strip()] if part]
    return "\n\n".join(parts).strip()


def split_h3_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    matches = list(H3_RE.finditer(markdown))
    if not matches:
        return markdown.strip(), []
    preface = markdown[: matches[0].start()].strip()
    sections: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        section = markdown[match.start():end].strip()
        heading = match.group(0).strip()
        sections.append((heading, section))
    return preface, sections


def normalize_financial_section(financial: str) -> str:
    financial = financial.strip()
    if not financial or PLATFORM_REVENUE_HEADING not in financial or QUARTERLY_HEADING not in financial:
        return financial

    heading = ""
    body = financial
    if financial.startswith("## "):
        lines = financial.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()

    preface, sections = split_h3_sections(body)
    platform_sections = [section for h, section in sections if h == PLATFORM_REVENUE_HEADING]
    if not platform_sections:
        return financial

    kept = [(h, section) for h, section in sections if h != PLATFORM_REVENUE_HEADING]
    reordered: list[str] = []
    inserted = False
    for h, section in kept:
        reordered.append(section)
        if h == QUARTERLY_HEADING:
            reordered.extend(platform_sections)
            inserted = True
    if not inserted:
        reordered.extend(platform_sections)

    parts = [part for part in [heading, preface, "\n\n".join(reordered).strip()] if part]
    return "\n\n".join(parts).strip()




def parse_number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "")
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def date_to_period(date_text: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})-\d{2}$", date_text.strip())
    if not match:
        return date_text.strip()
    year = match.group(1)
    month = int(match.group(2))
    if month == 12:
        return f"{year}-FY"
    quarter = ((month - 1) // 3) + 1
    return f"{year}-Q{quarter}"


def parse_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]




def month_to_quarter(month_text: str) -> str:
    match = re.match(r"^(\d{4})/(\d{1,2})$", month_text.strip())
    if not match:
        return ""
    year = match.group(1)
    month = int(match.group(2))
    quarter = ((month - 1) // 3) + 1
    return f"{year}-Q{quarter}"


def load_monthly_revenue_totals(path: Path) -> dict[str, dict[str, float]]:
    if not path.is_file():
        return {}
    totals: dict[str, dict[str, float]] = {}
    month_seen: dict[tuple[str, str], set[str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ticker = str(row.get("stock_code", "")).strip()
            month_text = str(row.get("月別", "")).strip()
            quarter = month_to_quarter(month_text)
            if not ticker or not quarter:
                continue
            revenue = parse_number(str(row.get("合併營業收入_營收_億", "")).strip())
            if revenue is None:
                revenue = parse_number(str(row.get("營業收入_營收_億", "")).strip())
            if revenue is None:
                continue
            revenue_million = revenue * 100.0
            totals.setdefault(ticker, {})[quarter] = totals.setdefault(ticker, {}).get(quarter, 0.0) + revenue_million
            year = quarter[:4]
            totals[ticker][f"{year}-FY"] = totals[ticker].get(f"{year}-FY", 0.0) + revenue_million
            month_seen.setdefault((ticker, f"{year}-FY"), set()).add(month_text)

    for (ticker, fy_period), months in month_seen.items():
        if len(months) < 12:
            totals.get(ticker, {}).pop(fy_period, None)
    return totals


def extract_revenue_totals(financial: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    _, sections = split_h3_sections(financial)
    for heading, section in sections:
        if "年度關鍵財務數據" not in heading and "季度關鍵財務數據" not in heading:
            continue
        table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]
        if len(table_lines) < 3:
            continue
        headers = parse_markdown_row(table_lines[0])
        for line in table_lines[2:]:
            cells = parse_markdown_row(line)
            if not cells or cells[0] != "Revenue":
                continue
            for header, value in zip(headers[1:], cells[1:]):
                number = parse_number(value)
                if number is not None:
                    totals[date_to_period(header)] = number
            break
    return totals


def format_revenue_amount(amount: float) -> str:
    if abs(amount) >= 100:
        return f"{amount:,.0f}"
    return f"{amount:,.1f}"


def add_revenue_amounts_to_platform_table(financial: str, fallback_totals: dict[str, float] | None = None) -> str:
    if PLATFORM_REVENUE_HEADING not in financial:
        return financial
    revenue_totals = dict(fallback_totals or {})
    revenue_totals.update(extract_revenue_totals(financial))
    if not revenue_totals:
        return financial

    preface, sections = split_h3_sections(financial)
    out_sections: list[str] = []
    pct_re = re.compile(r"^(-?\d+(?:\.\d+)?)%$")
    for heading, section in sections:
        if heading != PLATFORM_REVENUE_HEADING:
            out_sections.append(section)
            continue
        lines = section.splitlines()
        new_lines: list[str] = []
        for idx, line in enumerate(lines):
            if idx < 2 or not line.strip().startswith("|"):
                new_lines.append(line)
                continue
            cells = parse_markdown_row(line)
            if len(cells) < 2:
                new_lines.append(line)
                continue
            period = cells[0]
            total_revenue = revenue_totals.get(period)
            if total_revenue is None:
                new_lines.append(line)
                continue
            new_cells = [period]
            for cell in cells[1:]:
                match = pct_re.match(cell)
                if not match:
                    new_cells.append(cell)
                    continue
                pct = float(match.group(1))
                amount = total_revenue * pct / 100.0
                new_cells.append(f"{cell} ({format_revenue_amount(amount)})")
            new_lines.append("| " + " | ".join(new_cells) + " |")
        out_sections.append("\n".join(new_lines))

    parts = [part for part in [preface, "\n\n".join(out_sections).strip()] if part]
    return "\n\n".join(parts).strip()


def insert_competitor_financial_section(financial: str, competitor_section: str) -> str:
    financial = financial.strip()
    competitor_section = competitor_section.strip()
    if not financial or not competitor_section:
        return financial

    heading = ""
    body = financial
    if financial.startswith("## "):
        lines = financial.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()

    preface, sections = split_h3_sections(body)
    sections = [(h, section) for h, section in sections if h != COMPETITOR_FINANCIAL_HEADING]
    if not sections:
        parts = [part for part in [heading, body, competitor_section] if part]
        return "\n\n".join(parts).strip()

    reordered: list[str] = []
    inserted = False
    preferred_after = PLATFORM_REVENUE_HEADING if any(h == PLATFORM_REVENUE_HEADING for h, _section in sections) else QUARTERLY_HEADING
    for h, section in sections:
        reordered.append(section)
        if h == preferred_after:
            reordered.append(competitor_section)
            inserted = True
    if not inserted:
        reordered.append(competitor_section)

    parts = [part for part in [heading, preface, "\n\n".join(reordered).strip()] if part]
    return "\n\n".join(parts).strip()


def format_plain_number(value: object, decimals: int = 2) -> str:
    if value is None or value == "":
        return "NA"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NA"
    if abs(number) >= 1000:
        return f"{number:,.0f}"
    return f"{number:,.{decimals}f}"


def format_multiple(value: object) -> str:
    if value is None or value == "":
        return "NA"
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "NA"


def format_diff_pct(value: object) -> str:
    if value is None or value == "":
        return "NA"
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "NA"


def format_consensus_value(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if value is None:
        return "NA"
    if item.get("metric") == "revenue" and item.get("unit") == "百萬台幣":
        return format_plain_number(value, 0)
    return format_plain_number(value, 2)


def consensus_item(consensus: dict[str, Any], metric: str, period_offset: str) -> dict[str, Any] | None:
    for item in consensus.get("items", []) or []:
        if item.get("metric") == metric and item.get("period_offset") == period_offset:
            return item
    return None



def format_eps_value(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def actual_eps_by_period(actual_eps: dict[str, Any], key: str) -> dict[str, Any]:
    rows = actual_eps.get(key, []) if isinstance(actual_eps, dict) else []
    return {str(row.get("period", "")).strip(): row.get("eps_twd") for row in rows if str(row.get("period", "")).strip()}


def insert_eps_row(section: str, values_by_period: dict[str, Any]) -> str:
    if not values_by_period:
        return section
    lines = section.splitlines()
    table_indexes = [idx for idx, line in enumerate(lines) if line.strip().startswith("|")]
    if len(table_indexes) < 2:
        return section
    start, end = table_indexes[0], table_indexes[-1]
    headers = parse_markdown_row(lines[start])
    if len(headers) < 2:
        return section
    values = [format_eps_value(values_by_period.get(period)) for period in headers[1:]]
    if all(value == "-" for value in values):
        return section

    new_row = "| EPS (TWD)               | " + " | ".join(f"{value:>12}" for value in values) + " |"
    kept_table = []
    for line in lines[start : end + 1]:
        cells = parse_markdown_row(line)
        if cells and re.search(r"\bEPS\b", cells[0], re.IGNORECASE):
            continue
        kept_table.append(line)

    insert_at = len(kept_table)
    for idx, line in enumerate(kept_table):
        cells = parse_markdown_row(line)
        if cells and cells[0] == "Net Income":
            insert_at = idx + 1
            break
    kept_table.insert(insert_at, new_row)
    return "\n".join(lines[:start] + kept_table + lines[end + 1:])


def add_eps_rows_to_key_tables(financial: str, actual_eps: dict[str, Any]) -> str:
    if not financial.strip() or not actual_eps:
        return financial
    heading = ""
    body = financial.strip()
    if body.startswith("## "):
        lines = body.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()

    preface, sections = split_h3_sections(body)
    if not sections:
        return financial

    annual_eps = actual_eps_by_period(actual_eps, "annual")
    quarterly_eps = actual_eps_by_period(actual_eps, "quarterly")
    updated = []
    for h, section in sections:
        if "年度關鍵財務數據" in h:
            section = insert_eps_row(section, annual_eps)
        elif "季度關鍵財務數據" in h:
            section = insert_eps_row(section, quarterly_eps)
        updated.append(section)
    parts = [part for part in [heading, preface, "\n\n".join(updated).strip()] if part]
    return "\n\n".join(parts).strip()

def render_market_valuation_table(valuation: dict[str, Any]) -> str:
    metrics = valuation.get("metrics", {}) or {}
    inputs = valuation.get("derived_inputs", {}) or {}
    currency = valuation.get("currency") or "TWD"
    price = valuation.get("price")
    market_cap = valuation.get("market_cap_m_twd")
    enterprise_value = valuation.get("enterprise_value_m_twd")
    rows = [
        [
            "P/E (TTM)",
            format_multiple(metrics.get("pe_ttm")),
            f"股價 {format_plain_number(price, 2)} {currency}",
            f"TTM EPS {format_plain_number(inputs.get('ttm_eps_twd'), 2)} {currency}",
            "股價 / TTM EPS",
        ],
        [
            "P/S (TTM)",
            format_multiple(metrics.get("ps_ttm")),
            f"市值 {format_plain_number(market_cap, 0)} 百萬台幣",
            f"TTM 營收 {format_plain_number(inputs.get('ttm_revenue_m_twd'), 0)} 百萬台幣",
            "市值 / TTM 營收",
        ],
        [
            "P/B",
            format_multiple(metrics.get("pb")),
            f"市值 {format_plain_number(market_cap, 0)} 百萬台幣",
            f"股東權益 {format_plain_number(inputs.get('book_value_m_twd'), 0)} 百萬台幣",
            "市值 / 股東權益",
        ],
        [
            "EV/EBITDA (TTM)",
            format_multiple(metrics.get("ev_ebitda_ttm")),
            f"企業價值 {format_plain_number(enterprise_value, 0)} 百萬台幣",
            f"TTM EBITDA {format_plain_number(inputs.get('ttm_ebitda_m_twd'), 0)} 百萬台幣",
            "企業價值 / TTM EBITDA",
        ],
    ]
    return markdown_table(["指標", "數值", "分子", "分母", "說明"], rows)


def render_consensus_table(consensus: dict[str, Any]) -> str:
    rows: list[list[str]] = []
    for offset, label in [("0y", "current year"), ("1y", "next year")]:
        for metric, metric_label, purpose in [("eps", "EPS", "Forward P/E"), ("revenue", "Revenue", "Forward P/S")]:
            item = consensus_item(consensus, metric, offset)
            if not item:
                continue
            fiscal_year = item.get("fiscal_year") or "NA"
            unit_note = "百萬台幣" if item.get("unit") == "百萬台幣" else str(item.get("unit") or "")
            rows.append([
                f"{fiscal_year}E {metric_label}",
                format_consensus_value(item, "primary_value"),
                format_consensus_value(item, "cross_check_value"),
                format_diff_pct(item.get("difference_pct")),
                f"{purpose}; {label}; 單位: {unit_note}",
                str(item.get("confidence") or "NA"),
            ])
    target = consensus.get("target_price") or {}
    if target.get("value") is not None:
        rows.append([
            "Target Price",
            "NA",
            format_plain_number(target.get("value"), 2),
            "NA",
            "FactSet 目標價參考",
            "medium",
        ])
    if not rows:
        return ""
    return markdown_table(["指標", "Primary", "Cross-check", "差異", "用途 / 單位", "信心"], rows)


def render_consensus_valuation_table(valuation: dict[str, Any]) -> str:
    derived = valuation.get("derived_consensus_metrics", {}) or {}
    price = valuation.get("price")
    market_cap = valuation.get("market_cap_m_twd")
    currency = valuation.get("currency") or "TWD"
    rows: list[list[str]] = []
    if derived.get("forward_pe_consensus") is not None:
        year = derived.get("forward_pe_fiscal_year", "next")
        rows.append([
            "Forward P/E (Consensus)",
            format_multiple(derived.get("forward_pe_consensus")),
            f"股價 {format_plain_number(price, 2)} {currency}",
            f"{year}E EPS {format_plain_number(derived.get('forward_eps_twd'), 2)} {currency}",
            "股價 / consensus EPS",
        ])
    if derived.get("forward_ps_consensus") is not None:
        year = derived.get("forward_ps_fiscal_year", "next")
        rows.append([
            "Forward P/S (Consensus)",
            format_multiple(derived.get("forward_ps_consensus")),
            f"市值 {format_plain_number(market_cap, 0)} 百萬台幣",
            f"{year}E Revenue {format_plain_number(derived.get('forward_revenue_m_twd'), 0)} 百萬台幣",
            "市值 / consensus revenue",
        ])
    if not rows:
        metrics = valuation.get("metrics", {}) or {}
        if metrics.get("forward_pe") is not None:
            rows.append(["Forward P/E", format_multiple(metrics.get("forward_pe")), "NA", "NA", "provider forward P/E fallback"])
    return markdown_table(["估值指標", "數值", "分子", "分母", "使用基礎"], rows) if rows else ""


def render_valuation_section(data: dict[str, Any]) -> str:
    valuation = data.get("financials", {}).get("valuation", {}) or {}
    if not valuation:
        return ""
    meta_parts = []
    if valuation.get("as_of"):
        meta_parts.append(f"基準日: {valuation.get('as_of')}")
    if valuation.get("price") is not None:
        meta_parts.append(f"股價: {format_plain_number(valuation.get('price'), 2)} {valuation.get('currency') or 'TWD'}")
    if valuation.get("ttm_period_end"):
        meta_parts.append(f"TTM 截至: {valuation.get('ttm_period_end')}")
    if valuation.get("forward_period_end"):
        meta_parts.append(f"Forward: {valuation.get('forward_period_end')}")

    lines = ["### 估值指標"]
    if meta_parts:
        lines.extend(["", " | ".join(meta_parts)])
    lines.extend(["", "#### 市場估值", "", render_market_valuation_table(valuation)])

    consensus = valuation.get("consensus", {}) or {}
    consensus_table = render_consensus_table(consensus)
    if consensus_table:
        source_line = "Primary: Yahoo.Finance | Cross-check: FactSet | Revenue 單位: 百萬台幣"
        if consensus.get("as_of"):
            source_line = f"Consensus 截至: {consensus.get('as_of')} | " + source_line
        lines.extend(["", "#### Consensus 估值", "", source_line, "", consensus_table])
        derived_table = render_consensus_valuation_table(valuation)
        if derived_table:
            lines.extend(["", derived_table])
    return "\n".join(lines).strip()


def replace_valuation_section(financial: str, data: dict[str, Any]) -> str:
    valuation_section = render_valuation_section(data)
    if not valuation_section:
        return financial
    heading = ""
    body = financial.strip()
    if body.startswith("## "):
        lines = body.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()
    preface, sections = split_h3_sections(body)
    kept = [(h, section) for h, section in sections if not h.startswith("### 估值指標")]
    new_sections = [valuation_section] + [section for _h, section in kept]
    parts = [part for part in [heading, preface, "\n\n".join(new_sections).strip()] if part]
    return "\n\n".join(parts).strip()


def wikilinks(text: str) -> set[str]:
    return {x.strip() for x in WIKILINK_RE.findall(text) if x.strip()}


def rendered_reference_entities(text: str) -> set[str]:
    entities = wikilinks(text)
    entities.update(x.strip() for x in ENTITY_BADGE_RE.findall(text) if x.strip())
    return entities


def badge_label_text(label: str) -> str:
    # Shields badge path segments cannot contain raw spaces or non-ASCII text.
    return quote(label.replace("-", "--"), safe="")


def normalized_entity_key(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", value).lower()


def add_entity_alias(index: dict[str, str], alias: str, filename: str) -> None:
    alias = str(alias).strip()
    if not alias:
        return
    index.setdefault(alias, filename)
    normalized = normalized_entity_key(alias)
    if normalized:
        index.setdefault(normalized, filename)


def build_entity_render_index(json_dir: Path, output_dir: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for json_path in sorted(json_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ticker = str(data.get("ticker", "")).strip()
        company = str(data.get("company_name", "")).strip()
        if not ticker or not company:
            continue
        filename = f"{ticker}_{company}.md"
        if not (output_dir / filename).exists():
            continue
        aliases = {ticker, company, f"{ticker} {company}", f"{ticker}_{company}"}
        aliases.update(ENTITY_ALIAS_BY_COMPANY.get(company, []))
        for suffix in ("-KY", "-KY創", "-創"):
            if company.endswith(suffix):
                aliases.add(company[: -len(suffix)])
        for entity in data.get("entities", []) or []:
            if not isinstance(entity, dict):
                continue
            wikilink = str(entity.get("wikilink", "")).strip()
            if wikilink == company:
                aliases.add(wikilink)
        for alias in aliases:
            add_entity_alias(index, alias, filename)
    return index


def render_entity_badge(label: str, filename: str) -> str:
    return f"[![{label}](https://img.shields.io/badge/{badge_label_text(label)}-blue)]({quote(filename)})"


def theme_output_filename(theme_def: dict[str, Any]) -> str:
    render = theme_def.get("render", {}) if isinstance(theme_def.get("render"), dict) else {}
    filename = str(render.get("output_filename") or "").strip()
    if filename:
        return filename
    tag = str(theme_def.get("tag", "")).strip()
    return tag.replace(" ", "_").replace("/", "_") + ".md"


def build_theme_render_index(themes_dir: Path) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    if not themes_dir.is_dir():
        return index
    for path in sorted(themes_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tag = str(data.get("tag", "")).strip()
        if not tag:
            continue
        render = data.get("render", {}) if isinstance(data.get("render"), dict) else {}
        filename = theme_output_filename(data)
        color = str(render.get("badge_color") or THEME_BADGE_COLOR).strip()
        label = str(render.get("badge_label") or tag).strip()
        target = {"filename": filename, "color": color, "label": label}
        aliases = [tag] + [str(x).strip() for x in data.get("aliases", []) or [] if str(x).strip()]
        # Anchor entities are intentionally excluded: [[NVIDIA]] is a company, not [[NVIDIA 供應鏈]].
        for alias in aliases:
            index.setdefault(alias, target)
    return index


def render_theme_badge(display: str, target: dict[str, str]) -> str:
    label = str(target.get("label") or display).strip()
    color = str(target.get("color") or THEME_BADGE_COLOR).strip()
    filename = str(target.get("filename") or "").strip()
    if not filename:
        return f"[[{display}]]"
    return f"[![{label}](https://img.shields.io/badge/{badge_label_text(label)}-{color})](../themes/{quote(filename)})"


def normalize_badge_spacing(line: str) -> str:
    badge = r"\[!\[[^\]]+\]\(https://img\.shields\.io/badge/[^)]*\)\]\([^)]*\.md\)"
    line = re.sub(rf"(?<=[A-Za-z0-9\u4e00-\u9fff])({badge})", r" \1", line)
    return re.sub(rf"({badge})(?=[A-Za-z0-9\u4e00-\u9fff])", r"\1 ", line)


def apply_theme_badges(line: str, theme_render_index: dict[str, dict[str, str]] | None = None) -> str:
    if not theme_render_index:
        return line

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        display = raw.split("|", 1)[0].strip()
        target = theme_render_index.get(display) or theme_render_index.get(raw)
        if not target:
            return match.group(0)
        return render_theme_badge(display, target)

    return normalize_badge_spacing(WIKILINK_RE.sub(repl, line))


def apply_theme_badges_to_markdown(markdown: str, theme_render_index: dict[str, dict[str, str]] | None) -> str:
    if not theme_render_index:
        return markdown
    return "\n".join(apply_theme_badges(line, theme_render_index) for line in markdown.splitlines())


def apply_entity_badges(line: str, entity_render_index: dict[str, str] | None = None, current_filename: str = "") -> str:
    if not entity_render_index:
        return line

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        display = raw.split("|", 1)[0].strip()
        filename = (
            entity_render_index.get(display)
            or entity_render_index.get(raw)
            or entity_render_index.get(normalized_entity_key(display))
            or entity_render_index.get(normalized_entity_key(raw))
        )
        if not filename:
            return match.group(0)
        if filename == current_filename:
            return display
        return render_entity_badge(display, filename)

    return normalize_badge_spacing(WIKILINK_RE.sub(repl, line))


def apply_entity_badges_to_markdown(markdown: str, entity_render_index: dict[str, str] | None, current_filename: str) -> str:
    if not entity_render_index:
        return markdown
    return "\n".join(apply_entity_badges(line, entity_render_index, current_filename) for line in markdown.splitlines())


def load_json_files(json_dir: Path, ticker: str | None = None) -> list[Path]:
    if ticker:
        path = json_dir / f"{ticker}.json"
        return [path] if path.exists() else []
    return sorted(json_dir.glob("*.json"))


def original_md_path(coverage_root: Path, data: dict[str, Any]) -> Path:
    return coverage_root / data["source_md"]


def split_financial_section(original: str) -> str:
    idx = original.find(FINANCIAL_HEADING)
    if idx < 0:
        return ""
    return original[idx:].rstrip()


def source_enrichment_text(data: dict[str, Any]) -> str:
    source = data.get("source_text", {})
    return "\n\n".join(
        part.strip()
        for part in [
            source.get("business_summary_md", ""),
            source.get("supply_chain_md", ""),
            source.get("customers_suppliers_md", ""),
        ]
        if part and part.strip()
    )


def format_metadata(profile: dict[str, str]) -> list[str]:
    return [
        f"**板塊:** {profile.get('sector', '')}",
        f"**產業:** {profile.get('industry', '')}",
        f"**市值:** {profile.get('market_cap', '')}",
        f"**企業價值:** {profile.get('enterprise_value', '')}",
    ]


def clean_item_text(item: dict[str, Any]) -> str:
    text = str(item.get("text", "")).strip()
    role = str(item.get("role", "")).strip()
    if role and text:
        return f"- **{role}:** {text}"
    if text.startswith(('-', '*')):
        return text
    return f"- {text}" if text else ""


def is_competitive_item(item: dict[str, Any]) -> bool:
    joined = " ".join(str(item.get(k, "")) for k in ("role", "text", "category"))
    return any(x in joined for x in ["競爭", "同業競爭", "競爭同業", "競爭對手"])


def unique_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = clean_item_text(item)
        if key and key not in seen:
            out.append(item)
            seen.add(key)
    return out


def insert_platform_summary(supply_chain: str, platform_summary: str) -> str:
    supply_chain = supply_chain.strip()
    platform_summary = platform_summary.strip()
    if not supply_chain or not platform_summary or "主要平台" in supply_chain:
        return supply_chain

    lines = supply_chain.splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"^\*\*下游", line.strip()):
            lines.insert(idx + 1, platform_summary)
            return "\n".join(lines).strip()

    return supply_chain + "\n\n**下游應用:**\n" + platform_summary


def render_supply_chain(data: dict[str, Any], platform_summary: str = "") -> str:
    source = data.get("source_text", {}).get("supply_chain_md", "").strip()
    if source:
        return insert_platform_summary(source, platform_summary)
    lines: list[str] = []
    labels = [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游"), ("other", "其他")]
    for key, label in labels:
        items = data.get("supply_chain", {}).get(key, []) or []
        if not items:
            continue
        lines.append(f"**{label}:**")
        if key == "downstream" and platform_summary and "主要平台" not in "\n".join(lines):
            lines.append(platform_summary)
        for item in items:
            line = clean_item_text(item)
            if line:
                lines.append(line)
        lines.append("")
    return "\n".join(lines).strip()


def render_relationship_section(data: dict[str, Any], entity_render_index: dict[str, str] | None = None) -> str:
    rel = data.get("relationships", {})
    groups = [
        ("customers", "主要客戶"),
        ("suppliers", "主要供應商"),
        ("competitors", "競爭同業"),
        ("peers", "同業參照"),
        ("substitutes", "替代關係"),
        ("other", "其他關係"),
    ]
    lines: list[str] = []
    for key, title in groups:
        raw_items = rel.get(key, []) or []
        if key == "suppliers":
            competitor_entities = {
                entity
                for item in (rel.get("competitors", []) or [])
                for entity in (item.get("entities") or [])
            }
            raw_items = [
                item
                for item in raw_items
                if (not is_competitive_item(item)) or bool(set(item.get("entities") or []) - competitor_entities)
            ]
        items = unique_items(raw_items)
        if not items:
            continue
        lines.append(f"### {title}")
        for item in items:
            line = clean_item_text(item)
            if line:
                lines.append(line)
        lines.append("")
    return "\n".join(lines).strip()


def render_competitive_position(data: dict[str, Any], entity_render_index: dict[str, str] | None = None) -> str:
    comp = data.get("competitive_position", {})
    groups = [("moats", "核心競爭力"), ("risks", "競爭與營運風險"), ("notes", "競爭定位補充")]
    lines: list[str] = []
    for key, title in groups:
        items = unique_items(comp.get(key, []) or [])
        if not items:
            continue
        lines.append(f"## {title}")
        for item in items:
            line = clean_item_text(item)
            if line:
                lines.append(line)
        lines.append("")
    return "\n".join(lines).strip()


def render_markdown(data: dict[str, Any], original: str, segment_weight_tables: dict[str, str] | None = None, segment_weight_summaries: dict[str, str] | None = None, monthly_revenue_totals: dict[str, dict[str, float]] | None = None, competitor_financial_section: str = "", updated_at: str = "", entity_render_index: dict[str, str] | None = None, theme_render_index: dict[str, dict[str, str]] | None = None) -> str:
    title = data.get("title") or f"{data.get('ticker', '')} - [[{data.get('company_name', '')}]]"
    profile = data.get("profile", {})
    business_summary = data.get("business", {}).get("summary", "").strip()
    ticker = str(data.get("ticker", "")).strip()
    platform_summary = segment_weight_summaries.get(ticker, "") if segment_weight_summaries else ""
    financial = str(data.get("source_text", {}).get("financial_md", "")).strip()
    financial = replace_valuation_section(financial, data)
    financial = add_eps_rows_to_key_tables(financial, data.get("financials", {}).get("actual_eps", {}) or {})
    platform_table = render_segment_revenue_platforms_from_evidence(data)
    platform_table_from_evidence = bool(platform_table)
    if not platform_table and segment_weight_tables:
        platform_table = segment_weight_tables.get(ticker, "")
    if platform_table:
        financial = insert_platform_revenue_section(financial, platform_table, replace_existing=platform_table_from_evidence)
    financial = normalize_financial_section(financial)
    financial = add_revenue_amounts_to_platform_table(financial, (monthly_revenue_totals or {}).get(ticker, {}))
    financial = insert_competitor_financial_section(financial, competitor_financial_section)

    parts: list[str] = [f"# {title}", "", "## 業務簡介"]
    parts.extend(format_metadata(profile))
    parts.extend(["", business_summary, "", "## 供應鏈位置", render_supply_chain(data, platform_summary), "", "## 主要客戶及供應商", render_relationship_section(data, entity_render_index)])
    competitive = render_competitive_position(data, entity_render_index)
    if competitive:
        parts.extend(["", competitive])
    if financial:
        heading = financial if financial.startswith("## ") else "## 財務概況 (單位: 百萬台幣, 只有 Margin 為 %)\n" + financial
        parts.extend(["", heading])
    rendered = "\n".join(part.rstrip() for part in parts).rstrip()
    rendered = apply_annotations(rendered, data)
    rendered = apply_theme_badges_to_markdown(rendered, theme_render_index)
    current_filename = f"{ticker}_{data.get('company_name', '')}.md"
    rendered = apply_entity_badges_to_markdown(rendered, entity_render_index, current_filename)
    if updated_at:
        rendered = rendered.rstrip() + "\n\n" + f"Updated: {updated_at}"
    return rendered.rstrip() + "\n"


def compare(original: str, rendered: str, data: dict[str, Any]) -> dict[str, Any]:
    source_links = wikilinks(source_enrichment_text(data))
    rendered_links = rendered_reference_entities(rendered)
    missing_links = sorted(source_links - rendered_links)
    source_sections = data.get("source_text", {})
    section_results = []
    for key in ["business_summary_md", "supply_chain_md"]:
        text = str(source_sections.get(key, "")).strip()
        if text and text not in rendered:
            section_results.append(key)
    return {
        "ticker": data.get("ticker", ""),
        "company_name": data.get("company_name", ""),
        "source_md": data.get("source_md", ""),
        "rendered_md": "",
        "source_wikilinks": len(source_links),
        "rendered_wikilinks": len(rendered_links),
        "missing_wikilinks": ";".join(missing_links),
        "missing_source_sections": ";".join(section_results),
        "financial_preserved": str(bool(data.get("source_text", {}).get("financial_md", ""))).lower(),
        "competitor_count": len(data.get("relationships", {}).get("competitors", []) or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--coverage-root", default=".")
    parser.add_argument("--out", default="output/enrichment_all_rendered")
    parser.add_argument("--compare", default="output/enrichment_all_render_compare.csv")
    parser.add_argument("--segment-weights", default="../biztrends.TW/data/company_segment_weights.csv")
    parser.add_argument("--monthly-revenue", default="../biztrends.TW/data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv")
    parser.add_argument("--biztrends-root", default="../biztrends.TW")
    parser.add_argument("--themes-dir", default="data/themes")
    parser.add_argument("--competitor-financial-years", type=int, default=3)
    parser.add_argument("--updated-at", default=DEFAULT_UPDATED_AT)
    parser.add_argument("--ticker")
    args = parser.parse_args()

    json_dir = Path(args.json_dir).resolve()
    coverage_root = Path(args.coverage_root).resolve()
    out_dir = Path(args.out).resolve()
    compare_path = Path(args.compare).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    compare_path.parent.mkdir(parents=True, exist_ok=True)

    segment_weights_path = Path(args.segment_weights)
    if not segment_weights_path.is_absolute():
        segment_weights_path = (coverage_root / segment_weights_path).resolve()
    segment_weight_tables = load_segment_weight_tables(segment_weights_path)
    segment_weight_summaries = load_segment_weight_summaries(segment_weights_path)
    monthly_revenue_path = Path(args.monthly_revenue)
    if not monthly_revenue_path.is_absolute():
        monthly_revenue_path = (coverage_root / monthly_revenue_path).resolve()
    monthly_revenue_totals = load_monthly_revenue_totals(monthly_revenue_path)
    biztrends_root = Path(args.biztrends_root)
    if not biztrends_root.is_absolute():
        biztrends_root = (coverage_root / biztrends_root).resolve()
    health_summary, health_issues = render_data_health_summary(biztrends_root)
    print(health_summary)
    if health_issues:
        for issue in health_issues:
            print(f"Data health issue: {issue}", file=sys.stderr)
        return 2

    competitor_adapter = load_competitor_financial_adapter(coverage_root)
    entity_render_index = build_entity_render_index(json_dir, out_dir)
    themes_dir = Path(args.themes_dir)
    if not themes_dir.is_absolute():
        themes_dir = (coverage_root / themes_dir).resolve()
    theme_render_index = build_theme_render_index(themes_dir)

    rows = []
    written = 0
    for json_path in load_json_files(json_dir, args.ticker):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        src = original_md_path(coverage_root, data)
        original = src.read_text(encoding="utf-8") if src.exists() else ""
        competitor_financial_section = ""
        if competitor_adapter is not None:
            competitor_financial_section = competitor_adapter.render_competitor_financial_section(
                data,
                json_dir,
                biztrends_root,
                args.competitor_financial_years,
            )
        rendered = render_markdown(data, "", segment_weight_tables, segment_weight_summaries, monthly_revenue_totals, competitor_financial_section, args.updated_at, entity_render_index, theme_render_index)
        out_path = out_dir / f"{data['ticker']}_{data['company_name']}.md"
        out_path.write_text(rendered, encoding="utf-8")
        row = compare(original, rendered, data)
        row["rendered_md"] = str(out_path.relative_to(coverage_root)) if out_path.is_relative_to(coverage_root) else str(out_path)
        rows.append(row)
        written += 1

    fields = [
        "ticker",
        "company_name",
        "source_md",
        "rendered_md",
        "source_wikilinks",
        "rendered_wikilinks",
        "missing_wikilinks",
        "missing_source_sections",
        "financial_preserved",
        "competitor_count",
    ]
    with compare_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Rendered Markdown: {written}")
    print(f"Output: {out_dir}")
    print(f"Compare: {compare_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
