#!/usr/bin/env python3
"""Render canonical enrichment JSON back to preview Markdown and compare coverage.

Rendering is JSON-only and never overwrites Pilot_Reports. When source Markdown is
available, the compare CSV uses it as validation context only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
FINANCIAL_HEADING = "## 財務概況"
PLATFORM_REVENUE_HEADING = "### 營收平台佔比 (Revenue by Platform %)"
QUARTERLY_HEADING = "### 季度關鍵財務數據 (近 4 季)"
H3_RE = re.compile(r"(?m)^### .*$")



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

def insert_platform_revenue_section(financial: str, platform_section: str) -> str:
    financial = financial.strip()
    platform_section = platform_section.strip()
    if not financial or not platform_section or PLATFORM_REVENUE_HEADING in financial:
        return financial

    heading = ""
    body = financial
    if financial.startswith("## "):
        lines = financial.splitlines()
        heading = lines[0].rstrip()
        body = "\n".join(lines[1:]).strip()

    preface, sections = split_h3_sections(body)
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


def wikilinks(text: str) -> set[str]:
    return {x.strip() for x in WIKILINK_RE.findall(text) if x.strip()}


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


def render_relationship_section(data: dict[str, Any]) -> str:
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


def render_competitive_position(data: dict[str, Any]) -> str:
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


def render_markdown(data: dict[str, Any], original: str, segment_weight_tables: dict[str, str] | None = None, segment_weight_summaries: dict[str, str] | None = None, monthly_revenue_totals: dict[str, dict[str, float]] | None = None) -> str:
    title = data.get("title") or f"{data.get('ticker', '')} - [[{data.get('company_name', '')}]]"
    profile = data.get("profile", {})
    business_summary = data.get("business", {}).get("summary", "").strip()
    ticker = str(data.get("ticker", "")).strip()
    platform_summary = segment_weight_summaries.get(ticker, "") if segment_weight_summaries else ""
    financial = str(data.get("source_text", {}).get("financial_md", "")).strip()
    if segment_weight_tables:
        financial = insert_platform_revenue_section(financial, segment_weight_tables.get(ticker, ""))
    financial = normalize_financial_section(financial)
    financial = add_revenue_amounts_to_platform_table(financial, (monthly_revenue_totals or {}).get(ticker, {}))

    parts: list[str] = [f"# {title}", "", "## 業務簡介"]
    parts.extend(format_metadata(profile))
    parts.extend(["", business_summary, "", "## 供應鏈位置", render_supply_chain(data, platform_summary), "", "## 主要客戶及供應商", render_relationship_section(data)])
    competitive = render_competitive_position(data)
    if competitive:
        parts.extend(["", competitive])
    if financial:
        heading = financial if financial.startswith("## ") else "## 財務概況 (單位: 百萬台幣, 只有 Margin 為 %)\n" + financial
        parts.extend(["", heading])
    return "\n".join(part.rstrip() for part in parts).rstrip() + "\n"


def compare(original: str, rendered: str, data: dict[str, Any]) -> dict[str, Any]:
    source_links = wikilinks(source_enrichment_text(data))
    rendered_links = wikilinks(rendered)
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

    rows = []
    written = 0
    for json_path in load_json_files(json_dir, args.ticker):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        src = original_md_path(coverage_root, data)
        original = src.read_text(encoding="utf-8") if src.exists() else ""
        rendered = render_markdown(data, "", segment_weight_tables, segment_weight_summaries, monthly_revenue_totals)
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
