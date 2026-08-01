#!/usr/bin/env python3
"""Apply curated competitor overrides to enrichment JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def classify_entity(name: str) -> str:
    tech_terms = {"AI", "PCB", "HBM", "CoWoS", "EUV", "CPO", "FOPLP", "MLCC", "MOSFET", "IGBT", "DRAM", "NAND", "SSD"}
    if name in tech_terms:
        return "technology"
    if any("\u4e00" <= c <= "\u9fff" for c in name):
        return "taiwan_company_or_term"
    return "international_company_or_term"


def competitor_item(entry: dict[str, Any], company_name: str) -> dict[str, Any]:
    entities = [name for name in entry.get("entities", []) if name and name != company_name]
    text = entry.get("text", "").strip()
    text = __import__("re").sub(r"^-\s*\*\*[^:*：]+[:：]\*\*\s*", "", text)
    return {
        "role": entry.get("label", "競爭同業"),
        "text": text,
        "entities": entities,
        "basis": entry.get("basis", "curated_competitor_override"),
        "review_status": entry.get("review_status", "needs_review"),
    }


def apply_override(path: Path, entry: dict[str, Any], replace_existing: bool) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    rel = data.setdefault("relationships", {})
    existing_competitors = rel.get("competitors") or []
    if existing_competitors and not replace_existing:
        return False

    item = competitor_item(entry, data.get("company_name", ""))
    if not item["entities"]:
        return False

    rel["competitors"] = [item]
    known = {ent.get("name") for ent in data.get("entities", []) if isinstance(ent, dict)}
    for name in item["entities"]:
        if name not in known:
            data.setdefault("entities", []).append({"name": name, "type": classify_entity(name), "wikilink": name})
            known.add(name)

    warnings = data.setdefault("quality", {}).setdefault("warnings", [])
    if "competitors_curated_override_needs_review" not in warnings:
        warnings.append("competitors_curated_override_needs_review")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--overrides", default="data/enrichment_competitor_overrides.json")
    parser.add_argument("--replace-existing", action="store_true", help="Replace existing competitor entries instead of filling only empty arrays.")
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    overrides = json.loads(Path(args.overrides).read_text(encoding="utf-8"))["overrides"]
    applied = skipped_existing = missing = 0
    for ticker, entry in sorted(overrides.items()):
        path = json_dir / f"{ticker}.json"
        if not path.exists():
            missing += 1
            continue
        before = json.loads(path.read_text(encoding="utf-8")).get("relationships", {}).get("competitors") or []
        changed = apply_override(path, entry, args.replace_existing)
        if changed:
            applied += 1
        elif before and not args.replace_existing:
            skipped_existing += 1
    print(f"overrides={len(overrides)}")
    print(f"applied={applied}")
    print(f"skipped_existing={skipped_existing}")
    print(f"missing_json={missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
