#!/usr/bin/env python3
"""Backfill or review company theme links from canonical enrichment JSON.

This script distinguishes theme objects from company entities. Brand supply-chain
themes can use anchor_entities such as Apple or NVIDIA only in customer,
supplier, or supply-chain contexts. Those anchors are not theme aliases and do
not change entity badge behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_theme_defs(themes_dir: Path) -> dict[str, dict[str, Any]]:
    defs: dict[str, dict[str, Any]] = {}
    for path in sorted(themes_dir.glob("*.json")):
        data = read_json(path)
        tag = str(data.get("tag", "")).strip()
        theme_id = str(data.get("id", "")).strip()
        if tag and theme_id:
            defs[tag] = data
    return defs


def item_entities(item: dict[str, Any]) -> set[str]:
    text = str(item.get("text", ""))
    values = {str(x).strip() for x in item.get("entities", []) or [] if str(x).strip()}
    values.update(x.strip().split("|", 1)[0].strip() for x in WIKILINK_RE.findall(text) if x.strip())
    return values


def text_matches(text: str, needle: str) -> bool:
    if not needle:
        return False
    if f"[[{needle}]]" in text:
        return True
    if re.search(r"[A-Za-z0-9]", needle):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None
    return needle in text


def role_from_path(path: str) -> str:
    if "supply_chain.upstream" in path or "relationships.suppliers" in path:
        return "upstream"
    if "supply_chain.midstream" in path:
        return "midstream"
    if "supply_chain.downstream" in path or "relationships.customers" in path:
        return "downstream"
    return "related"


def iter_contexts(data: dict[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    business = data.get("business", {}) if isinstance(data.get("business"), dict) else {}
    if business.get("summary"):
        contexts.append({"path": "business.summary", "text": str(business.get("summary", "")), "entities": set(business.get("entities", []) or [])})
    supply_chain = data.get("supply_chain", {}) if isinstance(data.get("supply_chain"), dict) else {}
    for key in ("upstream", "midstream", "downstream", "other"):
        for idx, item in enumerate(supply_chain.get(key, []) or []):
            if isinstance(item, dict):
                contexts.append({"path": f"supply_chain.{key}[{idx}]", "text": " ".join(str(item.get(k, "")) for k in ("category", "text")), "entities": item_entities(item)})
    relationships = data.get("relationships", {}) if isinstance(data.get("relationships"), dict) else {}
    for key in ("customers", "suppliers", "competitors", "peers", "substitutes", "other"):
        for idx, item in enumerate(relationships.get(key, []) or []):
            if isinstance(item, dict):
                contexts.append({"path": f"relationships.{key}[{idx}]", "text": " ".join(str(item.get(k, "")) for k in ("role", "category", "text")), "entities": item_entities(item)})
    return contexts


def theme_terms(theme_def: dict[str, Any], source_path: str) -> list[str]:
    terms = [str(theme_def.get("tag", "")).strip()]
    terms.extend(str(x).strip() for x in theme_def.get("aliases", []) or [])
    if str(theme_def.get("type", "")) == "brand_supply_chain_theme" and (
        source_path.startswith("relationships.customers")
        or source_path.startswith("relationships.suppliers")
        or source_path.startswith("supply_chain.")
    ):
        terms.extend(str(x).strip() for x in theme_def.get("anchor_entities", []) or [])
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term and term not in seen:
            out.append(term)
            seen.add(term)
    return out


def detect_theme_links(data: dict[str, Any], theme_defs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for context in iter_contexts(data):
        text = str(context["text"])
        entities = set(context.get("entities") or [])
        source_path = str(context["path"])
        for tag, theme_def in theme_defs.items():
            matched = ""
            for term in theme_terms(theme_def, source_path):
                if term in entities or text_matches(text, term):
                    matched = term
                    break
            if not matched:
                continue
            key = (str(theme_def["id"]), source_path)
            if key in seen:
                continue
            seen.add(key)
            links.append({
                "id": theme_def["id"],
                "tag": tag,
                "role": role_from_path(source_path),
                "source_path": source_path,
                "matched_text": matched,
                "confidence": "medium" if matched in set(theme_def.get("anchor_entities", []) or []) else "high",
                "status": "needs_review",
            })
    return links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--themes-dir", default="data/themes")
    parser.add_argument("--review-out", default="output/theme_link_review_queue.csv")
    parser.add_argument("--ticker")
    parser.add_argument("--write", action="store_true", help="Write detected links to each JSON file's themes[] array")
    args = parser.parse_args()

    json_dir = Path(args.json_dir).resolve()
    themes_dir = Path(args.themes_dir).resolve()
    review_out = Path(args.review_out).resolve()
    review_out.parent.mkdir(parents=True, exist_ok=True)
    theme_defs = load_theme_defs(themes_dir)
    json_paths = [json_dir / f"{args.ticker}.json"] if args.ticker else sorted(json_dir.glob("*.json"))

    rows: list[dict[str, str]] = []
    changed = 0
    for path in json_paths:
        if not path.exists():
            continue
        data = read_json(path)
        detected = detect_theme_links(data, theme_defs)
        if args.write:
            existing = [x for x in data.get("themes", []) or [] if isinstance(x, dict)]
            existing_keys = {(str(x.get("id") or x.get("theme_id")), str(x.get("source_path"))) for x in existing}
            additions = [x for x in detected if (str(x.get("id")), str(x.get("source_path"))) not in existing_keys]
            if additions:
                data["themes"] = existing + additions
                write_json(path, data)
                changed += 1
        for item in detected:
            rows.append({
                "ticker": str(data.get("ticker", "")),
                "company_name": str(data.get("company_name", "")),
                "theme_id": str(item.get("id", "")),
                "theme_tag": str(item.get("tag", "")),
                "role": str(item.get("role", "")),
                "source_path": str(item.get("source_path", "")),
                "matched_text": str(item.get("matched_text", "")),
                "confidence": str(item.get("confidence", "")),
                "status": str(item.get("status", "")),
            })

    fields = ["ticker", "company_name", "theme_id", "theme_tag", "role", "source_path", "matched_text", "confidence", "status"]
    with review_out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Theme links detected: {len(rows)}")
    print(f"JSON files changed: {changed}")
    print(f"Review queue: {review_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
