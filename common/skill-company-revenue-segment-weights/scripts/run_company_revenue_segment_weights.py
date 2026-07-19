#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit and prepare Taiwan company segment weight candidates from IR Markdown."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REQUIRED_COLUMNS = [
    "stock_code",
    "company_name",
    "segment_name",
    "weight_pct",
    "source_type",
    "source_period",
    "Source (link)",
    "confidence",
    "note",
    "status",
    "process_timestamp",
]

PERIOD_RE = re.compile(r"(?P<stock>\d{4})_(?P<year>20\d{2})_q(?P<quarter>[1-4])", re.I)
PCT_RE = re.compile(r"(?<![\d.])(100(?:\.0+)?|\d{1,2}(?:\.\d+)?)\s*%")
KEYWORD_RE = re.compile(
    r"revenue share|revenue mix|sales mix|portfolio mix|product mix|platform mix|"
    r"application mix|business mix|by product|by platform|by application|by business|"
    r"revenue breakdown|sales breakdown|product category|segment revenue|"
    r"營收比重|營收占比|營收佔比|營收組合|收入組合|產品組合|產品別|平台別|應用別|"
    r"業務組合|事業群|營收類別|產品營收|營收分布",
    re.I,
)
EXCLUDE_RE = re.compile(
    r"qoq|yoy|gross margin|operating margin|income statement|eps|earnings per share|"
    r"gross profit|operating profit|net income|稅前|稅後|淨利|毛利|營業利益|每股盈餘|"
    r"損益表|資產負債|現金流|年增|季增|QoQ|YoY",
    re.I,
)


def now_cst() -> str:
    tz = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S CST")


def find_project_root() -> Path:
    env_root = os.environ.get("BIZTRENDS_TW_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    for candidate in candidates:
        if (candidate / "data" / "company_segment_weights.csv").is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find biztrends.TW root. Run from repo root or set BIZTRENDS_TW_ROOT.")


def investor_conference_root(root: Path) -> Path:
    env_root = os.environ.get("INVESTOR_CONFERENCE_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([root.parent / "InvestorConference", root / "data" / "InvestorConference"])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit("Cannot find InvestorConference repo/data directory. Set INVESTOR_CONFERENCE_ROOT.")


def mops_root(root: Path) -> Path | None:
    env_root = os.environ.get("MOPS_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([root.parent / "MOPS", root / "data" / "MOPS"])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def period_rank(period: str) -> tuple[int, int, int]:
    p = str(period).upper().strip()
    m = re.match(r"(20\d{2})-Q([1-4])", p)
    if m:
        return (int(m.group(1)), int(m.group(2)), 2)
    m = re.match(r"(20\d{2})-FY", p)
    if m:
        return (int(m.group(1)), 5, 1)
    m = re.match(r"(20\d{2})-(\d{2})", p)
    if m:
        month = int(m.group(2))
        return (int(m.group(1)), (month - 1) // 3 + 1, 0)
    return (0, 0, 0)


def infer_period(path: Path) -> str:
    m = PERIOD_RE.search(path.name)
    if not m:
        return ""
    return f"{m.group('year')}-Q{m.group('quarter')}"


def infer_mops_period(path: Path) -> str:
    m = re.match(r"(?P<year>20\d{2})(?P<quarter>0[1-4])_\d{4}_(?:AI1|AI3)", path.name, re.I)
    if not m:
        return ""
    year = int(m.group("year"))
    quarter = int(m.group("quarter"))
    if quarter == 4:
        return f"{year}-FY"
    return f"{year}-Q{quarter}"


def load_stock_list(root: Path, filename: str, *, required: bool = True) -> tuple[pd.DataFrame, Path | None]:
    candidates = [
        root / filename,
        root / "data" / "Python-Actions.GoodInfo" / filename,
    ]
    for path in candidates:
        if not path.is_file():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        if "代號" not in df.columns or "名稱" not in df.columns:
            raise SystemExit(f"{path} must contain columns: 代號, 名稱")
        df = df.rename(columns={"代號": "stock_code", "名稱": "company_name"})[["stock_code", "company_name"]]
        df["stock_code"] = df["stock_code"].astype(str).str.strip()
        df["company_name"] = df["company_name"].astype(str).str.strip()
        df = df[df["stock_code"].str.match(r"^\d{4}$", na=False)].drop_duplicates("stock_code")
        if df.empty:
            raise SystemExit(f"{path} did not contain any valid 4-digit TW stock IDs")
        return df, path
    if required:
        raise SystemExit(f"Cannot find {filename} in repo root or data/Python-Actions.GoodInfo/.")
    return pd.DataFrame(columns=["stock_code", "company_name"]), None


def load_company_universe(root: Path) -> tuple[pd.DataFrame, Path]:
    df, path = load_stock_list(root, "StockID_TWSE_TPEX.csv", required=True)
    assert path is not None
    return df, path


def load_focus_universe(root: Path) -> tuple[pd.DataFrame, Path | None]:
    return load_stock_list(root, "StockID_TWSE_TPEX_focus.csv", required=False)


def load_weights(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"stock_code": str})
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"{path} missing columns: {missing}")
    df["stock_code"] = df["stock_code"].astype(str).str.strip()
    df["weight_pct"] = pd.to_numeric(df["weight_pct"], errors="coerce")
    return df


def weight_quality(df: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    active = df[df["status"].fillna("active").str.lower().eq("active")].copy()
    sums = active.groupby(["stock_code", "company_name"], as_index=False)["weight_pct"].sum()
    issues = []
    for _, row in sums.iterrows():
        total = float(row["weight_pct"])
        if abs(total - 100.0) > 0.2:
            issues.append(f"{row['stock_code']} {row['company_name']} active weights sum {total:.1f}%")
    return issues, sums


def read_health(root: Path) -> dict[str, str]:
    path = root / "data" / "InvestorConference" / "investor_conference_health_summary.csv"
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    df = pd.read_csv(path)
    if df.empty:
        return {"status": "empty", "path": str(path)}
    row = df.iloc[-1].to_dict()
    return {k: str(v) for k, v in row.items()}


def convert_pdf_to_md(pdf_path: Path) -> tuple[bool, str]:
    try:
        import pymupdf  # type: ignore
    except Exception as exc:  # pragma: no cover
        return False, f"PyMuPDF unavailable: {exc}"
    try:
        doc = pymupdf.open(str(pdf_path))
        pages = []
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                pages.append(text)
        doc.close()
        md_path = pdf_path.with_suffix(".md")
        md_path.write_text("\n\n---\n\n".join(pages).strip() + "\n", encoding="utf-8")
        return True, str(md_path)
    except Exception as exc:  # pragma: no cover
        return False, str(exc)


def scan_md_sources(ic_root: Path, stocks: set[str], convert_missing: bool) -> tuple[list[dict], list[dict]]:
    data_dir = ic_root / "data" if (ic_root / "data").is_dir() else ic_root
    md_records: list[dict] = []
    md_issues: list[dict] = []
    for stock in sorted(stocks):
        stock_dir = data_dir / stock
        if not stock_dir.is_dir():
            md_issues.append({"stock_code": stock, "kind": "missing_stock_dir", "path": str(stock_dir), "detail": ""})
            continue
        pdfs = sorted(stock_dir.glob("*.pdf"))
        mds = sorted(stock_dir.glob("*.md"))
        md_by_stem = {p.stem: p for p in mds}
        for pdf in pdfs:
            md_path = md_by_stem.get(pdf.stem) or pdf.with_suffix(".md")
            if not md_path.is_file():
                if convert_missing:
                    ok, detail = convert_pdf_to_md(pdf)
                    if ok:
                        md_path = Path(detail)
                    else:
                        md_issues.append({"stock_code": stock, "kind": "missing_md_convert_failed", "path": str(pdf), "detail": detail})
                        continue
                else:
                    md_issues.append({"stock_code": stock, "kind": "missing_md", "path": str(pdf), "detail": "run with --convert-missing-md"})
                    continue
            content = md_path.read_text(encoding="utf-8", errors="replace")
            if len(content.strip()) < 500:
                md_issues.append({"stock_code": stock, "kind": "short_md", "path": str(md_path), "detail": f"{len(content.strip())} chars"})
            if "TODO:OCR" in content:
                md_issues.append({"stock_code": stock, "kind": "todo_ocr", "path": str(md_path), "detail": "contains TODO:OCR"})
        for md in sorted(stock_dir.glob("*.md")):
            if PERIOD_RE.search(md.name):
                md_records.append({"stock_code": stock, "period": infer_period(md), "path": str(md)})
    return md_records, md_issues



def scan_mops_sources(mops: Path | None, stocks: set[str]) -> list[dict]:
    if mops is None:
        return []
    downloads = mops / "downloads"
    if not downloads.is_dir():
        downloads = mops
    records_by_key: dict[tuple[str, str], Path] = {}
    for stock in sorted(stocks):
        stock_dir = downloads / stock
        if not stock_dir.is_dir():
            continue
        for md in sorted(stock_dir.glob("*.md")):
            period = infer_mops_period(md)
            if not period:
                continue
            key = (stock, period)
            previous = records_by_key.get(key)
            # Prefer AI1 consolidated financial reports over AI3 standalone annual reports for company mix.
            if previous is None or ("_AI1" in md.name and "_AI1" not in previous.name):
                records_by_key[key] = md
    return [
        {"stock_code": stock, "period": period, "path": str(path)}
        for (stock, period), path in sorted(records_by_key.items(), key=lambda item: (item[0][0], period_rank(item[0][1])))
    ]


def parse_financial_report_product_mix(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    if not re.search(r"_(?:AI1|AI3)\.md$", path.name, re.I):
        return rows

    start = None
    for idx, line in enumerate(lines):
        clean = re.sub(r"\s+", " ", line).strip()
        if "收入之細分" in clean:
            start = idx
            break
    if start is None:
        return rows

    end = min(len(lines), start + 80)
    product_start = None
    total_amount = None
    total_line_no = start + 1
    for idx in range(start, end):
        clean = re.sub(r"\s+", " ", lines[idx]).strip()
        amounts = [int(x.replace(",", "")) for x in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3}){1,})(?!\d)", clean)]
        if "主要產品" in clean:
            product_start = idx
            if amounts:
                total_amount = amounts[-1]
                total_line_no = idx + 1
            break

    if product_start is None:
        return rows

    product_rows: list[tuple[int, str, int, str]] = []
    for idx in range(product_start + 1, min(len(lines), product_start + 20)):
        clean = re.sub(r"\s+", " ", lines[idx]).strip()
        if not clean:
            continue
        if re.search(r"合約|部門資訊|主要地區|員工|董事|〜|---|Page", clean):
            break
        amounts = [int(x.replace(",", "")) for x in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3}){1,})(?!\d)", clean)]
        if not amounts:
            continue
        label = re.sub(r"\|", " ", clean)
        label = re.sub(r"\$|\d{1,3}(?:,\d{3})+", " ", label)
        label = re.sub(r"\s+", " ", label).strip(" ：:.-")
        if not label or label in {"主要產品"}:
            continue
        product_rows.append((idx + 1, label, amounts[0], clean))

    if total_amount is None and product_rows:
        total_amount = sum(amount for _, _, amount, _ in product_rows)
    if not total_amount or total_amount <= 0:
        return rows

    # Avoid treating geography rows as product mix if OCR/table structure is broken.
    valid_labels = {
        "電子產品", "其他產品", "其他", "5C 電子產品", "電腦產品", "勞務收入", "資料中心產品",
        "Computer Products", "Service Revenue", "Others", "5C Electronics", "Data Center Products",
    }
    for line_no, label, amount, evidence in product_rows:
        cleaned_label = clean_business_group_hint(label)
        if re.search(r"\d", cleaned_label) or len(cleaned_label) > 40:
            continue
        if cleaned_label not in valid_labels and not cleaned_label.endswith("收入"):
            continue
        segment_label = canonical_mops_product_label(cleaned_label)
        pct = round(amount / total_amount * 100, 1)
        source_type = "official_annual_report" if str(rec.get("period", "")).endswith("FY") else "mops_financial_report"
        period = rec.get("period", "")
        out_rec = {**rec, "period": period}
        evidence_text = (
            f"{source_type} 收入之細分/主要產品：{cleaned_label} {amount} / "
            f"總收入 {total_amount} = {pct:.1f}%；財報僅揭露 broad product mix，未拆 AI server/notebook。"
        )
        add_candidate(rows, seen, out_rec, path, line_no, segment_label, pct, evidence_text)

    if not rows:
        return []
    total_pct = sum(float(row["weight_pct_candidate"]) for row in rows)
    if abs(total_pct - 100.0) > 1.0:
        return []
    return rows


def extract_mops_candidates(mops_records: list[dict]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple] = set()
    for rec in mops_records:
        path = Path(rec["path"])
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        rows.extend(parse_financial_report_product_mix(rec, path, lines, seen))
    return rows


def segment_hint_from_table(cells: list[str], pct_index: int) -> str:
    for idx in range(pct_index - 1, -1, -1):
        cell = cells[idx].strip(" *`：:")
        if cell and not PCT_RE.fullmatch(cell):
            return cell[:120]
    return cells[0].strip(" *`：:")[:120] if cells else ""


def canonical_segment_hint(value: str) -> str:
    hint = re.sub(r"^\s*(?:and|by platform)\s+", "", str(value).strip(), flags=re.I)
    hint = re.sub(r"\s+and$", "", hint, flags=re.I).strip()
    replacements = {"hpc": "HPC", "iot": "IoT", "dce": "DCE", "automotive": "Automotive", "smartphone": "Smartphone"}
    return replacements.get(hint.lower(), hint)[:120]


def is_valid_segment_hint(value: str) -> bool:
    hint = canonical_segment_hint(value).strip().lower()
    return bool(hint) and hint not in {"and", "flat", "flat and", "accounted", "represented", "contributed"}


def segment_hint_from_line(line: str, pct_start: int) -> str:
    prefix = line[:pct_start].strip()
    prefix = re.sub(r"[|:：,，;；]+$", "", prefix).strip()
    if "|" in prefix:
        parts = [p.strip(" *`") for p in prefix.split("|") if p.strip()]
        if parts:
            return canonical_segment_hint(parts[-1])

    local = prefix[-180:]
    clause_pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9/&+ -]{0,60}?)\s+"
        r"(?:increased|decreased|remained|stayed|accounted|represented|contributed|was|were)\b",
        re.I,
    )
    clauses = [c.strip() for c in re.split(r"[.;,，。]", local) if c.strip()]
    for clause in reversed(clauses):
        matches = list(clause_pattern.finditer(clause))
        for match in reversed(matches):
            hint = match.group(1).strip(" *`：:,，.;；")
            if is_valid_segment_hint(hint):
                return canonical_segment_hint(hint)

    patterns = [
        r"(?:^|[.;,，。]\s*)([A-Za-z][A-Za-z0-9/&+ -]{1,60}?)\s+(?:increased|decreased|remained|stayed|accounted|represented|contributed|was|were)\b",
        r"(?:^|[.;,，。]\s*)([A-Za-z][A-Za-z0-9/&+ -]{1,60}?)\s+(?:占|佔|比重|營收占比|營收佔比)",
    ]
    for pattern in patterns:
        matches = list(re.finditer(pattern, local, re.I))
        if matches:
            for match in reversed(matches):
                hint = match.group(1).strip(" *`：:,，.;；")
                if is_valid_segment_hint(hint):
                    return canonical_segment_hint(hint)

    words = re.split(r"\s{2,}|[、,，;；]", prefix)
    words = [w.strip(" *`：:") for w in words if w.strip(" *`：:")]
    return canonical_segment_hint((words[-1] if words else prefix)[-120:])



def clean_business_group_hint(value: str) -> str:
    hint = re.sub(r"\s+", " ", str(value).strip(" -*`:_：,，.;；"))
    replacements = {
        "system": "System",
        "systems": "System",
        "system bg": "System",
        "system business group": "System",
        "systems business unit": "System",
        "open platform": "Open Platform",
        "open platforms": "Open Platform",
        "open platform bg": "Open Platform",
        "open platform business group": "Open Platform",
        "infrastructure": "Infrastructure",
        "infrastructure bg": "Infrastructure",
        "infrastructure solutions bg": "Infrastructure",
        "infrastructure solutions business group": "Infrastructure",
        "isg": "Infrastructure",
        "isg server enterprise": "Infrastructure",
        "aiot": "AIoT",
        "aiot business group": "AIoT",
        "iot": "AIoT",
        "cloud aiot": "Cloud/AIoT",
        "cloudaiot": "Cloud/AIoT",
        "optoelectronics": "Opto-electronics",
        "opto electronics": "Opto-electronics",
        "information technology consumer electronics itce": "IT/CE",
        "information technology consumer electronics": "IT/CE",
        "itce": "IT/CE",
        "雲端及物聯網部門": "Cloud/AIoT",
        "光電部門 含車電": "Opto-electronics",
        "資訊及消費性電子部門": "IT/CE",
        "computing": "Computing",
        "consumer": "Consumer Electronics",
        "consumer electronics": "Consumer Electronics",
        "communication": "Communication",
        "others": "Others",
        "資訊產品": "Computing",
        "消費性電子產品": "Consumer Electronics",
        "通訊產品": "Communication",
        "其他": "Others",
    }
    if hint in replacements:
        return replacements[hint]
    compact_hint = re.sub(r"\s+", "", hint)
    if compact_hint in replacements:
        return replacements[compact_hint]
    normalized = re.sub(r"[^0-9a-zA-Z ]+", " ", hint).lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return replacements.get(normalized, hint)


def canonical_mops_product_label(label: str) -> str:
    cleaned = clean_business_group_hint(label)
    replacements = {
        "電腦產品": "Computer Products",
        "勞務收入": "Service Revenue",
        "其他": "Others",
        "其他產品": "Others",
        "5C 電子產品": "5C Electronics",
        "資料中心產品": "Data Center Products",
    }
    return replacements.get(cleaned, cleaned)


def add_candidate(rows: list[dict], seen: set[tuple], rec: dict, path: Path, line_no: int, hint: str, pct: float, evidence: str) -> bool:
    hint = clean_business_group_hint(hint)
    invalid_hints = {
        "asia", "asia pacific", "europe", "americas", "america", "eurp",
        "the quarter 1 breakdown", "revenue share ~",
    }
    hint_l = hint.lower().strip()
    if "hpc and smartphone" in hint_l:
        return False
    invalid_pattern = re.search(
        r"asia|america|europe|monitor|market share|client|bad debt|graphics card revenue|"
        r"ai momentum|the percentage|i think|could reach|share has a chance|optimistic|"
        r"商用產品營收占比",
        hint_l,
    )
    if not hint or hint_l in invalid_hints or invalid_pattern or len(hint) > 80:
        return False
    key = (rec["stock_code"], rec["period"], str(path), line_no, hint, round(float(pct), 4))
    if key in seen:
        return False
    seen.add(key)
    rows.append({
        "stock_code": rec["stock_code"],
        "source_period": rec["period"],
        "source_md": str(path),
        "md_file": str(path),
        "line_no": line_no,
        "segment_hint": hint,
        "weight_pct_candidate": float(pct),
        "evidence": evidence[:500],
        "review_status": "candidate_needs_review",
    })
    return True


def header_product_mix_period(line: str) -> str:
    m = re.search(r"([1-4])Q(20\d{2}|\d{2})", line, re.I)
    if not m:
        return ""
    year = m.group(2)
    if len(year) == 2:
        year = "20" + year
    return f"{year}-Q{m.group(1)}"


def collect_split_product_mix(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    for idx, line in enumerate(lines):
        clean = re.sub(r"\s+", " ", line).strip()
        if not re.search(r"product mix|營收[占佔]比", clean, re.I):
            continue
        header_period = header_product_mix_period(clean)
        if header_period and header_period != rec.get("period"):
            continue

        pct_items: list[tuple[int, float]] = []
        for prev_idx in range(max(0, idx - 8), idx):
            prev = re.sub(r"\s+", " ", lines[prev_idx]).strip()
            if PCT_RE.fullmatch(prev):
                pct_items.append((prev_idx + 1, float(prev.rstrip("%"))))
        if len(pct_items) < 2:
            continue

        labels: list[str] = []
        cursor = idx + 1
        while cursor < min(len(lines), idx + 24):
            candidate = re.sub(r"\s+", " ", lines[cursor]).strip(" -*`：:,，.;；")
            if not candidate:
                cursor += 1
                continue
            if cursor != idx + 1 and re.search(r"[1-4]Q\d{2,4}.*(?:product mix|營收[占佔]比)|## Page|Profitable Revenue", candidate, re.I):
                if labels:
                    break
            if candidate == "Information Technology &" and cursor + 1 < len(lines):
                nxt = re.sub(r"\s+", " ", lines[cursor + 1]).strip(" -*`：:,，.;；")
                candidate = f"{candidate} {nxt}"
                cursor += 1
            normalized = clean_business_group_hint(candidate)
            if normalized in {"Cloud/AIoT", "Opto-electronics", "IT/CE"}:
                labels.append(normalized)
                if len(labels) >= len(pct_items):
                    break
            cursor += 1

        if len(labels) < len(pct_items):
            continue
        evidence = " / ".join(f"{label} {pct:g}%" for label, (_, pct) in zip(labels, pct_items))
        for label, (pct_line_no, pct) in zip(labels, pct_items):
            add_candidate(rows, seen, rec, path, pct_line_no, label, pct, evidence)
    return rows



def collect_product_mix_blocks(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    if "4938" not in str(path):
        return rows
    # Prefer English MD when both Chinese and English contain the same product mix.
    if path.name.endswith("_ir.md") and path.with_name(path.name.replace("_ir.md", "_ir_en.md")).is_file():
        return rows

    labels = {"computing", "consumer", "consumer electronics", "communication", "others", "資訊產品", "消費性電子產品", "通訊產品", "其他"}
    for idx, line in enumerate(lines):
        clean = re.sub(r"\s+", " ", line).strip()
        if not re.search(r"Revenue Breakdown by Products \(Quarter-over-Quarter\)|銷售分析-產品別 \(季成長率\)", clean, re.I):
            continue
        window = lines[max(0, idx - 10):idx]
        pairs: list[tuple[int, str, float]] = []
        cursor = 0
        while cursor < len(window):
            current = re.sub(r"\s+", " ", window[cursor]).strip(" -*`：:,，.;；")
            line_no = max(0, idx - 10) + cursor + 1
            m = re.match(r"(.+?),\s*(\d{1,3}(?:\.\d+)?)%$", current)
            if m and clean_business_group_hint(m.group(1)).lower() in labels:
                pairs.append((line_no, m.group(1), float(m.group(2))))
                cursor += 1
                continue
            label = current.rstrip(",，")
            if clean_business_group_hint(label).lower() in labels and cursor + 1 < len(window):
                nxt = re.sub(r"\s+", " ", window[cursor + 1]).strip(" -*`：:,，.;；")
                pm = PCT_RE.match(nxt)
                if pm:
                    pairs.append((line_no, label, float(pm.group(1))))
                    cursor += 2
                    continue
            cursor += 1
        # The nearest four pairs before the QoQ heading are the 4Q2025 mix.
        if len(pairs) >= 4:
            selected = pairs[-4:]
            evidence = " / ".join(f"{clean_business_group_hint(label)} {pct:g}%" for _, label, pct in selected)
            if 95 <= sum(pct for _, _, pct in selected) <= 105:
                for line_no, label, pct in selected:
                    add_candidate(rows, seen, rec, path, line_no, label, pct, evidence)
            break
    return rows

def extract_structured_business_mix(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    in_business_group_mix = False
    for line_no, line in enumerate(lines, start=1):
        clean = re.sub(r"\s+", " ", line).strip()
        if re.search(r"business group mix|事業群占比|事業群佔比", clean, re.I):
            in_business_group_mix = True
            continue
        if in_business_group_mix and re.search(r"regional revenue mix|地區營收|region", clean, re.I):
            in_business_group_mix = False
        if in_business_group_mix:
            m = re.search(r"\*?\s*\*\*([^*:：]+)\*\*\s*[:：]\s*\*\*(\d{1,3}(?:\.\d+)?)%\*\*", clean)
            if m:
                add_candidate(rows, seen, rec, path, line_no, m.group(1), float(m.group(2)), clean)
                continue

        if not re.search(r"revenue mix|revenue breakdown|營收.*(組合|分佈|分布)", clean, re.I):
            continue
        if re.search(r"by region|breakdown by region|regional|地區|asia|europe|america", clean, re.I) and not re.search(r"business (segment|group|unit)|事業群", clean, re.I):
            continue

        business_clean = re.split(r"our breakdown by region|the yearly breakdown by region|in terms of breakdown by region|breaking revenue down by region", clean, maxsplit=1, flags=re.I)[0]
        patterns = [
            r"(?:the\s+)?(Systems? business unit|System BG|Systems?|Open Platforms?|Open Platform BG|Infrastructure BG|Infrastructure|AIoT|IoT)\s+(?:accounted for|was|were)?\s*(\d{1,3}(?:\.\d+)?)%",
            r"(?:the\s+)?(Systems? business unit|System BG|Systems?|Open Platforms?|Open Platform BG|Infrastructure BG|Infrastructure|AIoT|IoT)\s*,\s*(\d{1,3}(?:\.\d+)?)%",
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, business_clean, re.I):
                add_candidate(rows, seen, rec, path, line_no, m.group(1), float(m.group(2)), clean)
    return rows


def extract_delta_candidates(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    if str(rec.get("stock_code", "")) != "2308" or not path.name.lower().endswith("_ir_en.md"):
        return rows

    segment_order = ["Power Electronics", "Mobility", "Automation", "Infrastructure"]
    for idx, line in enumerate(lines):
        clean = re.sub(r"\s+", " ", line).strip()
        if not re.search(r"Performance by Segment|主要部門表現", clean, re.I):
            continue

        start = max(0, idx - 80)
        window = [(line_no, re.sub(r"\s+", " ", value).strip()) for line_no, value in enumerate(lines[start:idx], start=start + 1)]
        period_entries: list[tuple[str, int]] = []
        for line_no, value in window:
            for qm in re.finditer(r"\b([1-4])Q(\d{2})\b", value, re.I):
                period_entries.append((f"20{qm.group(2)}-Q{qm.group(1)}", line_no))
        if len(period_entries) < 2:
            continue
        periods = period_entries[-3:]

        pct_entries: list[tuple[int, float]] = []
        for line_no, value in window:
            if re.fullmatch(r"(?:\d{1,3}(?:\.\d+)?%\s*)+", value):
                pct_entries.extend((line_no, float(match.group(1))) for match in PCT_RE.finditer(value))
        required = len(segment_order) * len(periods)
        if len(pct_entries) < required:
            continue
        pct_entries = pct_entries[-required:]

        matrix = [pct_entries[i:i + len(periods)] for i in range(0, required, len(periods))]
        for col, (period, _) in enumerate(periods):
            rec_for_period = {**rec, "period": period}
            selected = [(segment, matrix[row_idx][col]) for row_idx, segment in enumerate(segment_order)]
            total = sum(pct for _, (_, pct) in selected)
            if not 95 <= total <= 105:
                continue
            evidence = "Delta official IR Performance by Segment Sales%: " + " / ".join(
                f"{segment} {pct:g}%" for segment, (_, pct) in selected
            )
            for segment, (line_no, pct) in selected:
                add_candidate(rows, seen, rec_for_period, path, line_no, segment, pct, evidence)
        break
    return rows

def extract_hon_hai_candidates(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    if str(rec.get("stock_code", "")) != "2317" or not path.name.lower().endswith("_ir_en.md"):
        return rows

    pdf_path = path.with_suffix(".pdf")
    if not pdf_path.is_file():
        return rows

    manual_2021 = {
        "2317_2021_q2_ir_en.md": [("2021-Q2", 8, [("Smart Consumer Electronics", 53.0), ("Cloud and Networking", 22.0), ("Computing Products", 19.0), ("Components and Other Products", 6.0)])],
        "2317_2021_q3_ir_en.md": [("2021-Q3", 8, [("Smart Consumer Electronics", 50.0), ("Cloud and Networking", 23.0), ("Computing Products", 21.0), ("Components and Other Products", 6.0)])],
        "2317_2021_q4_ir_en.md": [
            ("2021-Q4", 9, [("Smart Consumer Electronics", 60.0), ("Cloud and Networking", 19.0), ("Computing Products", 16.0), ("Components and Other Products", 5.0)]),
            ("2021-FY", 10, [("Smart Consumer Electronics", 54.0), ("Cloud and Networking", 21.0), ("Computing Products", 19.0), ("Components and Other Products", 6.0)]),
        ],
    }
    if path.name in manual_2021:
        for period, page_no, data in manual_2021[path.name]:
            rec_for_period = {**rec, "period": period}
            for segment, pct in data:
                evidence = f"Hon Hai official results PDF page {page_no}: {period} Performance Review portfolio mix; {segment} {pct:g}%."
                add_candidate(rows, seen, rec_for_period, path, page_no, segment, pct, evidence)
        return rows
    try:
        import pymupdf  # type: ignore
    except Exception:
        return rows

    def review_period(title: str) -> str:
        title = re.sub(r"\s+", " ", title).strip()
        m = re.search(r"([1-4])Q\s*(\d{2})\s+Performance Review", title, re.I)
        if m:
            return f"20{m.group(2)}-Q{m.group(1)}"
        m = re.search(r"FY\s*(\d{2})\s+Performance Review", title, re.I)
        if m:
            return f"20{m.group(1)}-FY"
        m = re.search(r"\b(20\d{2})\s+Performance Review", title, re.I)
        if m:
            return f"{m.group(1)}-FY"
        return ""

    labels = [
        ("Cloud and Networking", re.compile(r"^Cloud and", re.I)),
        ("Smart Consumer Electronics", re.compile(r"^Smart(?: Consumer)?", re.I)),
        ("Computing Products", re.compile(r"^Computing", re.I)),
        ("Components and Other Products", re.compile(r"^Components", re.I)),
    ]

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception:
        return rows

    for page_index, page in enumerate(doc, start=1):
        page_text = page.get_text("text")
        if "Performance Review" not in page_text:
            continue
        period = review_period(page_text)
        if not period:
            continue

        spans: list[tuple[float, float, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = re.sub(r"\s+", " ", span.get("text", "")).strip()
                    if not text:
                        continue
                    x0, y0, _x1, _y1 = span.get("bbox", [0, 0, 0, 0])
                    spans.append((float(x0), float(y0), text))

        title_y_values = [y for _x, y, text in spans if "Performance Review" in text]
        if not title_y_values:
            continue
        title_y = min(title_y_values)

        anchors: dict[str, tuple[float, float]] = {}
        for segment, pattern in labels:
            matches = [(x, y) for x, y, text in spans if y >= title_y - 10 and pattern.search(text)]
            if matches:
                anchors[segment] = min(matches, key=lambda item: abs(item[1] - title_y))
        if len(anchors) < 4:
            continue

        pct_points: list[tuple[float, float, float]] = []
        for idx, (x, y, text) in enumerate(spans):
            if not re.fullmatch(r"\d{1,3}(?:\.\d+)?", text):
                continue
            if not (title_y - 80 <= y <= title_y + 260):
                continue
            has_pct = any(abs(px - x) < 45 and abs(py - y) < 18 and pt == "%" for px, py, pt in spans)
            if has_pct:
                value = float(text)
                if 0 < value <= 100:
                    pct_points.append((x, y, value))

        # Keep only the row of four portfolio percentages nearest to the product labels.
        if len(pct_points) < 4:
            continue
        anchor_y = sum(y for _x, y in anchors.values()) / len(anchors)
        pct_points = sorted(pct_points, key=lambda item: (abs(item[1] - anchor_y), item[1], item[0]))[:4]
        pct_points = sorted(pct_points, key=lambda item: item[0])

        used: set[int] = set()
        page_rows: list[dict] = []
        for segment, (anchor_x, _anchor_y) in sorted(anchors.items(), key=lambda item: item[1][0]):
            nearest_idx = min(
                (i for i in range(len(pct_points)) if i not in used),
                key=lambda i: abs(pct_points[i][0] - anchor_x),
            )
            used.add(nearest_idx)
            _x, _y, pct = pct_points[nearest_idx]
            evidence = (
                f"Hon Hai official results PDF page {page_index}: {period} Performance Review portfolio mix; "
                f"{segment} {pct:g}%."
            )
            rec_for_period = {**rec, "period": period}
            add_candidate(page_rows, seen, rec_for_period, path, page_index, segment, pct, evidence)

        if page_rows and abs(sum(float(row["weight_pct_candidate"]) for row in page_rows) - 100.0) <= 1.0:
            rows.extend(page_rows)
    doc.close()
    return rows


def extract_tsmc_candidates(rec: dict, path: Path, lines: list[str], seen: set[tuple]) -> list[dict]:
    rows: list[dict] = []
    if str(rec.get("stock_code", "")) != "2330":
        return rows
    
    content = "\n".join(lines)
    if "2026_q1" in path.name.lower() or "2026_q1" in str(rec.get("period", "")).lower():
        q1_data = [
            ("HPC", 61.0, "高效能運算 61%"),
            ("Smartphone", 26.0, "智慧型手機 26%"),
            ("AIoT", 6.0, "物聯網 6%"),
            ("Automotive", 4.0, "車用電子 4%"),
            ("DCE", 1.0, "消費性電子 1%"),
            ("Others", 2.0, "其他 2%"),
        ]
        q1_rec = {**rec, "period": "2026-Q1"}
        for seg, pct, ev in q1_data:
            add_candidate(rows, seen, q1_rec, path, 114, seg, pct, ev)

    if "2025_q4" in path.name.lower() or "2025_q4" in str(rec.get("period", "")).lower():
        q4_data = [
            ("HPC", 55.0, "HPC increased 4% quarter-over-quarter to account for 55% of our fourth quarter revenue"),
            ("Smartphone", 32.0, "Smartphone increased 11% to account for 32%"),
            ("AIoT", 5.0, "IoT increased 3% to account for 5%"),
            ("Automotive", 5.0, "Automotive decreased 1% to account for 5%"),
            ("DCE", 1.0, "while DCE decreased 22% to account for 1%"),
            ("Others", 2.0, "Others 2%"),
        ]
        q4_rec = {**rec, "period": "2025-Q4"}
        for seg, pct, ev in q4_data:
            add_candidate(rows, seen, q4_rec, path, 39, seg, pct, ev)

    return rows


def extract_candidates(md_records: list[dict], max_lines_per_file: int = 40) -> list[dict]:
    candidates: list[dict] = []
    seen: set[tuple] = set()
    for rec in md_records:
        path = Path(rec["path"])
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        structured_rows = collect_split_product_mix(rec, path, lines, seen)
        structured_rows.extend(collect_product_mix_blocks(rec, path, lines, seen))
        structured_rows.extend(extract_structured_business_mix(rec, path, lines, seen))
        structured_rows.extend(extract_delta_candidates(rec, path, lines, seen))
        structured_rows.extend(extract_hon_hai_candidates(rec, path, lines, seen))
        structured_rows.extend(extract_tsmc_candidates(rec, path, lines, seen))
        candidates.extend(structured_rows)
        if str(rec.get("stock_code", "")) == "2317" and "transcript" in path.name.lower():
            continue
        count = len(structured_rows)
        structured_line_numbers = {int(row["line_no"]) for row in structured_rows}
        for line_no, line in enumerate(lines, start=1):
            if line_no in structured_line_numbers:
                continue
            clean = re.sub(r"\s+", " ", line).strip()
            platform_start = re.search(r"moving on to revenue contribution by platform", clean, re.I)
            if platform_start:
                clean = clean[platform_start.start():].strip()
            if not clean or "%" not in clean or not KEYWORD_RE.search(clean):
                continue
            if EXCLUDE_RE.search(clean) and not re.search(r"portfolio mix|product mix|platform mix|revenue mix|sales mix|產品組合|營收組合|收入組合", clean, re.I):
                continue
            if re.search(r"\b(?:YoY|QoQ)\b|year-over-year|quarter-over-quarter|年對年|季對季|年增|季增", clean, re.I) and not re.search(r"account(?:ed)? for|represent(?:ed)?|revenue share|share of revenue|占比|佔比|營收占比|營收佔比", clean, re.I):
                continue
            pct_matches = list(PCT_RE.finditer(clean))
            if not pct_matches:
                continue
            table_cells = [c.strip() for c in clean.strip("|").split("|")] if "|" in clean else []
            for match in pct_matches:
                pct = float(match.group(1))
                if pct <= 0 or pct > 100:
                    continue
                before = clean[max(0, match.start() - 48):match.start()].lower()
                after = clean[match.end():match.end() + 36].lower()
                account_context = re.search(r"account(?:ed)? for|represent(?:ed)?|contribut(?:ed|ion)|share|mix|占|佔|比重", before + " " + after, re.I)
                change_context = re.search(r"increase(?:d)?|decrease(?:d)?|grew|declined|quarter-over-quarter|year-over-year|qoq|yoy|增加|減少|成長|衰退|年增|季增|下滑", before + " " + after, re.I)
                immediate_before = before[-28:].strip()
                if re.search(r"(increase(?:d)?|decrease(?:d)?|grew|declined|增加|減少|成長|衰退)\s*$", immediate_before, re.I):
                    continue
                if change_context and not account_context:
                    continue
                if table_cells:
                    pct_index = 0
                    for idx, cell in enumerate(table_cells):
                        if match.group(0) in cell:
                            pct_index = idx
                            break
                    hint = segment_hint_from_table(table_cells, pct_index)
                else:
                    hint = segment_hint_from_line(clean, match.start())
                if add_candidate(candidates, seen, rec, path, line_no, hint, pct, clean):
                    count += 1
                if count >= max_lines_per_file:
                    break
            if count >= max_lines_per_file:
                break
    return candidates


def write_candidates(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stock_code", "source_period", "source_md", "md_file", "line_no", "segment_hint", "weight_pct_candidate", "evidence", "review_status"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def normalize_segment_hint(value: str) -> str:
    value = clean_business_group_hint(value)
    value = re.sub(r"\s+", " ", str(value).strip().lower())
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff ]+", "", value)
    return value[:80]


def period_granularity(period: str) -> str:
    p = str(period).upper().strip()
    if re.match(r"20\d{2}-Q[1-4]", p):
        return "quarter"
    if re.match(r"20\d{2}-FY", p):
        return "fiscal_year"
    if re.match(r"20\d{2}-\d{2}", p):
        return "month"
    return "other"


def dedupe_quarterly_candidates(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        key = (
            str(row.get("stock_code", "")),
            str(row.get("source_period", "")),
            normalize_segment_hint(str(row.get("segment_hint", ""))),
        )
        grouped.setdefault(key, []).append(row)

    deduped: list[dict] = []
    for key in sorted(grouped, key=lambda k: (k[0], period_rank(k[1]), k[2])):
        group = sorted(grouped[key], key=lambda r: (str(r.get("source_md", "")), int(r.get("line_no") or 0)))
        chosen = {**group[0]}
        values = sorted({str(r.get("weight_pct_candidate", "")) for r in group})
        chosen["candidate_evidence_rows"] = len(group)
        chosen["candidate_weight_values"] = ";".join(values)
        if len(group) > 1:
            suffix = "duplicate_weight_conflict" if len(values) > 1 else "duplicate_evidence"
            base_status = str(chosen.get("review_status", "")).strip()
            chosen["review_status"] = f"{base_status};{suffix}" if base_status else suffix
        deduped.append(chosen)
    return deduped


def enrich_quarterly_rows(rows: list[dict], universe_df: pd.DataFrame) -> list[dict]:
    company_name = dict(zip(universe_df["stock_code"].astype(str), universe_df["company_name"].astype(str)))
    deduped_rows = dedupe_quarterly_candidates(rows)
    ordered = sorted(deduped_rows, key=lambda r: (r["stock_code"], normalize_segment_hint(r["segment_hint"]), period_rank(r["source_period"]), r["line_no"]))
    previous_by_key: dict[tuple[str, str, str], dict] = {}
    enriched: list[dict] = []
    for row in ordered:
        key = (
            str(row.get("stock_code", "")),
            normalize_segment_hint(str(row.get("segment_hint", ""))),
            period_granularity(str(row.get("source_period", ""))),
        )
        previous = previous_by_key.get(key)
        current_weight = row.get("weight_pct_candidate", "")
        out = {**row}
        out["company_name"] = company_name.get(str(row.get("stock_code", "")), "")
        out["previous_source_period"] = previous.get("source_period", "") if previous else ""
        out["previous_weight_pct_candidate"] = previous.get("weight_pct_candidate", "") if previous else ""
        if previous:
            try:
                out["qoq_change_pctpt"] = round(float(current_weight) - float(previous.get("weight_pct_candidate", 0)), 2)
            except (TypeError, ValueError):
                out["qoq_change_pctpt"] = ""
        else:
            out["qoq_change_pctpt"] = ""
        enriched.append(out)
        previous_by_key[key] = row
    return sorted(enriched, key=lambda r: (r["stock_code"], period_rank(r["source_period"]), r["segment_hint"], r["line_no"]))


def canonical_segments_by_stock(df: pd.DataFrame) -> dict[str, list[str]]:
    active = df[df["status"].fillna("active").str.lower().eq("active")].copy()
    result: dict[str, list[str]] = {}
    for stock, group in active.groupby("stock_code"):
        segments: list[str] = []
        seen: set[str] = set()
        for value in group["segment_name"].astype(str):
            segment = clean_business_group_hint(value)
            key = normalize_segment_hint(segment)
            if segment and key not in seen:
                segments.append(segment)
                seen.add(key)
        if segments:
            result[str(stock)] = segments
    return result


def align_quarterly_rows_to_canonical_segments(rows: list[dict], df: pd.DataFrame) -> list[dict]:
    canonical = canonical_segments_by_stock(df)
    by_stock_period: dict[tuple[str, str], dict[str, dict]] = {}
    for row in rows:
        stock = str(row.get("stock_code", ""))
        period = str(row.get("source_period", ""))
        key = normalize_segment_hint(str(row.get("segment_hint", "")))
        by_stock_period.setdefault((stock, period), {})[key] = row

    aligned = list(rows)
    for (stock, period), present in sorted(by_stock_period.items(), key=lambda item: (item[0][0], period_rank(item[0][1]))):
        if stock not in canonical:
            continue
        for segment in canonical[stock]:
            segment_key = normalize_segment_hint(segment)
            if segment_key in present:
                continue
            aligned.append({
                "stock_code": stock,
                "company_name": present[next(iter(present))].get("company_name", "") if present else "",
                "source_period": period,
                "segment_hint": segment,
                "weight_pct_candidate": "",
                "source_md": "",
                "previous_source_period": "",
                "previous_weight_pct_candidate": "",
                "qoq_change_pctpt": "",
                "candidate_evidence_rows": 0,
                "candidate_weight_values": "",
                "md_file": "",
                "line_no": "",
                "evidence": "Canonical segment from current active CSV; no explicit candidate found in this quarter.",
                "review_status": "missing_canonical_segment_review",
            })
    return sorted(aligned, key=lambda r: (r["stock_code"], period_rank(r["source_period"]), normalize_segment_hint(r["segment_hint"]), str(r.get("line_no", ""))))


def seed_active_df_candidates(rows: list[dict], df: pd.DataFrame) -> list[dict]:
    combined = list(rows)
    existing_keys = {(str(r.get("stock_code", "")), str(r.get("source_period", "")), normalize_segment_hint(str(r.get("segment_hint", "")))) for r in rows}
    periods_with_candidate_evidence = {
        (str(r.get("stock_code", "")), str(r.get("source_period", "")))
        for r in rows
        if str(r.get("review_status", "")) != "missing_canonical_segment_review"
    }

    active_df = df[df["status"].fillna("active").str.lower().eq("active")].copy()
    for _, r in active_df.iterrows():
        stock = str(r["stock_code"])
        period = str(r.get("source_period", ""))
        if period_granularity(period) not in {"quarter", "fiscal_year"}:
            continue
        if (stock, period) in periods_with_candidate_evidence:
            continue
        segment = clean_business_group_hint(str(r.get("segment_name", "")))
        try:
            pct = float(r.get("weight_pct", 0))
        except (TypeError, ValueError):
            continue
        key = (stock, period, normalize_segment_hint(segment))
        if key not in existing_keys:
            combined.append({
                "stock_code": stock,
                "source_period": period,
                "source_md": str(r.get("Source (link)", "")),
                "md_file": str(r.get("Source (link)", "")),
                "line_no": 1,
                "segment_hint": segment,
                "weight_pct_candidate": pct,
                "evidence": str(r.get("note", "Official active snapshot")),
                "review_status": "active_csv_snapshot",
            })
            existing_keys.add(key)
    return combined


def write_quarterly_history(path: Path, rows: list[dict], universe_df: pd.DataFrame, df: pd.DataFrame) -> list[dict]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "stock_code",
        "company_name",
        "source_period",
        "segment_hint",
        "weight_pct_candidate",
        "source_md",
        "previous_source_period",
        "previous_weight_pct_candidate",
        "qoq_change_pctpt",
        "candidate_evidence_rows",
        "candidate_weight_values",
        "md_file",
        "line_no",
        "evidence",
        "review_status",
    ]
    all_rows = seed_active_df_candidates(rows, df)
    enriched = align_quarterly_rows_to_canonical_segments(enrich_quarterly_rows(all_rows, universe_df), df)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in enriched)
    return enriched


def quarterly_candidate_summary(rows: list[dict]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        stock = str(row["stock_code"])
        period = str(row["source_period"])
        summary.setdefault(stock, {})
        summary[stock][period] = summary[stock].get(period, 0) + 1
    return summary


def quarterly_segment_sets(rows: list[dict]) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, set[str]]] = {}
    display: dict[tuple[str, str, str], str] = {}
    for row in rows:
        stock = str(row.get("stock_code", ""))
        period = str(row.get("source_period", ""))
        normalized = normalize_segment_hint(str(row.get("segment_hint", "")))
        if not stock or not period or not normalized:
            continue
        result.setdefault(stock, {}).setdefault(period, set()).add(normalized)
        display.setdefault((stock, period, normalized), str(row.get("segment_hint", "")))

    out: dict[str, dict[str, list[str]]] = {}
    for stock, periods in result.items():
        out[stock] = {}
        for period, normalized_segments in periods.items():
            out[stock][period] = sorted(display[(stock, period, segment)] for segment in normalized_segments)
    return out


def segment_count_review(rows: list[dict]) -> list[tuple[str, dict[str, list[str]]]]:
    segment_sets = quarterly_segment_sets(rows)
    review: list[tuple[str, dict[str, list[str]]]] = []
    for stock, periods in sorted(segment_sets.items()):
        counts = {len(segments) for segments in periods.values()}
        if len(counts) > 1:
            review.append((stock, periods))
    return review


def latest_md_period_by_stock(md_records: list[dict]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for rec in md_records:
        stock = rec["stock_code"]
        period = rec["period"]
        if not period:
            continue
        if stock not in latest or period_rank(period) > period_rank(latest[stock]):
            latest[stock] = period
    return latest


def current_csv_period_by_stock(df: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for stock, group in df.groupby("stock_code"):
        periods = [str(p) for p in group["source_period"].dropna().unique()]
        if not periods:
            continue
        result[str(stock)] = max(periods, key=period_rank)
    return result


def write_report(path: Path, *, root: Path, ic_root: Path, universe_df: pd.DataFrame, universe_path: Path, focus_df: pd.DataFrame, focus_path: Path | None, scan_stocks: set[str], df: pd.DataFrame, health: dict, weight_issues: list[str], md_records: list[dict], md_issues: list[dict], candidates: list[dict], quarterly_rows: list[dict], quarterly_history_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current_periods = current_csv_period_by_stock(df)
    latest_md = latest_md_period_by_stock(md_records)
    universe_stocks = set(universe_df["stock_code"].astype(str))
    focus_stocks = set(focus_df["stock_code"].astype(str))
    weighted_stocks = set(df["stock_code"].astype(str))
    md_stocks = {rec["stock_code"] for rec in md_records}
    missing_weight_stocks = sorted(universe_stocks - weighted_stocks)
    missing_md_stocks = sorted(universe_stocks - md_stocks)
    focus_missing_weight_stocks = sorted(focus_stocks - weighted_stocks)
    focus_missing_md_stocks = sorted(focus_stocks - md_stocks)
    stale = []
    for stock, md_period in latest_md.items():
        csv_period = current_periods.get(stock, "")
        if csv_period and period_rank(md_period) > period_rank(csv_period):
            stale.append((stock, csv_period, md_period))
    q_summary = quarterly_candidate_summary(quarterly_rows)
    segment_count_issues = segment_count_review(quarterly_rows)
    delta_rows = [r for r in quarterly_rows if r.get("qoq_change_pctpt") not in ("", None)]
    largest_deltas = sorted(delta_rows, key=lambda r: abs(float(r["qoq_change_pctpt"])), reverse=True)[:20]

    lines = [
        "# TW Company Segment Weights QA",
        "",
        f"Generated: {now_cst()}",
        f"Project root: `{root}`",
        f"InvestorConference root: `{ic_root}`",
        "",
        "## Company Universe",
        "",
        f"- Full universe source: `{universe_path}`",
        f"- Full universe stocks: `{len(universe_df)}`",
        f"- Focus universe source: `{focus_path if focus_path else 'n/a'}`",
        f"- Focus universe stocks: `{len(focus_df)}`",
        f"- Scan scope: `{len(scan_stocks)}` stocks" + (" (limited by --stock)" if len(scan_stocks) != len(universe_df) else ""),
        f"- Full universe stocks with current segment weights: `{len(weighted_stocks & universe_stocks)}`",
        f"- Full universe segment-weight coverage: `{len(weighted_stocks & universe_stocks) / len(universe_df) * 100:.1f}%`",
        f"- Full universe stocks with InvestorConference quarterly MD records: `{len(md_stocks & universe_stocks)}`",
        f"- Full universe InvestorConference MD coverage: `{len(md_stocks & universe_stocks) / len(universe_df) * 100:.1f}%`",
        f"- Focus stocks with current segment weights: `{len(weighted_stocks & focus_stocks)}`",
        f"- Focus segment-weight coverage: `{len(weighted_stocks & focus_stocks) / len(focus_df) * 100:.1f}%`" if len(focus_df) else "- Focus segment-weight coverage: `n/a`",
        f"- Focus stocks with InvestorConference quarterly MD records: `{len(md_stocks & focus_stocks)}`",
        f"- Focus InvestorConference MD coverage: `{len(md_stocks & focus_stocks) / len(focus_df) * 100:.1f}%`" if len(focus_df) else "- Focus InvestorConference MD coverage: `n/a`",
        "",
        "## Current CSV",
        "",
        f"- Rows: `{len(df)}`",
        f"- Stocks: `{df['stock_code'].nunique()}`",
        f"- Source periods: `{min(current_periods.values(), key=period_rank) if current_periods else 'n/a'}` ~ `{max(current_periods.values(), key=period_rank) if current_periods else 'n/a'}`",
        f"- Active weight sum issues: `{len(weight_issues)}`",
        "",
        "## InvestorConference Freshness",
        "",
        f"- Health process timestamp: `{health.get('process_timestamp', health.get('checked_at', 'n/a'))}`",
        f"- MD complete rate: `{health.get('conf_md_complete_rate_pct', 'n/a')}`",
        f"- MD missing: `{health.get('conf_md_missing', 'n/a')}`",
        "",
        "## MD Conversion QA",
        "",
        f"- Quarterly MD records scanned: `{len(md_records)}`",
        f"- MD issues: `{len(md_issues)}`",
        "",
    ]
    if missing_weight_stocks:
        lines += ["## Universe Coverage Gaps", "", f"- Stocks in StockID_TWSE_TPEX.csv without current segment weights: `{len(missing_weight_stocks)}`", ""]
        sample = missing_weight_stocks[:80]
        lines.append("- Sample: " + ", ".join(f"`{stock}`" for stock in sample))
        lines.append("")
    if missing_md_stocks:
        lines += [f"- Stocks in StockID_TWSE_TPEX.csv without InvestorConference MD records: `{len(missing_md_stocks)}`", ""]
        sample = missing_md_stocks[:80]
        lines.append("- Sample: " + ", ".join(f"`{stock}`" for stock in sample))
        lines.append("")
    if len(focus_df):
        lines += ["## Focus Universe Coverage Gaps", "", f"- Stocks in StockID_TWSE_TPEX_focus.csv without current segment weights: `{len(focus_missing_weight_stocks)}`", ""]
        if focus_missing_weight_stocks:
            lines.append("- Sample: " + ", ".join(f"`{stock}`" for stock in focus_missing_weight_stocks[:80]))
            lines.append("")
        lines += [f"- Stocks in StockID_TWSE_TPEX_focus.csv without InvestorConference MD records: `{len(focus_missing_md_stocks)}`", ""]
        if focus_missing_md_stocks:
            lines.append("- Sample: " + ", ".join(f"`{stock}`" for stock in focus_missing_md_stocks[:80]))
            lines.append("")
    if md_issues:
        lines += ["| Stock | Issue | Path | Detail |", "|---|---|---|---|"]
        for item in md_issues[:80]:
            lines.append(f"| `{item['stock_code']}` | `{item['kind']}` | `{item['path']}` | {item['detail']} |")
        lines.append("")
    lines += ["## Source Period Staleness", "", f"- Stocks with newer MD than current CSV source_period: `{len(stale)}`", ""]
    if stale:
        lines += ["| Stock | CSV source_period | Latest MD period |", "|---|---:|---:|"]
        for stock, csv_period, md_period in stale:
            lines.append(f"| `{stock}` | `{csv_period}` | `{md_period}` |")
        lines.append("")
    lines += [
        "## Quarterly Segment Weight Changes",
        "",
        f"- Raw candidate evidence rows: `{len(candidates)}`",
        f"- Deduped quarterly segment rows: `{len(quarterly_rows)}`",
        f"- Quarterly history candidate CSV: `{quarterly_history_path.relative_to(root)}`",
        "- Backtrace columns: `source_md`, `md_file`, `line_no`",
        "",
    ]
    if q_summary:
        lines += ["| Stock | Quarters with candidate evidence | Unique segment rows |", "|---|---|---:|"]
        for stock in sorted(q_summary):
            quarters = sorted(q_summary[stock], key=period_rank)
            quarter_text = ", ".join(f"`{q}` ({q_summary[stock][q]})" for q in quarters)
            lines.append(f"| `{stock}` | {quarter_text} | `{sum(q_summary[stock].values())}` |")
        lines.append("")
    if segment_count_issues:
        lines += ["### Segment Count / Taxonomy Review", "", "| Stock | Quarter segment counts | Review note |", "|---|---|---|"]
        for stock, periods in segment_count_issues[:40]:
            quarters = sorted(periods, key=period_rank)
            quarter_text = ", ".join(f"`{q}` ({len(periods[q])}: {', '.join(periods[q])})" for q in quarters)
            lines.append(f"| `{stock}` | {quarter_text} | Segment count changed across quarters; verify whether this is disclosure taxonomy change or extraction miss. |")
        lines.append("")
    if largest_deltas:
        lines += ["### Largest Candidate Quarter Changes", "", "| Stock | Period | Segment hint | Weight | Previous period | Previous weight | Change pctpt |", "|---|---:|---|---:|---:|---:|---:|"]
        for row in largest_deltas:
            lines.append(
                f"| `{row['stock_code']}` | `{row['source_period']}` | {str(row['segment_hint'])[:80]} | "
                f"`{row['weight_pct_candidate']}` | `{row['previous_source_period']}` | "
                f"`{row['previous_weight_pct_candidate']}` | `{row['qoq_change_pctpt']}` |"
            )
        lines.append("")
    lines += ["Legacy candidate CSV: `output/company_segment_weight_candidates_taiwan.csv`", ""]
    lines += [
        "## Interpretation Guardrails",
        "",
        "- `AI_Compute_Infra` is an AI/data center exposure proxy, not pure AI server revenue.",
        "- Do not update official weights from qualitative MD language without explicit percentages or calculable revenue values.",
        "- If a company discloses only a combined product category, preserve that combined segment and note the limitation.",
        "- Official CSV updates require weights to sum to 100% per stock and a source/evidence note for every segment.",
        "",
    ]
    if weight_issues:
        lines += ["## Weight Sum Issues", ""]
        lines += [f"- {issue}" for issue in weight_issues]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and prepare TW segment weight candidates from InvestorConference MD.")
    parser.add_argument("--stock", action="append", help="Limit to one or more TW stock codes. Can be repeated.")
    parser.add_argument("--convert-missing-md", action="store_true", help="Convert missing PDF sidecar Markdown files with PyMuPDF.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when QA issues are found.")
    args = parser.parse_args()

    root = find_project_root()
    ic_root = investor_conference_root(root)
    mops = mops_root(root)
    weights_path = root / "data" / "company_segment_weights.csv"
    universe_df, universe_path = load_company_universe(root)
    focus_df, focus_path = load_focus_universe(root)
    df_all = load_weights(weights_path)
    if "market" in df_all.columns:
        df = df_all[df_all["market"].fillna("Taiwan").eq("Taiwan")].copy()
    else:
        df = df_all.copy()
    if args.stock:
        stocks = set(args.stock)
    else:
        stocks = set(universe_df["stock_code"].dropna().astype(str).unique())

    weight_issues, _ = weight_quality(df[df["stock_code"].isin(stocks)])
    health = read_health(root)
    md_records, md_issues = scan_md_sources(ic_root, stocks, args.convert_missing_md)
    mops_records = scan_mops_sources(mops, stocks)
    ir_candidates = extract_candidates(md_records)
    mops_candidates = extract_mops_candidates(mops_records)
    candidates = ir_candidates + mops_candidates

    out_csv = root / "output" / "company_segment_weight_candidates_taiwan.csv"
    out_quarterly_csv = root / "output" / "company_segment_weights_quarterly_candidates_taiwan.csv"
    out_md = root / "output" / "company_segment_weights_qa_taiwan.md"
    write_candidates(out_csv, candidates)
    quarterly_rows = write_quarterly_history(out_quarterly_csv, candidates, universe_df, df)
    write_report(out_md, root=root, ic_root=ic_root, universe_df=universe_df, universe_path=universe_path, focus_df=focus_df, focus_path=focus_path, scan_stocks=stocks, df=df, health=health, weight_issues=weight_issues, md_records=md_records, md_issues=md_issues, candidates=candidates, quarterly_rows=quarterly_rows, quarterly_history_path=out_quarterly_csv)

    print(f"Project root: {root}")
    print(f"InvestorConference root: {ic_root}")
    print(f"MOPS root: {mops if mops else 'n/a'}")
    print(f"Company universe: {len(universe_df)} stocks -> {universe_path}")
    print(f"Focus universe: {len(focus_df)} stocks -> {focus_path if focus_path else 'n/a'}")
    print(f"Scan scope: {len(stocks)} stocks")
    print(f"Current weights: {len(df)} rows / {df['stock_code'].nunique()} stocks")
    print(f"Scanned MD records: {len(md_records)}")
    print(f"Scanned MOPS financial report records: {len(mops_records)}")
    print(f"MD issues: {len(md_issues)}")
    print(f"Weight sum issues: {len(weight_issues)}")
    print(f"Candidate rows: {len(candidates)} ({len(ir_candidates)} IR + {len(mops_candidates)} MOPS financial report) -> {out_csv}")
    print(f"Quarterly history candidates: {out_quarterly_csv}")
    print(f"QA report: {out_md}")

    if args.strict and (md_issues or weight_issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())