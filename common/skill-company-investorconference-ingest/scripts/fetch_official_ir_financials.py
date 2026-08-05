#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
OUT_CSV = ROOT / "data/financials/raw_ir_quarterly_financials.csv"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

FIELDNAMES = [
    "symbol",
    "company_name",
    "market",
    "currency",
    "fiscal_year",
    "fiscal_quarter",
    "fiscal_period_label",
    "end_date",
    "period",
    "total_revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "gross_margin",
    "source_url",
    "source_type",
    "retrieved_at",
    "notes",
]

PROVIDERS = {
    "lenovo": {
        "symbol": "0992.HK",
        "company_name": "Lenovo Group Limited",
        "market": "Hong Kong",
        "currency": "USD",
        "url": "https://investor.lenovo.com/en/financial/key_fin_data.php",
    },
    "samsung": {
        "symbol": "005930.KS",
        "company_name": "Samsung Electronics Co., Ltd.",
        "market": "Korea",
        "currency": "KRW",
        "url": "https://www.samsung.com/global/ir/financial-information/earnings-release/",
    },
    "smic": {
        "symbol": "0981.HK",
        "company_name": "Semiconductor Manufacturing International Corporation",
        "market": "Hong Kong",
        "currency": "USD",
        "url": "https://www.smics.com/en/site/company_financialSummary",
    },
}

class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href = ""
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        self._current_href = attrs_dict.get("href", "")
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href:
            self.links.append({"href": self._current_href, "text": " ".join(self._current_text).strip()})
            self._current_href = ""
            self._current_text = []


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S CST")


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def number(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "nan", "None"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", "."}:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return -out if negative else out


def lenovo_end_date(fiscal_year: int, fiscal_quarter: int) -> str:
    if fiscal_quarter == 1:
        return f"{fiscal_year - 1}-06-30"
    if fiscal_quarter == 2:
        return f"{fiscal_year - 1}-09-30"
    if fiscal_quarter == 3:
        return f"{fiscal_year - 1}-12-31"
    return f"{fiscal_year}-03-31"


def html_cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
    out: list[str] = []
    for cell in cells:
        cell = re.sub(r"<br\s*/?>", " ", cell, flags=re.I)
        cell = re.sub(r"<[^>]+>", " ", cell)
        cell = re.sub(r"\s+", " ", cell).strip()
        out.append(cell)
    return out


def parse_lenovo() -> tuple[list[dict[str, str]], dict[str, Any]]:
    provider = PROVIDERS["lenovo"]
    html = fetch_text(provider["url"])
    table_match = re.search(r'<table[^>]+id="key_data_quarterly"[^>]*>(.*?)</table>', html, flags=re.I | re.S)
    if not table_match:
        raise RuntimeError("Could not find Lenovo quarterly table")
    table_html = table_match.group(1)
    row_htmls = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S)
    rows_cells = [html_cells(row) for row in row_htmls]
    header = next((cells for cells in rows_cells if any(re.fullmatch(r"Q[1-4]\s+\d{2}/\d{2}", cell) for cell in cells)), [])
    labels = [cell for cell in header if re.fullmatch(r"Q[1-4]\s+\d{2}/\d{2}", cell)]
    if not labels:
        raise RuntimeError("Could not find Lenovo quarterly labels")

    metric_values: dict[str, list[float | None]] = {}
    metric_aliases = {
        "Revenue": "total_revenue",
        "Gross Profit": "gross_profit",
        "Operating Profit": "operating_income",
        "Profit attributable to equity holders of the Company": "net_income",
    }
    for cells in rows_cells:
        if not cells:
            continue
        field = metric_aliases.get(cells[0])
        if not field or field in metric_values:
            continue
        values = [number(cell) for cell in cells[1:] if cell.strip() and cell not in {"<", ">", "&lt;", "&gt;"}]
        if len(values) >= len(labels):
            metric_values[field] = values[:len(labels)]

    rows: list[dict[str, str]] = []
    retrieved_at = now()
    for idx, label in enumerate(labels):
        match = re.search(r"Q([1-4])\s+(\d{2})/(\d{2})", label)
        if not match:
            continue
        fiscal_quarter = int(match.group(1))
        fiscal_year = 2000 + int(match.group(3))
        values = {field: vals[idx] if idx < len(vals) else None for field, vals in metric_values.items()}
        revenue = values.get("total_revenue")
        gross_profit = values.get("gross_profit")
        gross_margin = gross_profit / revenue if gross_profit is not None and revenue else None
        multiplier = 1_000_000.0
        rows.append({
            "symbol": provider["symbol"],
            "company_name": provider["company_name"],
            "market": provider["market"],
            "currency": provider["currency"],
            "fiscal_year": str(fiscal_year),
            "fiscal_quarter": str(fiscal_quarter),
            "fiscal_period_label": label,
            "end_date": lenovo_end_date(fiscal_year, fiscal_quarter),
            "period": f"Q{fiscal_quarter}",
            "total_revenue": "" if revenue is None else str(revenue * multiplier),
            "gross_profit": "" if gross_profit is None else str(gross_profit * multiplier),
            "operating_income": "" if values.get("operating_income") is None else str(values["operating_income"] * multiplier),
            "net_income": "" if values.get("net_income") is None else str(values["net_income"] * multiplier),
            "gross_margin": "" if gross_margin is None else str(gross_margin),
            "source_url": provider["url"],
            "source_type": "official_ir_html_key_financials",
            "retrieved_at": retrieved_at,
            "notes": "Lenovo official key financial data; source table unit is US$ million.",
        })

    source = {
        "symbol": provider["symbol"],
        "source_url": provider["url"],
        "source_type": "official_ir_html_key_financials",
        "retrieved_at": retrieved_at,
        "sha256": sha256_text(html),
        "notes": "Parsed Lenovo quarterly key financial table.",
    }
    return rows, source


def discover_links(provider_name: str) -> tuple[list[dict[str, str]], dict[str, Any]]:
    provider = PROVIDERS[provider_name]
    html = fetch_text(provider["url"])
    parser = LinkParser()
    parser.feed(html)
    links = [link for link in parser.links if re.search(r"pdf|financial|earning|result|quarter", (link.get("href", "") + " " + link.get("text", "")), re.I)]
    retrieved_at = now()
    source = {
        "symbol": provider["symbol"],
        "source_url": provider["url"],
        "source_type": "official_ir_discovery",
        "retrieved_at": retrieved_at,
        "sha256": sha256_text(html),
        "notes": "Discovery only; PDF/table parser still required before writing normalized quarterly rows.",
        "links": links[:40],
    }
    return [], source


def read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{field: str(row.get(field, "")) for field in FIELDNAMES} for row in rows]
    rows.sort(key=lambda r: (r["symbol"], r["end_date"], r["source_type"]))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_source(source: dict[str, Any]) -> None:
    symbol = source.get("symbol", "unknown")
    out_dir = ROOT / "data" / str(symbol)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{symbol}_official_ir_sources.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch official IR quarterly financial data into a normalized InvestorConference CSV.")
    parser.add_argument("--provider", choices=["all", *PROVIDERS.keys()], default="all")
    parser.add_argument("--out", default=str(OUT_CSV))
    parser.add_argument("--replace-symbol", action="store_true", help="Replace existing rows for fetched symbols.")
    args = parser.parse_args()

    providers = ["lenovo", "samsung", "smic"] if args.provider == "all" else [args.provider]
    existing = read_existing(Path(args.out))
    new_rows: list[dict[str, str]] = []
    symbols: set[str] = set()
    for provider in providers:
        try:
            if provider == "lenovo":
                rows, source = parse_lenovo()
            else:
                rows, source = discover_links(provider)
        except Exception as exc:
            print(f"{provider}: {exc}", file=sys.stderr)
            continue
        new_rows.extend(rows)
        symbols.add(str(source.get("symbol", "")))
        write_source(source)
        print(f"{provider}: {len(rows)} normalized rows; source sidecar written")

    if args.replace_symbol and symbols:
        existing = [row for row in existing if row.get("symbol") not in symbols]
    merged = existing + new_rows
    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in merged:
        dedup[(row.get("symbol", ""), row.get("end_date", ""), row.get("source_type", ""))] = row
    write_rows(Path(args.out), list(dedup.values()))
    print(f"wrote {len(dedup)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
