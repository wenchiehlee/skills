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


def render_supply_chain(data: dict[str, Any]) -> str:
    source = data.get("source_text", {}).get("supply_chain_md", "").strip()
    if source:
        return source
    lines: list[str] = []
    labels = [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游"), ("other", "其他")]
    for key, label in labels:
        items = data.get("supply_chain", {}).get(key, []) or []
        if not items:
            continue
        lines.append(f"**{label}:**")
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


def render_markdown(data: dict[str, Any], original: str) -> str:
    title = data.get("title") or f"{data.get('ticker', '')} - [[{data.get('company_name', '')}]]"
    profile = data.get("profile", {})
    business_summary = data.get("business", {}).get("summary", "").strip()
    financial = str(data.get("source_text", {}).get("financial_md", "")).strip()

    parts: list[str] = [f"# {title}", "", "## 業務簡介"]
    parts.extend(format_metadata(profile))
    parts.extend(["", business_summary, "", "## 供應鏈位置", render_supply_chain(data), "", "## 主要客戶及供應商", render_relationship_section(data)])
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
    parser.add_argument("--ticker")
    args = parser.parse_args()

    json_dir = Path(args.json_dir).resolve()
    coverage_root = Path(args.coverage_root).resolve()
    out_dir = Path(args.out).resolve()
    compare_path = Path(args.compare).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    compare_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    written = 0
    for json_path in load_json_files(json_dir, args.ticker):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        src = original_md_path(coverage_root, data)
        original = src.read_text(encoding="utf-8") if src.exists() else ""
        rendered = render_markdown(data, "")
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
