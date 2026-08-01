#!/usr/bin/env python3
"""Ensure local competitor relationships are reciprocal across enrichment JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def classify_entity(name: str) -> str:
    if any("\u4e00" <= c <= "\u9fff" for c in name):
        return "taiwan_company_or_term"
    return "international_company_or_term"


def load_json(json_dir: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(json_dir.glob("*.json")):
        out[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


def item_entities(data: dict[str, Any]) -> set[str]:
    return {
        entity
        for item in data.get("relationships", {}).get("competitors", []) or []
        for entity in (item.get("entities") or [])
    }


def ensure_entity(data: dict[str, Any], name: str) -> None:
    existing = {item.get("name") for item in data.get("entities", []) if isinstance(item, dict)}
    if name not in existing:
        data.setdefault("entities", []).append({"name": name, "type": classify_entity(name), "wikilink": name})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--basis-prefix", default="curated_", help="Only reciprocal-sync competitor items whose basis starts with this prefix. Use empty string for all.")
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    data_by_ticker = load_json(json_dir)
    name_to_ticker = {
        data.get("company_name", ""): ticker
        for ticker, data in data_by_ticker.items()
        if data.get("company_name")
    }

    additions: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in data_by_ticker}
    seen_edges: set[tuple[str, str]] = set()
    for source_ticker, source_data in data_by_ticker.items():
        source_name = source_data.get("company_name", "")
        if not source_name:
            continue
        for item in source_data.get("relationships", {}).get("competitors", []) or []:
            basis = str(item.get("basis", ""))
            if args.basis_prefix and not basis.startswith(args.basis_prefix):
                continue
            for entity in item.get("entities") or []:
                target_ticker = name_to_ticker.get(entity)
                if not target_ticker or target_ticker == source_ticker:
                    continue
                target_data = data_by_ticker[target_ticker]
                if source_name in item_entities(target_data):
                    continue
                edge = (target_ticker, source_name)
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                additions[target_ticker].append({
                    "role": "競爭同業",
                    "text": f"[[{source_name}]]",
                    "entities": [source_name],
                    "basis": f"reciprocal_competitor_from:{source_ticker}",
                    "review_status": "needs_review",
                })

    changed = 0
    added = 0
    for ticker, items in additions.items():
        if not items:
            continue
        data = data_by_ticker[ticker]
        rel = data.setdefault("relationships", {})
        rel.setdefault("competitors", [])
        rel["competitors"].extend(items)
        for item in items:
            for entity in item["entities"]:
                ensure_entity(data, entity)
        warnings = data.setdefault("quality", {}).setdefault("warnings", [])
        if "competitors_reciprocal_edges_need_review" not in warnings:
            warnings.append("competitors_reciprocal_edges_need_review")
        (json_dir / f"{ticker}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += 1
        added += len(items)

    print(f"json_files={len(data_by_ticker)}")
    print(f"files_changed={changed}")
    print(f"reciprocal_items_added={added}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
