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
    }
    if hint in replacements:
        return replacements[hint]
    normalized = re.sub(r"[^0-9a-zA-Z ]+", " ", hint).lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return replacements.get(normalized, hint)


def add_candidate(rows: list[dict], seen: set[tuple], rec: dict, path: Path, line_no: int, hint: str, pct: float, evidence: str) -> bool:
    hint = clean_business_group_hint(hint)
    invalid_hints = {
        "asia", "asia pacific", "europe", "americas", "america", "eurp",
        "the quarter 1 breakdown", "revenue share ~",
    }
    hint_l = hint.lower().strip()
    invalid_pattern = re.search(
        r"asia|america|europe|monitor|market share|client|bad debt|graphics card revenue|"
        r"ai momentum|the percentage|i think|could reach|share has a chance|optimistic",
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
        structured_rows.extend(extract_structured_business_mix(rec, path, lines, seen))
        candidates.extend(structured_rows)
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
                change_context = re.search(r"increase(?:d)?|decrease(?:d)?|grew|declined|quarter-over-quarter|year-over-year|qoq|yoy|增加|減少|成長|衰退|年增|季增", before + " " + after, re.I)
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
    previous_by_key: dict[tuple[str, str], dict] = {}
    enriched: list[dict] = []
    for row in ordered:
        key = (str(row.get("stock_code", "")), normalize_segment_hint(str(row.get("segment_hint", ""))))
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
    
    active_df = df[df["status"].fillna("active").str.lower().eq("active")].copy()
    for _, r in active_df.iterrows():
        stock = str(r["stock_code"])
        period = str(r.get("source_period", ""))
        segment = str(r.get("segment_name", ""))
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
    candidates = extract_candidates(md_records)

    out_csv = root / "output" / "company_segment_weight_candidates_taiwan.csv"
    out_quarterly_csv = root / "output" / "company_segment_weights_quarterly_candidates_taiwan.csv"
    out_md = root / "output" / "company_segment_weights_qa_taiwan.md"
    write_candidates(out_csv, candidates)
    quarterly_rows = write_quarterly_history(out_quarterly_csv, candidates, universe_df, df)
    write_report(out_md, root=root, ic_root=ic_root, universe_df=universe_df, universe_path=universe_path, focus_df=focus_df, focus_path=focus_path, scan_stocks=stocks, df=df, health=health, weight_issues=weight_issues, md_records=md_records, md_issues=md_issues, candidates=candidates, quarterly_rows=quarterly_rows, quarterly_history_path=out_quarterly_csv)

    print(f"Project root: {root}")
    print(f"InvestorConference root: {ic_root}")
    print(f"Company universe: {len(universe_df)} stocks -> {universe_path}")
    print(f"Focus universe: {len(focus_df)} stocks -> {focus_path if focus_path else 'n/a'}")
    print(f"Scan scope: {len(stocks)} stocks")
    print(f"Current weights: {len(df)} rows / {df['stock_code'].nunique()} stocks")
    print(f"Scanned MD records: {len(md_records)}")
    print(f"MD issues: {len(md_issues)}")
    print(f"Weight sum issues: {len(weight_issues)}")
    print(f"Candidate rows: {len(candidates)} -> {out_csv}")
    print(f"Quarterly history candidates: {out_quarterly_csv}")
    print(f"QA report: {out_md}")

    if args.strict and (md_issues or weight_issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
