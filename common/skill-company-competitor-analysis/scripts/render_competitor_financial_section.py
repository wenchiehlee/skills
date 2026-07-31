#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER_PATH = SCRIPT_DIR / "run_company_competitor_analysis.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("company_competitor_analysis_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load competitor analysis runner: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CCA = load_runner()
_ORIGINAL_CCA_READ_CSV = CCA.read_csv


@lru_cache(maxsize=None)
def cached_cca_read_csv(path_text: str) -> tuple[tuple[tuple[str, str], ...], ...]:
    rows = _ORIGINAL_CCA_READ_CSV(Path(path_text))
    return tuple(tuple(row.items()) for row in rows)


def cca_read_csv_cached(path: Path) -> list[dict[str, str]]:
    return [dict(items) for items in cached_cca_read_csv(str(path))]


CCA.read_csv = cca_read_csv_cached
_ALIAS_CACHE: dict[tuple[str, str], dict[str, str]] = {}

KNOWN_ALIASES = {
    "光寶科技": "2301",
    "光寶科": "2301",
    "Qualcomm": "QCOM",
    "Broadcom": "AVGO",
    "Samsung LSI": "005930.KS",
    "Samsung System LSI": "005930.KS",
    "GlobalFoundries": "GFS",
    "GlobalFoundries Inc.": "GFS",
    "Intel Foundry": "INTC",
    "Intel": "INTC",
    "中芯國際": "0981.HK",
    "SMIC": "0981.HK",
    "Samsung Foundry": "005930.KS",
    "Samsung Electronics": "005930.KS",
    "世界": "5347",
    "世界先進": "5347",
    "力積電": "6770",
    "聯電": "2303",
    "UMC": "2303",
}

USD_TO_TWD_RATE = 32.3
USD_BILLION_TO_TWD_MILLION = USD_TO_TWD_RATE * 1_000.0

RELATIONSHIP_BY_ROLE = [
    ("晶圓", "foundry_competitor"),
    ("foundry", "foundry_competitor"),
    ("品牌", "brand_competitor"),
    ("brand", "brand_competitor"),
    ("晶片", "chip_competitor"),
    ("chip", "chip_competitor"),
    ("ODM", "odm_peer"),
    ("伺服器", "server_peer"),
    ("server", "server_peer"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_alias(text: str) -> str:
    text = re.sub(r"\[\[|\]\]", "", str(text or "")).strip()
    text = re.sub(r"\s*\([^)]*\)\s*", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def add_alias(aliases: dict[str, str], name: str, stock: str) -> None:
    name = str(name or "").strip()
    stock = str(stock or "").strip()
    if name and stock:
        aliases.setdefault(normalize_alias(name), stock)


def build_alias_map(json_dir: Path, biztrends_root: Path) -> dict[str, str]:
    cache_key = (str(json_dir.resolve()), str(biztrends_root.resolve()))
    if cache_key in _ALIAS_CACHE:
        return _ALIAS_CACHE[cache_key]
    aliases: dict[str, str] = {}
    for json_path in sorted(json_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ticker = str(data.get("ticker", "")).strip()
        company = str(data.get("company_name", "")).strip()
        add_alias(aliases, ticker, ticker)
        add_alias(aliases, company, ticker)
        add_alias(aliases, company.replace("-KY", ""), ticker)

    performance_path = biztrends_root / "data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv"
    revenue_path = biztrends_root / "data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv"
    for row in read_csv(performance_path) + read_csv(revenue_path):
        add_alias(aliases, row.get("company_name", ""), row.get("stock_code", ""))

    for symbol, name in CCA.US_NAME_OVERRIDES.items():
        add_alias(aliases, symbol, symbol)
        add_alias(aliases, name, symbol)
        if "/" in name:
            for part in name.split("/"):
                add_alias(aliases, part.strip(), symbol)
    for name, stock in KNOWN_ALIASES.items():
        add_alias(aliases, name, stock)
    _ALIAS_CACHE[cache_key] = aliases
    return aliases


def configure_runner_paths(biztrends_root: Path) -> None:
    CCA.ROOT = biztrends_root
    CCA.OUTPUT_DIR = biztrends_root / "output"
    CCA.TAIWAN_PERFORMANCE = biztrends_root / "data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv"
    CCA.TAIWAN_MONTHLY_REVENUE = biztrends_root / "data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv"
    CCA.TAIWAN_SUPPLY_F000 = biztrends_root / "data/ic.tpex.org.tw/raw_SupplyChain_F000.csv"
    CCA.US_INCOME = biztrends_root / "data/ConceptStocks/raw_conceptstock_company_income.csv"
    CCA.COMPANY_CYCLE_MAJOR_WEIGHTS = biztrends_root / "output/company_cycle_major_weights.csv"
    CCA.COMPANY_SEGMENT_WEIGHTS = biztrends_root / "data/company_segment_weights.csv"
    CCA.CYCLE_MAPPING = biztrends_root / "data/cycle_mapping.csv"


def relationship_type(role: str) -> str:
    role_text = str(role or "")
    role_lower = role_text.casefold()
    for needle, rel_type in RELATIONSHIP_BY_ROLE:
        if needle.casefold() in role_lower:
            return rel_type
    return "product_peer"


def resolve_competitors(data: dict[str, Any], aliases: dict[str, str]) -> list[tuple[str, str, str]]:
    resolved: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in data.get("relationships", {}).get("competitors", []) or []:
        rel_type = relationship_type(str(item.get("role", "")))
        entities = item.get("entities") or []
        if not entities:
            entities = re.findall(r"\[\[([^\]]+)\]\]", str(item.get("text", "")))
        for entity in entities:
            entity_text = str(entity).strip()
            stock = aliases.get(normalize_alias(entity_text)) or entity_text
            if not stock or stock in seen:
                continue
            resolved.append((stock, entity_text, rel_type))
            seen.add(stock)
    return resolved


def convert_my_tw_units(metric: dict[str, object]) -> dict[str, object]:
    metric = dict(metric)
    unit = metric.get("unit")
    if unit == "TWD 億":
        metric["market"] = "Taiwan"
        multiplier = 100.0
    elif unit == "USD 十億":
        metric["market"] = "US"
        multiplier = USD_BILLION_TO_TWD_MILLION
    else:
        metric["market"] = CCA.market_label_for_unit(unit)
        return metric

    metric["unit"] = "百萬台幣"
    for key in ["revenue", "profit"]:
        value = CCA.to_float(metric.get(key))
        if value is not None:
            metric[key] = value * multiplier
    return metric


def market_sort_key(market: object) -> int:
    order = {"Taiwan": 0, "US": 1, "Other": 2}
    return order.get(str(market), 9)


def row_sort_key(item: tuple[tuple[object, object, object, object], dict[object, dict[str, object]]]) -> tuple[object, int, int, str]:
    stock, _company, rel_type, market = item[0]
    return (rel_type != "target", CCA.relationship_sort_key(rel_type), market_sort_key(market), str(stock))


def my_tw_markdown_period_label(row: dict[str, object]) -> str:
    label = CCA.markdown_period_label(row)
    return re.sub(r"^(\d{4})-Q([1-4])$", r"\1Q\2", label)


def market_for_peer_stock(stock: object) -> str:
    text = str(stock or "")
    if text.isdigit():
        return "Taiwan"
    if text.endswith(".KS"):
        return "Korea"
    if text.endswith(".HK"):
        return "Hong Kong"
    if re.fullmatch(r"[A-Z.]+", text):
        return "US"
    return "Other"


def output_rows_for_data(data: dict[str, Any], json_dir: Path, biztrends_root: Path, years: int) -> list[dict[str, object]]:
    configure_runner_paths(biztrends_root)
    aliases = build_alias_map(json_dir, biztrends_root)
    target = str(data.get("ticker", "")).strip().upper()
    if not target:
        return []

    peers: dict[str, Any] = {
        target: CCA.Peer(target, str(data.get("company_name", "")), "target", "target", set())
    }
    for stock, entity, rel_type in resolve_competitors(data, aliases):
        peers[stock] = CCA.Peer(stock, entity, rel_type, "data/enrichment_all relationships.competitors", set())
    if len(peers) <= 1:
        return []

    tw_stocks = {stock for stock in peers if stock.isdigit()}
    us_symbols = {stock for stock in peers if not stock.isdigit()}
    metrics: dict[str, list[dict[str, object]]] = {}
    taiwan_metrics = CCA.taiwan_quarterly_metrics(tw_stocks, years)
    taiwan_metrics = CCA.taiwan_monthly_revenue_metrics(tw_stocks, years, taiwan_metrics)
    metrics.update(taiwan_metrics)
    metrics.update(CCA.us_quarterly_metrics(us_symbols, years))

    rows: list[dict[str, object]] = []
    for peer_stock, peer in sorted(peers.items(), key=lambda item: (item[1].relationship_type != "target", CCA.relationship_sort_key(item[1].relationship_type), item[0])):
        peer_metrics = metrics.get(peer_stock, [])
        if not peer_metrics:
            rows.append({
                "stock": peer_stock,
                "company": peer.company,
                "relationship_type": peer.relationship_type,
                "period": "",
                "market": market_for_peer_stock(peer_stock),
                "unit": "百萬台幣",
                "revenue": "",
                "revenue_yoy_pct": "",
                "profit": "",
                "profit_yoy_pct": "",
                "gross_margin_pct": "",
                "is_monthly_revenue_only": False,
            })
            continue
        for metric_raw in peer_metrics:
            metric = convert_my_tw_units(metric_raw)
            rows.append({
                "stock": peer_stock,
                "company": metric.get("company") or peer.company,
                "relationship_type": peer.relationship_type,
                "period": metric.get("period"),
                "market": metric.get("market") or CCA.market_label_for_unit(metric.get("unit")),
                "unit": metric.get("unit"),
                "revenue": CCA.number(metric.get("revenue")),
                "revenue_yoy_pct": CCA.pct(metric.get("revenue_yoy_pct")),
                "profit": CCA.number(metric.get("profit")),
                "profit_yoy_pct": CCA.pct(metric.get("profit_yoy_pct")),
                "gross_margin_pct": CCA.gm_pct(metric.get("gm")),
                "is_monthly_revenue_only": bool(metric.get("is_monthly_revenue_only")),
            })
    return rows


def render_pivot(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    metrics = [
        ("revenue", "Revenue"),
        ("revenue_yoy_pct", "Rev YoY"),
        ("profit", "Profit"),
        ("profit_yoy_pct", "Profit YoY"),
        ("gross_margin_pct", "GM"),
    ]
    unit = "百萬台幣"
    periods = sorted({label for row in rows if (label := my_tw_markdown_period_label(row))}, key=CCA.period_sort_key, reverse=True)
    companies: dict[tuple[object, object, object, object], dict[object, dict[str, object]]] = defaultdict(dict)
    has_us = False
    for row in rows:
        market = row.get("market") or CCA.market_label_for_unit(row.get("unit"))
        if market == "US":
            has_us = True
        period_label = my_tw_markdown_period_label(row)
        company_key = (row.get("stock"), row.get("company"), row.get("relationship_type"), market)
        companies.setdefault(company_key, {})
        if period_label:
            companies[company_key][period_label] = row

    out = StringIO()
    out.write("### 競爭同業 Revenue/Profit/GM\n\n")
    out.write(f"Unit: `{unit}`\n")
    if has_us:
        out.write(f"FX: `1 USD = {USD_TO_TWD_RATE:g} TWD`\n")
    out.write("\n<table>\n<thead>\n<tr>")
    out.write(CCA.html_cell("Stock", header=True))
    out.write(CCA.html_cell("Company", header=True))
    out.write(CCA.html_cell("Market", header=True))
    out.write(CCA.html_cell("Relationship", header=True))
    for period in periods:
        out.write(CCA.html_cell(period, header=True, align="center", colspan=len(metrics)))
    out.write("</tr>\n<tr>")
    out.write(CCA.html_cell("", header=True))
    out.write(CCA.html_cell("", header=True))
    out.write(CCA.html_cell("", header=True))
    out.write(CCA.html_cell("", header=True))
    for _period in periods:
        for _key, label in metrics:
            out.write(CCA.html_cell(label, header=True, align="right"))
    out.write("</tr>\n</thead>\n<tbody>\n")
    for (stock, company, rel_type, market), values_by_period in sorted(companies.items(), key=row_sort_key):
        out.write("<tr>")
        out.write(CCA.html_cell(stock))
        out.write(CCA.html_cell(company))
        out.write(CCA.html_cell(market))
        out.write(CCA.html_cell(CCA.RELATIONSHIP_LABEL_ZH.get(str(rel_type), rel_type)))
        for period in periods:
            row = values_by_period.get(period, {})
            for key, _label in metrics:
                out.write(CCA.html_cell(row.get(key, ""), align="right"))
        out.write("</tr>\n")
    out.write("</tbody>\n</table>\n")
    return out.getvalue().strip()


def render_competitor_financial_section(data: dict[str, Any], json_dir: Path, biztrends_root: Path, years: int = 3) -> str:
    rows = output_rows_for_data(data, json_dir, biztrends_root, years)
    return render_pivot(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--biztrends-root", default="../biztrends.TW")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--years", type=int, default=3)
    args = parser.parse_args()

    json_dir = Path(args.json_dir).resolve()
    data = json.loads((json_dir / f"{args.ticker}.json").read_text(encoding="utf-8"))
    section = render_competitor_financial_section(data, json_dir, Path(args.biztrends_root).resolve(), args.years)
    if section:
        print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
