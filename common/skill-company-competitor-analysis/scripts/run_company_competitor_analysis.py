#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = ROOT / "output"
TAIWAN_PERFORMANCE = ROOT / "data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv"
TAIWAN_MONTHLY_REVENUE = ROOT / "data/Python-Actions.GoodInfo.Analyzer/raw_revenue.csv"
TAIWAN_SUPPLY_F000 = ROOT / "data/ic.tpex.org.tw/raw_SupplyChain_F000.csv"
US_INCOME = ROOT / "data/ConceptStocks/raw_conceptstock_company_income.csv"
INVESTORCONFERENCE_IR_INCOME = ROOT / "data/InvestorConference/raw_ir_quarterly_financials.csv"
INVESTORCONFERENCE_DATA = ROOT.parent / "InvestorConference/data"
INVESTOR_EVENTS = ROOT / "data/InvestorEvents/raw_event_upcoming_earnings.csv"
COMPANY_CYCLE_MAJOR_WEIGHTS = OUTPUT_DIR / "company_cycle_major_weights.csv"
COMPANY_SEGMENT_WEIGHTS = ROOT / "data/company_segment_weights.csv"
CYCLE_MAPPING = ROOT / "data/cycle_mapping.csv"

AI_RELATED_CYCLES = [
    "AI_Server_Rack",
    "AI_Foundry_Packaging",
    "AI_Network_Infra",
    "AI_Accelerator",
    "AI_CPU_Orchestration",
    "AI_Memory_HBM",
    "Cloud_AI_Compute",
]

PC_BRAND_COMPETITORS = {"2357": {"2353", "2376", "2377", "DELL", "0992.HK"}}
IPC_BRAND_COMPETITORS = {
    "2395": {"2397", "2405", "3022", "3088", "3416", "3479", "3515", "6166", "6245", "6414", "6579", "8050", "8234"},
}
CHIP_COMPETITORS = {
    "2379": {"2454", "6526", "AVGO", "QCOM"},
}
FOUNDRY_COMPETITORS = {
    "2330": {"2303", "GFS", "INTC", "0981.HK", "005930.KS"},
}
PC_ODM_PEERS = {
    "2357": {"2317", "2324", "2356", "2382", "3231", "4938"},
    "2382": {"2317", "2324", "2356", "3231", "4938"},
}
SERVER_PEERS = {
    "2357": {"2317", "2356", "2382", "3231", "6669", "DELL", "HPE"},
    "2382": {"2317", "2356", "3231", "6669"},
}
SUPPLIER_OR_COMPONENT = {"2301", "2330", "2308", "2344", "2408", "2451", "8299", "2360", "2474", "3022", "6231"}
US_NAME_OVERRIDES = {
    "DELL": "Dell Technologies Inc.",
    "HPQ": "HP Inc.",
    "0992.HK": "Lenovo Group Limited",
    "LNVGY": "Lenovo Group ADR",
    "HPE": "Hewlett Packard Enterprise",
    "AVGO": "Broadcom Inc.",
    "QCOM": "Qualcomm Inc.",
    "GFS": "GlobalFoundries Inc.",
    "INTC": "Intel Corporation",
    "0981.HK": "SMIC / Semiconductor Manufacturing International Corporation",
    "005930.KS": "Samsung Electronics Co., Ltd.",
}

RELATIONSHIP_LABEL_ZH = {
    "target": "目標公司",
    "brand_competitor": "品牌競爭者",
    "chip_competitor": "晶片競爭者",
    "foundry_competitor": "晶圓代工競爭者",
    "odm_peer": "ODM 同業",
    "server_peer": "伺服器同業",
    "product_peer": "產品同業",
    "supplier_or_component": "供應商/零組件",
}

@dataclass
class Peer:
    stock: str
    company: str
    relationship_type: str
    peer_basis: str
    shared_categories: set[str]

def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "N/A", "nan", "None"}:
        return None
    try:
        value_float = float(text)
    except ValueError:
        return None
    if math.isnan(value_float):
        return None
    return value_float

def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:+.1f}%"

def gm_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%"

def number(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) >= 100:
        return f"{value:,.1f}"
    return f"{value:.2f}".rstrip("0").rstrip(".")

def period_key_taiwan(period: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})Q([1-4])", period.strip())
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2)))

def month_to_taiwan_quarter(month: str) -> tuple[tuple[int, int], str] | None:
    match = re.fullmatch(r"(\d{4})/(\d{2})", month.strip())
    if not match:
        return None
    year = int(match.group(1))
    month_num = int(match.group(2))
    quarter = (month_num - 1) // 3 + 1
    return (year, quarter), f"{year}Q{quarter}"

def period_key_us(fiscal_year: str, period: str) -> tuple[int, int]:
    match = re.fullmatch(r"Q([1-4])", period.strip())
    if not match or not fiscal_year.isdigit():
        return (0, 0)
    return (int(fiscal_year), int(match.group(1)))

def period_key_from_end_date(end_date: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})-\d{2}", str(end_date or "").strip())
    if not match:
        return (0, 0)
    year = int(match.group(1))
    month = int(match.group(2))
    quarter = (month - 1) // 3 + 1
    return (year, quarter)

def segment_period_key(period: str) -> tuple[int, int]:
    text = period.strip()
    match = re.fullmatch(r"(\d{4})-Q([1-4])", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    match = re.fullmatch(r"(\d{4})-FY", text)
    if match:
        return (int(match.group(1)), 5)
    match = re.fullmatch(r"(\d{4})Q([1-4])", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def load_ai_cycle_weights(stocks: set[str]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for row in read_csv(COMPANY_CYCLE_MAJOR_WEIGHTS):
        stock = row.get("代號", "").strip()
        if stock not in stocks:
            continue
        current_period = row.get("期間", "").strip()
        existing_period = str(latest.get(stock, {}).get("source_period") or "")
        if stock in latest and segment_period_key(current_period) <= segment_period_key(existing_period):
            continue
        cycle_weights = {cycle: to_float(row.get(cycle)) or 0.0 for cycle in AI_RELATED_CYCLES}
        latest[stock] = {
            "company": row.get("公司", "").strip(),
            "source_period": current_period,
            "confidence": row.get("信心", "").strip(),
            "source": row.get("來源", "").strip(),
            "cycle_weights": cycle_weights,
            "total_ai_weight": sum(cycle_weights.values()),
        }

    cycle_map = {
        (row.get("symbol", "").strip(), row.get("segment_name", "").strip()): (
            row.get("canonical_cycle", "").strip(),
            row.get("demand_cycle", "").strip(),
        )
        for row in read_csv(CYCLE_MAPPING)
        if row.get("symbol", "").strip() and row.get("segment_name", "").strip()
    }
    for row in read_csv(COMPANY_SEGMENT_WEIGHTS):
        stock = row.get("stock_code", "").strip()
        if stock not in stocks or stock.isdigit() or row.get("status", "").strip() != "active":
            continue
        current_period = row.get("source_period", "").strip()
        existing_period = str(latest.get(stock, {}).get("source_period") or "")
        if stock in latest and segment_period_key(current_period) < segment_period_key(existing_period):
            continue
        if stock not in latest or segment_period_key(current_period) > segment_period_key(existing_period):
            latest[stock] = {
                "company": row.get("company_name", "").strip(),
                "source_period": current_period,
                "confidence": row.get("confidence", "").strip(),
                "source": "data/company_segment_weights.csv + data/cycle_mapping.csv",
                "cycle_weights": {cycle: 0.0 for cycle in AI_RELATED_CYCLES},
                "total_ai_weight": 0.0,
            }
        weight = to_float(row.get("weight_pct")) or 0.0
        canonical_cycle, demand_cycle = cycle_map.get((stock, row.get("segment_name", "").strip()), ("", ""))
        target_cycles = []
        if canonical_cycle in AI_RELATED_CYCLES:
            target_cycles.append(canonical_cycle)
        if demand_cycle in AI_RELATED_CYCLES and demand_cycle not in target_cycles:
            target_cycles.append(demand_cycle)
        cycle_weights = latest[stock]["cycle_weights"]
        if isinstance(cycle_weights, dict):
            for cycle in target_cycles:
                cycle_weights[cycle] = float(cycle_weights.get(cycle) or 0.0) + weight
            latest[stock]["total_ai_weight"] = sum(float(cycle_weights.get(cycle) or 0.0) for cycle in AI_RELATED_CYCLES)
    return latest


def relationship_sort_key(relationship: object) -> int:
    order = {"target": 0, "brand_competitor": 1, "chip_competitor": 2, "foundry_competitor": 3, "server_peer": 4, "odm_peer": 5, "product_peer": 6, "supplier_or_component": 7}
    return order.get(str(relationship), 9)

def yoy(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return (current / prior - 1.0) * 100.0

def load_investor_event_dates(stocks: set[str]) -> dict[tuple[str, str], dict[str, str]]:
    events: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    if not stocks:
        return events
    for row in read_csv(INVESTOR_EVENTS):
        name = row.get("事件名稱", "").strip()
        match = re.search(r"\(([^)]+)\).*?(?:FY)?(\d{4})\s*Q([1-4])", name)
        if not match:
            continue
        stock = match.group(1).strip().upper()
        period = f"{match.group(2)}Q{match.group(3)}"
        if stock not in stocks and stock.endswith("O") and stock[:-1] in stocks:
            stock = stock[:-1]
        if stock not in stocks:
            continue
        date = row.get("開始日期", "").strip()
        if not date:
            continue
        category = row.get("類別", "").strip()
        event_name = row.get("事件名稱", "").strip()
        key = (stock, period)
        if category == "財報公告" or "財報" in event_name:
            events[key]["financial_report_event_date"] = min(
                [value for value in [events[key].get("financial_report_event_date"), date] if value]
            )
        if category == "法說會" or "法說" in event_name:
            events[key]["ir_event_date"] = min(
                [value for value in [events[key].get("ir_event_date"), date] if value]
            )
    return events


def event_date_status(value: object, today: date | None = None) -> str:
    if not value:
        return ""
    today = today or date.today()
    try:
        if date.fromisoformat(str(value)) < today:
            return "Ready"
    except ValueError:
        return ""
    return ""


def format_event_date(financial_report_date: object, ir_date: object) -> str:
    parts = []
    for label, value in [("財報", financial_report_date), ("法說", ir_date)]:
        if not value:
            continue
        status = event_date_status(value)
        suffix = f" ({status})" if status else ""
        parts.append(f"{label}: {value}{suffix}")
    return "<br>".join(parts)


def attach_investor_event_dates(metrics: dict[str, list[dict[str, object]]], stocks: set[str]) -> None:
    event_dates = load_investor_event_dates({stock.upper() for stock in stocks})
    display_periods = {str(row.get("period") or "") for rows in metrics.values() for row in rows}
    for stock, rows in list(metrics.items()):
        rows_by_period = {str(row.get("period") or ""): row for row in rows}
        for (event_stock, period), events in event_dates.items():
            if event_stock != stock.upper():
                continue
            target_row = rows_by_period.get(period)
            if target_row is not None and not target_row.get("is_monthly_revenue_only"):
                row = target_row
            elif target_row is not None and target_row.get("is_monthly_revenue_only"):
                row = {
                    "period": period,
                    "unit": target_row.get("unit"),
                    "revenue": None,
                    "revenue_yoy_pct": None,
                    "profit": None,
                    "profit_yoy_pct": None,
                    "gm": None,
                    "company": target_row.get("company"),
                    "is_monthly_revenue_only": False,
                }
                rows.append(row)
                rows_by_period[period] = row
            elif period in display_periods:
                row = {
                    "period": period,
                    "unit": rows[0].get("unit") if rows else None,
                    "revenue": None,
                    "revenue_yoy_pct": None,
                    "profit": None,
                    "profit_yoy_pct": None,
                    "gm": None,
                    "company": rows[0].get("company") if rows else None,
                    "is_monthly_revenue_only": False,
                }
                rows.append(row)
                rows_by_period[period] = row
            else:
                continue
            row["financial_report_event_date"] = events.get("financial_report_event_date", "")
            row["ir_event_date"] = events.get("ir_event_date", "")
            row["event_date"] = format_event_date(row["financial_report_event_date"], row["ir_event_date"])

        for row in rows:
            row.setdefault("financial_report_event_date", "")
            row.setdefault("ir_event_date", "")
            row.setdefault("event_date", "")


def load_taiwan_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for row in read_csv(TAIWAN_SUPPLY_F000):
        stock = row.get("代號", "").strip()
        name = row.get("名稱", "").strip()
        if stock and name:
            names[stock] = name
    return names

def classify_peer(target: str, stock: str, shared_categories: set[str]) -> str:
    if stock in PC_BRAND_COMPETITORS.get(target, set()):
        return "brand_competitor"
    if stock in CHIP_COMPETITORS.get(target, set()):
        return "chip_competitor"
    if stock in FOUNDRY_COMPETITORS.get(target, set()):
        return "foundry_competitor"
    if stock in IPC_BRAND_COMPETITORS.get(target, set()) and "工業電腦" in shared_categories:
        return "brand_competitor"
    if stock in SERVER_PEERS.get(target, set()) and "伺服器" in shared_categories:
        return "server_peer"
    if stock in PC_ODM_PEERS.get(target, set()):
        return "odm_peer"
    if stock in SUPPLIER_OR_COMPONENT:
        return "supplier_or_component"
    return "product_peer"

def build_supply_peers(target: str) -> dict[str, Peer]:
    rows = read_csv(TAIWAN_SUPPLY_F000)
    names = load_taiwan_names()
    target_cats = {
        row.get("子分類", "").strip()
        for row in rows
        if row.get("代號", "").strip() == target and row.get("位置", "").strip() == "下游"
    }
    if not target_cats:
        target_cats = {row.get("子分類", "").strip() for row in rows if row.get("代號", "").strip() == target}

    peers_by_stock: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        stock = row.get("代號", "").strip()
        category = row.get("子分類", "").strip()
        position = row.get("位置", "").strip()
        if not stock or stock == target or not category:
            continue
        if category in target_cats and position == "下游":
            peers_by_stock[stock].add(category)

    peers: dict[str, Peer] = {
        target: Peer(target, names.get(target, ""), "target", "target", target_cats)
    }
    for stock, cats in peers_by_stock.items():
        relationship = classify_peer(target, stock, cats)
        peers[stock] = Peer(stock, names.get(stock, ""), relationship, "F000 downstream shared categories", cats)

    for stock in PC_BRAND_COMPETITORS.get(target, set()):
        peers[stock] = Peer(
            stock,
            names.get(stock, US_NAME_OVERRIDES.get(stock, "")),
            "brand_competitor",
            "known PC brand competitor rule",
            peers.get(stock, Peer(stock, "", "", "", set())).shared_categories,
        )
    for stock in IPC_BRAND_COMPETITORS.get(target, set()):
        peers[stock] = Peer(
            stock,
            names.get(stock, ""),
            "brand_competitor",
            "known IPC brand competitor rule",
            peers.get(stock, Peer(stock, "", "", "", {"工業電腦"})).shared_categories or {"工業電腦"},
        )
    for stock in CHIP_COMPETITORS.get(target, set()):
        existing = peers.get(stock)
        peers[stock] = Peer(
            stock,
            names.get(stock, US_NAME_OVERRIDES.get(stock, existing.company if existing else "")),
            "chip_competitor",
            "known IC design / connectivity chip competitor rule",
            existing.shared_categories if existing else {"IC設計", "網通晶片"},
        )
    for stock in FOUNDRY_COMPETITORS.get(target, set()):
        existing = peers.get(stock)
        peers[stock] = Peer(
            stock,
            names.get(stock, US_NAME_OVERRIDES.get(stock, existing.company if existing else "")),
            "foundry_competitor",
            "known semiconductor foundry competitor rule",
            existing.shared_categories if existing else {"IC/晶圓製造", "晶圓代工"},
        )
    for stock in PC_ODM_PEERS.get(target, set()):
        existing = peers.get(stock)
        if existing and existing.relationship_type in {"brand_competitor", "server_peer"}:
            continue
        peers[stock] = Peer(
            stock,
            names.get(stock, existing.company if existing else ""),
            "odm_peer",
            "known ODM peer rule",
            existing.shared_categories if existing else set(),
        )
    for stock in SERVER_PEERS.get(target, set()):
        existing = peers.get(stock)
        if existing and existing.relationship_type == "brand_competitor":
            peers[stock] = Peer(
                stock,
                existing.company,
                existing.relationship_type,
                existing.peer_basis,
                existing.shared_categories | {"伺服器"},
            )
            continue
        peers[stock] = Peer(
            stock,
            names.get(stock, US_NAME_OVERRIDES.get(stock, existing.company if existing else "")),
            "server_peer",
            "known server peer rule",
            (existing.shared_categories if existing else set()) | {"伺服器"},
        )
    return peers

def select_recent_periods(periods: list[tuple[int, int]], years: int) -> set[tuple[int, int]]:
    return set(sorted(set(periods))[-years * 4 :])

def parse_official_taiwan_earnings_release(path: Path) -> dict[str, object] | None:
    match = re.fullmatch(r"(\d+)_([0-9]{4})_q([1-4])_earnings_release\.md", path.name)
    if not match:
        return None
    stock, year_text, quarter_text = match.groups()
    text = path.read_text(encoding="utf-8", errors="ignore")
    revenue_match = re.search(r"consolidated revenue of\s*NT\$([0-9,.]+)\s*billion", text, re.IGNORECASE)
    gm_match = re.search(r"Gross margin for the quarter was\s*([0-9.]+)%", text, re.IGNORECASE)
    op_margin_match = re.search(r"operating margin was\s*([0-9.]+)%", text, re.IGNORECASE)
    if not revenue_match:
        return None
    revenue = float(revenue_match.group(1).replace(",", "")) * 10.0
    gm = float(gm_match.group(1)) if gm_match else None
    op_margin = float(op_margin_match.group(1)) if op_margin_match else None
    profit = revenue * op_margin / 100.0 if op_margin is not None else None
    return {
        "period": f"{year_text}Q{quarter_text}",
        "unit": "TWD 億",
        "revenue": revenue,
        "profit": profit,
        "gm": gm,
        "company": "",
        "source_priority": 0,
    }


def load_official_taiwan_earnings_metrics(stocks: set[str]) -> dict[tuple[str, tuple[int, int]], dict[str, object]]:
    out: dict[tuple[str, tuple[int, int]], dict[str, object]] = {}
    for stock in stocks:
        company_dir = INVESTORCONFERENCE_DATA / stock
        if not company_dir.exists():
            continue
        for path in company_dir.glob(f"{stock}_*_q*_earnings_release.md"):
            row = parse_official_taiwan_earnings_release(path)
            if row is None:
                continue
            key = period_key_taiwan(str(row.get("period") or ""))
            if key == (0, 0):
                continue
            row["source_file"] = str(path)
            out[(stock, key)] = row
    return out


def taiwan_quarterly_metrics(stocks: set[str], years: int) -> dict[str, list[dict[str, object]]]:
    by_stock_period: dict[tuple[str, tuple[int, int]], dict[str, object]] = {}
    for row in read_csv(TAIWAN_PERFORMANCE):
        stock = row.get("stock_code", "").strip()
        period = row.get("季度", "").strip()
        key = period_key_taiwan(period)
        revenue = to_float(row.get("獲利金額_億_營業_收入"))
        if stock not in stocks or key == (0, 0) or revenue is None:
            continue
        gross_profit = to_float(row.get("獲利金額_億_營業_毛利"))
        profit = to_float(row.get("獲利金額_億_營業_利益"))
        gm = to_float(row.get("獲利率_pct_營業_毛利"))
        if gm is None and gross_profit is not None and revenue:
            gm = gross_profit / revenue * 100.0
        by_stock_period[(stock, key)] = {
            "period": period,
            "unit": "TWD 億",
            "revenue": revenue,
            "profit": profit,
            "gm": gm,
            "company": row.get("company_name", "").strip(),
        }

    for (stock, key), row in load_official_taiwan_earnings_metrics(stocks).items():
        existing = by_stock_period.get((stock, key))
        if existing is None or int(existing.get("source_priority", 9)) > int(row.get("source_priority", 9)):
            if existing and not row.get("company"):
                row["company"] = existing.get("company", "")
            by_stock_period[(stock, key)] = row

    selected_periods = select_recent_periods([key for stock, key in by_stock_period if stock in stocks], years)
    out: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (stock, key), current in sorted(by_stock_period.items(), key=lambda item: (item[0][0], item[0][1])):
        if key not in selected_periods:
            continue
        prior = by_stock_period.get((stock, (key[0] - 1, key[1])), {})
        current["revenue_yoy_pct"] = yoy(current.get("revenue"), prior.get("revenue"))
        current["profit_yoy_pct"] = yoy(current.get("profit"), prior.get("profit"))
        out[stock].append(current)
    return out


def taiwan_monthly_revenue_metrics(stocks: set[str], years: int, existing: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    by_stock_quarter: dict[tuple[str, tuple[int, int]], dict[str, object]] = {}
    monthly_sums: dict[tuple[str, tuple[int, int]], dict[str, object]] = defaultdict(lambda: {"revenue": 0.0, "months": set(), "company": ""})
    for row in read_csv(TAIWAN_MONTHLY_REVENUE):
        stock = row.get("stock_code", "").strip()
        parsed = month_to_taiwan_quarter(row.get("月別", ""))
        if stock not in stocks or parsed is None:
            continue
        key, period = parsed
        revenue = to_float(row.get("合併營業收入_營收_億"))
        if revenue is None:
            revenue = to_float(row.get("營業收入_營收_億"))
        if revenue is None:
            continue
        bucket = monthly_sums[(stock, key)]
        bucket["revenue"] = float(bucket["revenue"]) + revenue
        bucket["months"].add(row.get("月別", ""))
        bucket["company"] = row.get("company_name", "").strip()
        bucket["period"] = period

    for (stock, key), bucket in monthly_sums.items():
        prior = monthly_sums.get((stock, (key[0] - 1, key[1])), {})
        by_stock_quarter[(stock, key)] = {
            "period": bucket.get("period"),
            "unit": "TWD 億",
            "revenue": bucket.get("revenue"),
            "profit": None,
            "gm": None,
            "company": bucket.get("company"),
            "revenue_yoy_pct": yoy(bucket.get("revenue"), prior.get("revenue")),
            "profit_yoy_pct": None,
            "is_monthly_revenue_only": True,
        }

    merged: dict[str, dict[tuple[int, int], dict[str, object]]] = defaultdict(dict)
    for stock, rows in existing.items():
        for row in rows:
            key = period_key_taiwan(str(row.get("period") or ""))
            if key != (0, 0):
                merged[stock][key] = row

    for (stock, key), row in by_stock_quarter.items():
        if key not in merged[stock]:
            merged[stock][key] = row

    trimmed: dict[str, list[dict[str, object]]] = defaultdict(list)
    for stock, rows_by_period in merged.items():
        for _key, row in sorted(rows_by_period.items())[-years * 4:]:
            trimmed[stock].append(row)
    return trimmed

def us_quarterly_metrics(symbols: set[str], years: int) -> dict[str, list[dict[str, object]]]:
    by_stock_period: dict[tuple[str, tuple[int, int]], dict[str, object]] = {}
    source_priority = {
        "InvestorConferenceOfficialIR": 0,
        "SEC": 1,
        "YahooFinance": 2,
        "AlphaVantage": 3,
        "FMP": 4,
    }

    for row in read_csv(INVESTORCONFERENCE_IR_INCOME):
        symbol = row.get("symbol", "").strip()
        key = period_key_from_end_date(row.get("end_date", ""))
        revenue = to_float(row.get("total_revenue"))
        if symbol not in symbols or key == (0, 0) or revenue is None:
            continue
        gross_profit = to_float(row.get("gross_profit"))
        profit = to_float(row.get("operating_income"))
        gm = to_float(row.get("gross_margin"))
        if gm is None and gross_profit is not None and revenue:
            gm = gross_profit / revenue * 100.0
        elif gm is not None and abs(gm) <= 1.5:
            gm *= 100.0
        currency = row.get("currency", "").strip() or "USD"
        scale = 1_000_000_000.0 if currency in {"USD", "HKD", "KRW"} else 1.0
        by_stock_period[(symbol, key)] = {
            "period": f"{key[0]}Q{key[1]}",
            "unit": f"{currency} 十億" if scale != 1.0 else currency,
            "revenue": revenue / scale,
            "profit": profit / scale if profit is not None else None,
            "gm": gm,
            "company": row.get("company_name", "").strip() or US_NAME_OVERRIDES.get(symbol, ""),
            "revenue_yoy_pct": to_float(row.get("revenue_yoy_pct")),
            "source_priority": source_priority["InvestorConferenceOfficialIR"],
        }

    for row in read_csv(US_INCOME):
        symbol = row.get("symbol", "").strip()
        period = row.get("period", "").strip()
        if period == "FY":
            continue
        fiscal_year = row.get("fiscal_year", "").strip()
        key = period_key_from_end_date(row.get("end_date", ""))
        if key == (0, 0):
            key = period_key_us(fiscal_year, period)
        revenue = to_float(row.get("total_revenue"))
        if symbol not in symbols or key == (0, 0) or revenue is None:
            continue
        source = row.get("source", "").strip()
        existing = by_stock_period.get((symbol, key))
        if existing and source_priority.get(source, 9) >= int(existing.get("source_priority", 9)):
            continue
        profit = to_float(row.get("operating_income"))
        gm = to_float(row.get("gross_margin"))
        if gm is not None and abs(gm) <= 1.5:
            gm *= 100.0
        currency = row.get("currency", "").strip() or "USD"
        by_stock_period[(symbol, key)] = {
            "period": f"{key[0]}Q{key[1]}",
            "unit": f"{currency} 十億",
            "revenue": revenue / 1_000_000_000.0,
            "profit": profit / 1_000_000_000.0 if profit is not None else None,
            "gm": gm,
            "company": row.get("company_name", "").strip() or US_NAME_OVERRIDES.get(symbol, ""),
            "revenue_yoy_pct": to_float(row.get("revenue_yoy_pct")),
            "source_priority": source_priority.get(source, 9),
        }

    selected_periods = select_recent_periods([key for stock, key in by_stock_period if stock in symbols], years)
    out: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (symbol, key), current in sorted(by_stock_period.items(), key=lambda item: (item[0][0], item[0][1])):
        if key not in selected_periods:
            continue
        prior = by_stock_period.get((symbol, (key[0] - 1, key[1])), {})
        if current.get("revenue_yoy_pct") is None:
            current["revenue_yoy_pct"] = yoy(current.get("revenue"), prior.get("revenue"))
        current["profit_yoy_pct"] = yoy(current.get("profit"), prior.get("profit"))
        out[symbol].append(current)
    return out

def write_outputs(stock: str, peers: dict[str, Peer], metrics: dict[str, list[dict[str, object]]], relationships: set[str]) -> tuple[Path, Path, int]:
    out_dir = OUTPUT_DIR / "focus" / stock
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"company_competitor_analysis_{stock}.csv"
    md_path = out_dir / f"company_competitor_analysis_{stock}.md"
    fields = ["stock", "company", "relationship_type", "peer_basis", "shared_categories", "period", "financial_report_event_date", "ir_event_date", "unit", "revenue", "revenue_yoy_pct", "profit", "profit_yoy_pct", "gross_margin_pct"]
    output_rows: list[dict[str, object]] = []
    for peer_stock, peer in sorted(peers.items(), key=lambda item: (item[1].relationship_type != "target", item[1].relationship_type, item[0])):
        if peer.relationship_type != "target" and relationships and peer.relationship_type not in relationships:
            continue
        for metric in metrics.get(peer_stock, []):
            output_rows.append({
                "stock": peer_stock,
                "company": metric.get("company") or peer.company,
                "relationship_type": peer.relationship_type,
                "peer_basis": peer.peer_basis,
                "shared_categories": ";".join(sorted(peer.shared_categories)),
                "period": metric.get("period"),
                "financial_report_event_date": metric.get("financial_report_event_date", ""),
                "ir_event_date": metric.get("ir_event_date", ""),
                "event_date": metric.get("event_date", ""),
                "unit": metric.get("unit"),
                "revenue": number(metric.get("revenue")),
                "revenue_yoy_pct": pct(metric.get("revenue_yoy_pct")),
                "profit": number(metric.get("profit")),
                "profit_yoy_pct": pct(metric.get("profit_yoy_pct")),
                "gross_margin_pct": gm_pct(metric.get("gm")),
                "is_monthly_revenue_only": bool(metric.get("is_monthly_revenue_only")),
            })
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(f"# Company Competitor Analysis: {stock}\n\n")
        f.write("CSV remains long-format for machine processing. The tables below are pivoted with Period as the major column. Taiwan quarters sourced only from monthly revenue show Revenue and Rev YoY while Profit, Profit YoY, and GM remain blank.\n\n")
        write_pivot_markdown(f, output_rows)
        write_ai_cycle_weights_markdown(f, output_rows, load_ai_cycle_weights({str(row.get("stock") or "") for row in output_rows}))
    return csv_path, md_path, len(output_rows)


def period_sort_key(period: object) -> tuple[int, int, str]:
    text = str(period or "")
    match = re.fullmatch(r"(\d{4})Q([1-4])(?:（月營收）)?", text)
    if match:
        return (int(match.group(1)), int(match.group(2)), text)
    match = re.fullmatch(r"(\d{4})-Q([1-4])", text)
    if match:
        return (int(match.group(1)), int(match.group(2)), text)
    return (0, 0, text)


def markdown_period_label(row: dict[str, object]) -> str:
    period = str(row.get("period") or "")
    if row.get("is_monthly_revenue_only"):
        return f"{period}（月營收）"
    return period


def html_cell(value: object, *, align: str = "left", header: bool = False, colspan: int = 1) -> str:
    tag = "th" if header else "td"
    attrs = []
    if colspan != 1:
        attrs.append(f'colspan="{colspan}"')
    if align:
        attrs.append(f'style="text-align: {align};"')
    attr_text = " " + " ".join(attrs) if attrs else ""
    return f"<{tag}{attr_text}>{value or ''}</{tag}>"


def market_label_for_stock(stock: object) -> str:
    return "Taiwan" if str(stock or "").isdigit() else "US"


def market_label_for_unit(unit: object) -> str:
    text = str(unit or "")
    if text.startswith("TWD"):
        return "Taiwan"
    if text.startswith("USD"):
        return "US"
    if text.startswith("HKD"):
        return "Hong Kong"
    if text.startswith("KRW"):
        return "Korea"
    return text or "Other"


def write_ai_cycle_weights_markdown(f, output_rows: list[dict[str, object]], ai_weights: dict[str, dict[str, object]]) -> None:
    companies_by_market: dict[str, dict[tuple[object, object, object], None]] = defaultdict(dict)
    for row in output_rows:
        market = market_label_for_stock(row.get("stock"))
        companies_by_market[market][(row.get("stock"), row.get("company"), row.get("relationship_type"))] = None
    if not companies_by_market:
        return

    f.write("## 2. AI Canonical Cycle Revenue Weights\n\n")
    f.write("Weights are latest available revenue segment weights rolled up to AI-related cycles from `output/company_cycle_major_weights.csv`; US peers can also use `data/company_segment_weights.csv` plus `data/cycle_mapping.csv`, including demand-cycle AI exposure where mapped. Blank cycle cells mean no active segment-weight allocation is available for that company/cycle in the current source snapshot.\n\n")
    for market in ["Taiwan", "US"]:
        companies = companies_by_market.get(market, {})
        if not companies:
            continue
        section = "2.1" if market == "Taiwan" else "2.2"
        f.write(f"### {section} {market}\n\n")
        f.write("<table>\n<thead>\n<tr>")
        for label in ["Stock", "Company", "Relationship", "Period", "Confidence", "Source", "Total AI"] + AI_RELATED_CYCLES:
            align = "right" if label == "Total AI" or label in AI_RELATED_CYCLES else "left"
            f.write(html_cell(label, header=True, align=align))
        f.write("</tr>\n</thead>\n<tbody>\n")
        for stock, company, relationship in sorted(companies, key=lambda item: (relationship_sort_key(item[2]), str(item[0]))):
            stock_text = str(stock or "")
            weight_row = ai_weights.get(stock_text, {})
            cycle_weights = weight_row.get("cycle_weights", {}) if weight_row else {}
            f.write("<tr>")
            f.write(html_cell(stock_text))
            f.write(html_cell(company))
            f.write(html_cell(RELATIONSHIP_LABEL_ZH.get(str(relationship), relationship)))
            f.write(html_cell(weight_row.get("source_period", "") if weight_row else ""))
            f.write(html_cell(weight_row.get("confidence", "") if weight_row else ""))
            f.write(html_cell(weight_row.get("source", "") if weight_row else ""))
            total = weight_row.get("total_ai_weight") if weight_row else None
            f.write(html_cell(gm_pct(total) if total not in (None, 0.0) else "", align="right"))
            for cycle in AI_RELATED_CYCLES:
                value = cycle_weights.get(cycle) if isinstance(cycle_weights, dict) else None
                f.write(html_cell(gm_pct(value) if value not in (None, 0.0) else "", align="right"))
            f.write("</tr>\n")
        f.write("</tbody>\n</table>\n\n")

def write_pivot_markdown(f, output_rows: list[dict[str, object]]) -> None:
    metrics = [
        ("revenue", "Revenue"),
        ("revenue_yoy_pct", "Rev YoY"),
        ("profit", "Profit"),
        ("profit_yoy_pct", "Profit YoY"),
        ("gross_margin_pct", "GM"),
    ]
    rows_by_unit: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in output_rows:
        rows_by_unit[str(row.get("unit") or "")].append(row)

    f.write("## 1. Revenue/Profit/GM\n\n")
    for unit, unit_rows in sorted(rows_by_unit.items(), key=lambda item: market_label_for_unit(item[0])):
        market = market_label_for_unit(unit)
        section = "1.1" if market == "Taiwan" else "1.2" if market == "US" else "1.x"
        periods = sorted({markdown_period_label(row) for row in unit_rows}, key=period_sort_key, reverse=True)
        companies: dict[tuple[object, object, object], dict[object, dict[str, object]]] = defaultdict(dict)
        for row in unit_rows:
            key = (row.get("stock"), row.get("company"), row.get("relationship_type"))
            companies[key][markdown_period_label(row)] = row

        f.write(f"### {section} {market}\n\n")
        f.write(f"Unit: `{unit}`\n\n")
        f.write("<table>\n")
        f.write("<thead>\n")
        f.write("<tr>")
        f.write(html_cell("Stock", header=True))
        f.write(html_cell("Company", header=True))
        f.write(html_cell("Relationship", header=True))
        for period in periods:
            f.write(html_cell(period, header=True, align="center", colspan=len(metrics)))
        f.write("</tr>\n")
        f.write("<tr>")
        f.write(html_cell("", header=True))
        f.write(html_cell("", header=True))
        f.write(html_cell("", header=True))
        for _period in periods:
            for _key, label in metrics:
                f.write(html_cell(label, header=True, align="right"))
        f.write("</tr>\n")
        f.write("</thead>\n<tbody>\n")
        for (stock, company, relationship), values_by_period in sorted(companies.items(), key=lambda item: (item[0][2] != "target", str(item[0][2]), str(item[0][0]))):
            f.write("<tr>")
            f.write(html_cell(stock))
            f.write(html_cell(company))
            f.write(html_cell(RELATIONSHIP_LABEL_ZH.get(str(relationship), relationship)))
            for period in periods:
                row = values_by_period.get(period, {})
                for key, _label in metrics:
                    value = row.get(key, "")
                    if key == "profit" and not value:
                        value = row.get("event_date", "")
                    f.write(html_cell(value, align="right"))
            f.write("</tr>\n")
        f.write("</tbody>\n</table>\n\n")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze competitors for a stock using supply-chain peer rules and quarterly performance data.")
    parser.add_argument("--stock", required=True, help="Target stock id or symbol, for example 2357.")
    parser.add_argument("--years", type=int, default=3, help="Number of recent years of quarterly data to include.")
    parser.add_argument("--relationship", default="brand_competitor,chip_competitor,foundry_competitor,odm_peer,server_peer", help="Comma-separated relationship types to include. Use empty string for all.")
    parser.add_argument("--include-suppliers", action="store_true", help="Include supplier_or_component rows.")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    target = args.stock.strip().upper()
    relationships = {item.strip() for item in args.relationship.split(",") if item.strip()}
    if args.include_suppliers:
        relationships.add("supplier_or_component")
    peers = build_supply_peers(target)
    tw_stocks = {stock for stock in peers if stock.isdigit()}
    us_symbols = {stock for stock in peers if not stock.isdigit()}
    metrics = {}
    taiwan_metrics = taiwan_quarterly_metrics(tw_stocks, args.years)
    taiwan_metrics = taiwan_monthly_revenue_metrics(tw_stocks, args.years, taiwan_metrics)
    metrics.update(taiwan_metrics)
    metrics.update(us_quarterly_metrics(us_symbols, args.years))
    for peer_stock in peers:
        metrics.setdefault(peer_stock, [])
    attach_investor_event_dates(metrics, set(peers))
    csv_path, md_path, row_count = write_outputs(target, peers, metrics, relationships)
    print(f"Wrote {row_count} rows")
    print(csv_path.relative_to(ROOT))
    print(md_path.relative_to(ROOT))
    if target != "2330" and peers.get("2330") and peers["2330"].relationship_type == "supplier_or_component" and "supplier_or_component" not in relationships:
        print("2330 excluded as supplier_or_component, not competitor")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
