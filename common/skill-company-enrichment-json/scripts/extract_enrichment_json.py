#!/usr/bin/env python3
"""Extract My-TW-Coverage Markdown enrichment into atomic canonical JSON.

The extractor is intentionally conservative: it preserves source Markdown
snippets and emits warnings when text cannot be safely atomized.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
HEADING_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(.+?)[:：]\*\*\s*(.*)$")
REL_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)

COMPETITOR_PATTERNS = [
    "競爭對手",
    "主要競爭對手",
    "競爭同業",
    "同業競爭",
    "競爭:",
    "競爭：",
]
PEER_PATTERNS = ["同業包括", "同業比較", "同業資金"]
SUBSTITUTE_PATTERNS = ["替代", "取代", "自研", "轉自製"]
MOAT_PATTERNS = ["核心競爭力", "競爭優勢", "利基", "技術領先", "成本優勢", "良率", "客戶黏著"]
RISK_PATTERNS = ["風險", "競爭加劇", "紅海競爭", "營收下滑", "毛利壓力"]


@dataclass
class FocusRow:
    ticker: str
    company_name: str


def focus_rows_from_reports(files: dict[str, Path]) -> list[FocusRow]:
    rows: list[FocusRow] = []
    for ticker, path in sorted(files.items()):
        name = path.stem.split("_", 1)[1] if "_" in path.stem else ""
        rows.append(FocusRow(ticker=ticker, company_name=name))
    return rows



def entity_type_for_name(name: str) -> str:
    return "taiwan_company_or_term" if any("\u4e00" <= ch <= "\u9fff" for ch in name) else "international_company_or_term"


def now_cst() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S CST")


def read_focus(path: Path) -> list[FocusRow]:
    rows: list[FocusRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("代號") or row.get("ticker") or "").strip()
            name = (row.get("名稱") or row.get("company_name") or "").strip()
            if re.fullmatch(r"\d{4}", ticker):
                rows.append(FocusRow(ticker=ticker, company_name=name))
    return rows


def find_report_files(coverage_root: Path) -> dict[str, Path]:
    reports_dir = coverage_root / "Pilot_Reports"
    files: dict[str, Path] = {}
    for path in reports_dir.rglob("*.md"):
        match = re.match(r"^(\d{4})_", path.name)
        if match:
            files.setdefault(match.group(1), path)
    return files


def split_sections(content: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(content))
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        sections[name] = content[start:end].strip()
    return sections


def extract_title(content: str) -> str:
    first = content.splitlines()[0].strip() if content.splitlines() else ""
    return first[2:].strip() if first.startswith("# ") else first


def extract_metadata(business_body: str) -> tuple[dict[str, str], str]:
    metadata: dict[str, str] = {}
    remaining_lines: list[str] = []
    in_metadata = True
    for line in business_body.splitlines():
        m = re.match(r"^\*\*(板塊|產業|市值|企業價值):\*\*\s*(.*)$", line.strip())
        if in_metadata and m:
            metadata[m.group(1)] = m.group(2).strip()
            continue
        if line.strip() == "" and in_metadata:
            continue
        in_metadata = False
        remaining_lines.append(line)
    return metadata, "\n".join(remaining_lines).strip()


def wikilinks(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in WIKILINK_RE.findall(text):
        name = item.strip()
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def classify_entity(name: str) -> str:
    tech_terms = {"AI", "PCB", "HBM", "CoWoS", "EUV", "CPO", "FOPLP", "MLCC", "MOSFET", "IGBT", "DRAM", "NAND", "SSD"}
    if name in tech_terms:
        return "technology"
    if any("\u4e00" <= c <= "\u9fff" for c in name):
        return "taiwan_company_or_term"
    return "international_company_or_term"


def parse_supply_chain(body: str) -> dict[str, list[dict[str, Any]]]:
    buckets = {"upstream": [], "midstream": [], "downstream": [], "other": []}
    current = "other"
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "上游" in line:
            current = "upstream"
        elif "中游" in line:
            current = "midstream"
        elif "下游" in line:
            current = "downstream"
        m = HEADING_RE.match(line)
        if m:
            category, rest = m.group(1).strip(), m.group(2).strip()
        else:
            category, rest = "", re.sub(r"^[-*]\s*", "", line)
        buckets[current].append(
            {
                "category": category,
                "text": rest or line,
                "entities": wikilinks(line),
            }
        )
    return buckets


def parse_customer_supplier(body: str) -> dict[str, list[dict[str, Any]]]:
    rels = {"customers": [], "suppliers": [], "competitors": [], "peers": [], "other": []}
    current = "other"
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("###"):
            title = line.lstrip("#").strip()
            if "客戶" in title:
                current = "customers"
            elif "供應商" in title:
                current = "suppliers"
            elif "競爭" in title:
                current = "competitors"
            elif "同業" in title:
                current = "peers"
            else:
                current = "other"
            continue
        if not line.startswith(("-", "*")):
            continue
        m = HEADING_RE.match(line)
        role = m.group(1).strip() if m else ""
        text = m.group(2).strip() if m else re.sub(r"^[-*]\s*", "", line)
        rels[current].append({"role": role, "text": text, "entities": wikilinks(line)})
    return rels


def lines_matching(text: str, patterns: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and any(p in line for p in patterns):
            out.append({"text": line, "entities": wikilinks(line)})
    return out


def build_json(focus: FocusRow, path: Path, coverage_root: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    sections = split_sections(content)
    business_body = sections.get("業務簡介", "")
    metadata, business_summary = extract_metadata(business_body)
    supply_text = sections.get("供應鏈位置", "")
    rel_text = sections.get("主要客戶及供應商", "")
    enrichment_text = "\n".join([business_summary, supply_text, rel_text])
    parsed_rels = parse_customer_supplier(rel_text)
    all_text = "\n".join([business_summary, supply_text, rel_text])

    competitors = parsed_rels["competitors"] + lines_matching(all_text, COMPETITOR_PATTERNS)
    peers = parsed_rels["peers"] + lines_matching(all_text, PEER_PATTERNS)
    substitutes = lines_matching(all_text, SUBSTITUTE_PATTERNS)
    moats = lines_matching(all_text, MOAT_PATTERNS)
    risks = lines_matching(all_text, RISK_PATTERNS)
    all_links = wikilinks(enrichment_text)
    warnings = []
    if focus.company_name and focus.company_name not in path.name:
        warnings.append("focus_company_name_does_not_match_filename")
    if not business_summary:
        warnings.append("missing_business_summary")
    if not supply_text:
        warnings.append("missing_supply_chain_section")
    if not rel_text:
        warnings.append("missing_customer_supplier_section")

    return {
        "schema_version": "0.1.0",
        "ticker": focus.ticker,
        "company_name": focus.company_name,
        "title": extract_title(content),
        "source_md": str(path.relative_to(coverage_root)),
        "extracted_at": now_cst(),
        "profile": {
            "sector": metadata.get("板塊", ""),
            "industry": metadata.get("產業", ""),
            "market_cap": metadata.get("市值", ""),
            "enterprise_value": metadata.get("企業價值", ""),
        },
        "business": {
            "summary": business_summary,
            "entities": wikilinks(business_summary),
        },
        "supply_chain": parse_supply_chain(supply_text),
        "relationships": {
            "customers": parsed_rels["customers"],
            "suppliers": parsed_rels["suppliers"],
            "competitors": competitors,
            "peers": peers,
            "substitutes": substitutes,
            "other": parsed_rels["other"],
        },
        "competitive_position": {
            "moats": moats,
            "risks": risks,
            "notes": lines_matching(all_text, ["競爭力", "競爭優勢", "紅海"]),
        },
        "entities": [{"name": name, "type": classify_entity(name), "wikilink": name} for name in all_links],
        "source_text": {
            "business_summary_md": business_summary,
            "supply_chain_md": supply_text,
            "customers_suppliers_md": rel_text,
            "financial_md": sections.get("財務概況 (單位: 百萬台幣, 只有 Margin 為 %)", ""),
        },
        "quality": {
            "parser_status": "parsed",
            "review_status": "needs_review",
            "wikilink_count": len(all_links),
            "warnings": warnings,
        },
    }


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ticker",
        "company_name",
        "source_md",
        "json_path",
        "status",
        "warnings",
        "extracted_at",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus")
    parser.add_argument("--coverage-root")
    parser.add_argument("--out")
    parser.add_argument("--manifest")
    parser.add_argument("--ticker", action="append", help="Limit to one ticker; can be repeated.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all-reports", action="store_true", help="Extract every Pilot_Reports Markdown file instead of the focus list.")
    args = parser.parse_args()

    cwd = Path.cwd()
    default_coverage_root = cwd if (cwd / "Pilot_Reports").exists() else cwd / "../My-TW-Coverage"
    default_focus = (
        cwd / "StockID_TWSE_TPEX_focus.csv"
        if (cwd / "StockID_TWSE_TPEX_focus.csv").exists()
        else cwd / "../biztrends.TW/StockID_TWSE_TPEX_focus.csv"
    )
    focus_path = Path(args.focus).resolve() if args.focus else default_focus.resolve()
    coverage_root = Path(args.coverage_root).resolve() if args.coverage_root else default_coverage_root.resolve()
    default_out = coverage_root / "data" / "enrichment_all"
    default_manifest = coverage_root / "data" / "enrichment_all_manifest.csv"
    out_dir = Path(args.out).resolve() if args.out else default_out
    manifest_path = Path(args.manifest).resolve() if args.manifest else default_manifest
    out_dir.mkdir(parents=True, exist_ok=True)

    files = find_report_files(coverage_root)
    focus_rows = focus_rows_from_reports(files) if args.all_reports else read_focus(focus_path)
    if args.ticker:
        wanted = set(args.ticker)
        focus_rows = [row for row in focus_rows if row.ticker in wanted]
    if args.limit:
        focus_rows = focus_rows[: args.limit]
    manifest_rows: list[dict[str, str]] = []
    written = missing = 0
    for row in focus_rows:
        source = files.get(row.ticker)
        if not source:
            missing += 1
            manifest_rows.append(
                {
                    "ticker": row.ticker,
                    "company_name": row.company_name,
                    "source_md": "",
                    "json_path": "",
                    "status": "blocked_missing_md",
                    "warnings": "missing_md",
                    "extracted_at": now_cst(),
                }
            )
            continue
        data = build_json(row, source, coverage_root)
        out_path = out_dir / f"{row.ticker}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
        manifest_rows.append(
            {
                "ticker": row.ticker,
                "company_name": row.company_name,
                "source_md": data["source_md"],
                "json_path": str(out_path),
                "status": data["quality"]["review_status"],
                "warnings": ";".join(data["quality"]["warnings"]),
                "extracted_at": data["extracted_at"],
            }
        )

    write_manifest(manifest_path, manifest_rows)
    print(f"Focus rows: {len(focus_rows)}")
    print(f"JSON written: {written}")
    print(f"Missing markdown: {missing}")
    print(f"Output: {out_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
