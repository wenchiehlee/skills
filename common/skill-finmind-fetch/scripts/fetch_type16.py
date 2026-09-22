#!/usr/bin/env python3
"""Fetch FinMind fundamentals and export an Analyzer-compatible Type 16 CSV.

This adapter deliberately keeps the FinMind source data and the derived ratio
calculation separate.  Values that cannot be reconstructed from FinMind are
left blank instead of being guessed.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from token_env import TokenRotator

API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASETS = (
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockCashFlowsStatement",
)
ANALYZER_HEADER = Path(__file__).resolve().parent.parent / "schemas" / "raw_fin_ratio_quarter_header.csv"


def number(value):
    try:
        value = float(value)
        return None if math.isnan(value) else value
    except (TypeError, ValueError):
        return None


def divide(a, b, multiplier=1.0):
    a, b = number(a), number(b)
    if a is None or b in (None, 0):
        return None
    return a / b * multiplier


def growth(current, previous):
    current, previous = number(current), number(previous)
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100


def quarter(value):
    d = datetime.strptime(value, "%Y-%m-%d")
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def fetch(session, dataset, stock_id, start_date, end_date, token):
    params = {"dataset": dataset, "data_id": stock_id,
              "start_date": start_date, "end_date": end_date}
    request_token = token.next() if isinstance(token, TokenRotator) else token
    if request_token:
        params["token"] = request_token
    for attempt in range(3):
        response = session.get(API_URL, params=params, timeout=90)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.ok and payload.get("msg") == "success":
            return payload.get("data", [])
        safe_error = payload.get("msg") or f"HTTP {response.status_code}"
        if isinstance(token, TokenRotator) and "token is illegal" in str(safe_error).strip().lower():
            token.retire(request_token)
            if token.count == 0:
                raise RuntimeError("FinMind rejected all configured tokens")
            return fetch(session, dataset, stock_id, start_date, end_date, token)
        if attempt < 2:
            time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"FinMind {dataset}: {safe_error}")
    return []


def index_records(records):
    result = defaultdict(dict)
    for item in records:
        # Prefer the main statement amount over FinMind's *_per percentage row.
        kind = item.get("type", "")
        if kind.endswith("_per"):
            continue
        result[item["date"]][kind] = number(item.get("value"))
    return result


def quarterly_values(indexed, dates):
    """Convert FinMind YTD income/cash-flow values into single-quarter values."""
    result = {}
    previous_by_year = {}
    for d in dates:
        raw = indexed[d]
        prior_date = previous_by_year.get(d[:4])
        if prior_date is None:
            result[d] = dict(raw)
        else:
            prior = indexed[prior_date]
            result[d] = {
                key: (value - prior[key] if value is not None and prior.get(key) is not None else value)
                for key, value in raw.items()
            }
        previous_by_year[d[:4]] = d
    return result


def sum_values(row, *names):
    values = [row.get(name) for name in names]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def build_rows(stock_id, company_name, records):
    fin = index_records(records["TaiwanStockFinancialStatements"])
    bal = index_records(records["TaiwanStockBalanceSheet"])
    cash = index_records(records["TaiwanStockCashFlowsStatement"])
    dates = sorted(set(fin) & set(bal) & set(cash))
    # FinMind income statements are already quarter values; cash-flow rows are YTD.
    cash = quarterly_values(cash, dates)
    output = []
    previous = None
    year_ago = {}
    for d in dates:
        bs, inc, cf = bal[d], fin[d], cash[d]
        revenue = inc.get("Revenue")
        gross = inc.get("GrossProfit")
        op_income = inc.get("OperatingIncome")
        pretax = inc.get("PreTaxIncome")
        net_income = inc.get("IncomeAfterTaxes")
        receivables = sum_values(
            bs, "AccountsReceivableNet", "AccountsReceivableDuefromRelatedPartiesNet",
            "OtherReceivablesDueFromRelatedParties",
        )
        payables = sum_values(
            bs, "AccountsPayable", "AccountsPayableToRelatedParties", "OtherPayables"
        )
        # GoodInfo classifies these as non-current residual categories.
        other_assets = bs.get("OtherNoncurrentAssets")
        other_liabilities = bs.get("OtherNoncurrentLiabilities")
        short_investments = sum_values(
            bs, "CurrentFinancialAssetsAtFairvalueThroughProfitOrLoss",
            "FinancialAssetsAtAmortizedCost",
            "FinancialAssetsAtFairvalueThroughOtherComprehensiveIncome",
            "HedgingAinancialAssets",
        )
        investments = sum_values(
            bs, "InvestmentAccountedForUsingEquityMethod",
            "NonCurrentFinancialAssetsAtFairvalueThroughProfitOrLoss",
            "FinancialAssetsAtFairvalueThroughOtherComprehensiveIncomeNonCurrent",
            "FinancialAssetsAtAmortizedCostNonCurrent",
        )
        current = {
            "cash": bs.get("CashAndCashEquivalents"), "receivables": receivables,
            "short_investments": short_investments,
            "inventory": bs.get("Inventories"), "current_assets": bs.get("CurrentAssets"),
            "investments": investments,
            "fixed_assets": bs.get("PropertyPlantAndEquipment"), "intangible": bs.get("IntangibleAssets"),
            "other_assets": other_assets, "assets": bs.get("TotalAssets"),
            "payables": payables, "current_liabilities": bs.get("CurrentLiabilities"),
            "long_debt": sum_values(bs, "LongtermBorrowings", "BondsPayable"),
            "other_liabilities": other_liabilities, "liabilities": bs.get("Liabilities"),
            "capital": bs.get("OrdinaryShare"), "equity": bs.get("Equity"),
            "parent_equity": bs.get("EquityAttributableToOwnersOfParent") or bs.get("Equity"),
            "revenue": revenue, "gross": gross, "op_income": op_income,
            "pretax": pretax, "net_income": net_income, "eps": inc.get("EPS"),
            "operating_cash": cf.get("CashFlowsFromOperatingActivities") or cf.get("NetCashInflowFromOperatingActivities"),
            "investing_cash": cf.get("CashProvidedByInvestingActivities"),
            "financing_cash": cf.get("CashFlowsProvidedFromFinancingActivities"),
            "cash_change": cf.get("CashBalancesIncrease"),
            "interest": abs(cf.get("PayTheInterest") or cf.get("InterestExpense") or 0),
        }
        values = {"stock_code": stock_id, "company_name": company_name, "季度": quarter(d)}
        total_assets = current["assets"]
        for key, field in [("cash", "現金 (%)"), ("receivables", "應收帳款 (%)"), ("inventory", "存貨 (%)"),
                           ("current_assets", "流動資產 (%)"), ("investments", "基金與投資 (%)"),
                           ("fixed_assets", "固定資產 (%)"), ("intangible", "無形資產 (%)"),
                           ("other_assets", "其他資產 (%)"), ("payables", "應付帳款 (%)"),
                           ("current_liabilities", "流動負債 (%)"), ("long_debt", "長期負債 (%)"),
                           ("liabilities", "負債總額 (%)"), ("capital", "普通股股本 (%)"),
                           ("equity", "股東權益總額 (%)")]:
            values[field] = divide(current[key], total_assets, 100)
        values.update({
            # Taiwan ordinary shares have a par value of NT0; balance-sheet
            # OrdinaryShare is the paid-in-capital amount, so this reconstructs
            # the issued-share denominator used by GoodInfo.
            "每股淨值 (元)股東權益總額 / 發行股數": divide(current["parent_equity"] * 10 if current["parent_equity"] is not None else None, current["capital"]),
            "營業毛利率營業毛利 / 營業收入 x 100%": divide(gross, revenue, 100),
            "營業利益率營業利益 / 營業收入 x 100%": divide(op_income, revenue, 100),
            "稅前淨利率稅前淨利 / 營業收入 x 100%": divide(pretax, revenue, 100),
            "稅後淨利率合併稅後淨利 / 營業收入 x 100%": divide(net_income, revenue, 100),
            "每股稅後盈餘 (元)稅後淨利 / 發行股數": current["eps"],
            "現金比現金及約當現金 / 流動負債 x 100%": divide(current["cash"], current["current_liabilities"], 100),
            "速動比速動資產 / 流動負債 x 100%": divide(sum_values(current, "cash", "receivables", "short_investments"), current["current_liabilities"], 100),
            "流動比流動資產 / 流動負債 x 100%": divide(current["current_assets"], current["current_liabilities"], 100),
            "負債對淨值比率負債總額 / 股東權益總額 x 100%": divide(current["liabilities"], current["equity"], 100),
            "現金流量比 (當季)營業活動淨現金流量 / 流動負債 x 100%": divide(current["operating_cash"], current["current_liabilities"], 100),
            "現金流量比 (年預估)營業活動淨現金流量 / 流動負債 x 100% x 4": divide(current["operating_cash"], current["current_liabilities"], 400),
            "營業成本率營業成本 / 營業收入 x 100%": divide(inc.get("CostOfGoodsSold"), revenue, 100),
            "營業費用率營業費用 / 營業收入 x 100%": divide(inc.get("OperatingExpenses"), revenue, 100),
            "每股營業現金流量 (元)營業活動之淨現金流入(出) / 發行股數": None,
            "每股投資現金流量 (元)投資活動之淨現金流入(出) / 發行股數": None,
            "每股融資現金流量 (元)融資活動之淨現金流入(出) / 發行股數": None,
            "每股淨現金流量 (元)當期現金及約當現金淨增減數 / 發行股數": None,
            "每股自由現金流量 (元)(營業活動之淨現金流入(出) + 投資活動之淨現金流入(出)) / 發行股數": None,
            "file_type": "finmind_type16", "source_file": "FinMind API",
            "download_success": True, "download_timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        growth_labels = {
            "cash": "現金", "receivables": "應收帳款", "inventory": "存貨",
            "current_assets": "流動資產", "investments": "基金與投資",
            "fixed_assets": "固定資產", "intangible": "無形資產",
            "other_assets": "其他資產", "assets": "資產總額",
            "payables": "應付帳款", "current_liabilities": "流動負債",
            "long_debt": "長期負債", "other_liabilities": "其他負債", "liabilities": "負債總額",
            "capital": "普通股股本", "equity": "股東權益總額",
        }
        if previous:
            for key, label in growth_labels.items():
                values[f"{label}季成長率"] = growth(current[key], previous[key])
        quarter_label = quarter(d)
        quarter_number = quarter_label[-1]
        year_ago[(d[:4], quarter_number)] = current
        prior_year = year_ago.get((str(int(d[:4]) - 1), quarter_number))
        if prior_year:
            for key in ("cash", "receivables", "inventory", "current_assets", "investments", "fixed_assets", "intangible", "other_assets", "assets", "payables", "current_liabilities", "long_debt", "other_liabilities", "liabilities", "capital", "equity"):
                values[f"{growth_labels[key]}年成長率"] = growth(current[key], prior_year[key])
        output.append(values)
        previous = current
    return output


def load_header():
    with ANALYZER_HEADER.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-id", default="2330")
    parser.add_argument("--company-name", default="台積電")
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--output", default="financial/type16/raw_fin_ratio_quarter_2330.csv")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()
    args.token = TokenRotator(args.token)
    session = requests.Session()
    records = {ds: fetch(session, ds, args.stock_id, args.start_date, args.end_date, args.token) for ds in DATASETS}
    rows = build_rows(args.stock_id, args.company_name, records)
    header = load_header()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {}
            for key in header:
                if key in row:
                    normalized[key] = row[key]
                    if isinstance(normalized[key], float):
                        normalized[key] = f"{normalized[key]:.2f}"
                    continue
                # The Analyzer schema contains both concise and formula-expanded
                # labels.  Fill both from the same calculated metric.
                aliases = [value for name, value in row.items() if name and (key.startswith(name) or name.startswith(key))]
                normalized[key] = aliases[0] if aliases else ""
                if isinstance(normalized[key], float):
                    normalized[key] = f"{normalized[key]:.2f}"
            writer.writerow(normalized)
    print(f"Wrote {len(rows)} quarter rows to {args.output}")
    print(f"FinMind token rotation count: {args.token.count}")


if __name__ == "__main__":
    main()
