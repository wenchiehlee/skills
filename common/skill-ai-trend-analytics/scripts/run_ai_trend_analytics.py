#!/usr/bin/env python3
"""Build AI trend coverage matrix and issue register from existing cycle outputs."""

from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
from pathlib import Path

import pandas as pd


GUIDELINE = "chats/AI_Trend_Analytics_Data_Refinement_Guideline.md"
MAPPING = "output/company_canonical_cycle_mapping.csv"
PERFORMANCE = "output/company_canonical_cycle_performance.csv"
PERFORMANCE_DETAILS = "output/company_canonical_cycle_performance_details.csv"
SEGMENT_WEIGHTS = "data/company_segment_weights.csv"
SEGMENT_QA = "output/company_segment_weights_qa_taiwan.md"
TW_QUARTERLY_CANDIDATES = "output/company_segment_weights_quarterly_candidates_taiwan.csv"
FRESHNESS = "data/data_freshness_status.csv"

OUT_COVERAGE_CSV = "output/ai_trend_coverage_matrix.csv"
OUT_COVERAGE_MD = "output/ai_trend_coverage_matrix.md"
OUT_ISSUES_CSV = "output/ai_trend_data_issue_register.csv"
OUT_ISSUES_MD = "output/ai_trend_data_issue_register.md"
OUT_INFERENCE_MD = "output/ai_trend_inference.md"

AI_CYCLE_PREFIXES = (
    "AI_",
    "Cloud_AI_Compute",
    "Software_SaaS",
    "Memory",
    "Memory_Commodity",
)

STATUS_RANK = {
    "VALID_DIRECT": 0,
    "VALID_DERIVED": 1,
    "ESTIMATED": 2,
    "PROXY": 3,
    "STALE": 4,
    "MISSING": 5,
    "CONFLICTING": 6,
    "INVALID": 7,
}


def now_cst() -> str:
    tz = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S CST")


def root_dir() -> Path:
    env_root = os.environ.get("BIZTRENDS_TW_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([Path.cwd(), *Path.cwd().parents])
    for candidate in candidates:
        if (candidate / MAPPING).is_file() and (candidate / PERFORMANCE_DETAILS).is_file():
            return candidate.resolve()
    raise SystemExit("Cannot find biztrends.TW root. Run from repo root or set BIZTRENDS_TW_ROOT.")


def read_csv(root: Path, rel: str) -> pd.DataFrame:
    path = root / rel
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")


def to_num(value: object) -> float:
    text = str(value or "").replace(",", "").replace("%", "").strip()
    if not text:
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def period_rank(period: str) -> tuple[int, int, int]:
    text = str(period or "").upper().strip()
    m = re.match(r"(20\d{2})Q([1-4])$", text)
    if m:
        return int(m.group(1)), int(m.group(2)), 2
    m = re.match(r"(20\d{2})-Q([1-4])$", text)
    if m:
        return int(m.group(1)), int(m.group(2)), 2
    m = re.match(r"(20\d{2})-FY$", text)
    if m:
        return int(m.group(1)), 5, 1
    m = re.match(r"(20\d{2})-(\d{2})$", text)
    if m:
        month = int(m.group(2))
        return int(m.group(1)), (month - 1) // 3 + 1, 0
    return 0, 0, 0


def latest_period(periods: pd.Series) -> str:
    values = [str(v) for v in periods.dropna().astype(str) if str(v)]
    if not values:
        return ""
    return max(values, key=period_rank)


def source_tier(source_type: str, source_file: str) -> str:
    st = source_type.lower()
    src = source_file.lower()
    if "official_annual" in st or "mops_financial_report" in st:
        return "audited_or_regulatory_filing"
    if "official_ir" in st:
        return "company_investor_presentation"
    if "conceptstocks" in src:
        return "structured_company_filing_or_release"
    if "company_cycle_mapping" in st:
        return "internal_mapping_proxy"
    return "derived_internal_output"


def initial_status(row: pd.Series) -> str:
    source_type = row.get("source_type", "")
    confidence = row.get("confidence", "")
    note = row.get("note", "")
    segment = row.get("segment_name", "")
    if "Company_Fallback" in segment or source_type == "company_cycle_mapping":
        return "PROXY"
    if "segment_weight_override=Y" in note:
        return "ESTIMATED"
    if confidence == "high":
        return "VALID_DERIVED"
    if confidence == "medium":
        return "ESTIMATED"
    if confidence in {"low", "none"}:
        return "PROXY"
    return "ESTIMATED"


def worse(a: str, b: str) -> str:
    return a if STATUS_RANK.get(a, 0) >= STATUS_RANK.get(b, 0) else b


def load_segment_context(root: Path) -> tuple[pd.DataFrame, dict[tuple[str, str], dict[str, object]]]:
    weights = read_csv(root, SEGMENT_WEIGHTS)
    context: dict[tuple[str, str], dict[str, object]] = {}
    if weights.empty:
        return weights, context
    for col in ["market", "stock_code", "source_period", "weight_pct", "status"]:
        if col not in weights.columns:
            weights[col] = ""
    active = weights[weights["status"].replace("", "active").str.lower().eq("active")].copy()
    active["weight_num"] = active["weight_pct"].map(to_num)
    grouped = active.groupby(["market", "stock_code"], dropna=False)
    for key, g in grouped:
        periods = sorted({str(v) for v in g["source_period"] if str(v)}, key=period_rank)
        sums = g.groupby("source_period")["weight_num"].sum().dropna().to_dict()
        bad_sums = {p: total for p, total in sums.items() if abs(float(total) - 100.0) > 0.2}
        context[(str(key[0] or "Taiwan"), str(key[1]))] = {
            "segment_row_count": int(len(g)),
            "source_period_count": len(periods),
            "latest_source_period": periods[-1] if periods else "",
            "bad_sums": bad_sums,
        }
    return weights, context


def freshness_lookup(root: Path) -> dict[str, str]:
    freshness = read_csv(root, FRESHNESS)
    if freshness.empty or "dest_path" not in freshness.columns:
        return {}
    out = {}
    for _, row in freshness.iterrows():
        out[str(row.get("dest_path", ""))] = str(row.get("freshness_status", "") or row.get("timestamp_health_status", ""))
    return out


def parse_candidate_values(value: object) -> list[float]:
    text = str(value or "").replace("/", ";")
    values = []
    for part in text.split(";"):
        part = part.strip()
        if not part or part.lower() == "nan":
            continue
        try:
            values.append(float(part))
        except ValueError:
            continue
    return values


def material_duplicate_conflicts(root: Path, threshold_pctpt: float = 1.0) -> dict[tuple[str, str], float]:
    q = read_csv(root, TW_QUARTERLY_CANDIDATES)
    required = {"review_status", "stock_code", "source_period", "candidate_weight_values"}
    if q.empty or not required.issubset(q.columns):
        return {}
    mask = q["review_status"].astype(str).str.contains("duplicate_weight_conflict", na=False)
    conflicts: dict[tuple[str, str], float] = {}
    for _, row in q.loc[mask].iterrows():
        values = parse_candidate_values(row.get("candidate_weight_values", ""))
        if len(values) < 2:
            continue
        spread = max(values) - min(values)
        if spread > threshold_pctpt:
            key = (str(row.get("stock_code", "")), str(row.get("source_period", "")))
            conflicts[key] = max(conflicts.get(key, 0.0), spread)
    return conflicts


def performance_impact(perf: pd.DataFrame, key_cols: list[str]) -> dict[tuple[str, str, str, str], dict[str, float]]:
    if perf.empty or "revenue" not in perf.columns:
        return {}
    data = perf.copy()
    data["revenue_num"] = data["revenue"].map(to_num)
    totals = data.groupby(["market_scope", "canonical_cycle"])["revenue_num"].sum().to_dict()
    impact: dict[tuple[str, str, str, str], dict[str, float]] = {}
    for _, row in data.iterrows():
        key = tuple(str(row.get(col, "")) for col in key_cols)
        market_cycle = (str(row.get("market_scope", "")), str(row.get("canonical_cycle", "")))
        revenue = to_num(row.get("revenue", ""))
        total = float(totals.get(market_cycle, 0.0) or 0.0)
        share = revenue / total * 100 if total and not math.isnan(revenue) else math.nan
        impact[key] = {"revenue": revenue, "cycle_revenue": total, "cycle_revenue_share_pct": share}
    return impact


def build_coverage(root: Path) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    mapping = read_csv(root, MAPPING)
    perf = read_csv(root, PERFORMANCE_DETAILS)
    _, seg_context = load_segment_context(root)
    fresh = freshness_lookup(root)
    material_conflicts = material_duplicate_conflicts(root)
    issues: list[dict[str, object]] = []

    if mapping.empty:
        raise SystemExit(f"Missing required input: {MAPPING}")
    if perf.empty:
        raise SystemExit(f"Missing required input: {PERFORMANCE_DETAILS}")

    key_cols = ["market_scope", "stock_code", "canonical_cycle", "segment_name"]
    for col in key_cols:
        if col not in mapping.columns:
            mapping[col] = ""
        if col not in perf.columns:
            perf[col] = ""
    perf_keys = set(map(tuple, perf[key_cols].astype(str).to_records(index=False)))
    perf_stock_cycle_keys = set(map(tuple, perf[["market_scope", "stock_code", "canonical_cycle"]].astype(str).to_records(index=False)))
    perf_impact = performance_impact(perf, key_cols)

    rows = []
    issue_id = 1
    for _, row in mapping.iterrows():
        market = str(row.get("market_scope", ""))
        stock = str(row.get("stock_code", ""))
        cycle = str(row.get("canonical_cycle", ""))
        segment = str(row.get("segment_name", ""))
        if cycle == "Other":
            continue
        if not cycle.startswith(AI_CYCLE_PREFIXES):
            continue
        if (
            str(row.get("source_type", "")) == "cycle_mapping_only"
            and not str(row.get("source_period", ""))
            and (market, stock, cycle) in perf_stock_cycle_keys
        ):
            continue

        key = (market, stock, cycle, segment)
        has_perf = key in perf_keys
        impact = perf_impact.get(key, {})
        revenue_impact = impact.get("revenue", math.nan)
        cycle_revenue_share = impact.get("cycle_revenue_share_pct", math.nan)
        seg = seg_context.get((market, stock), {})
        status = initial_status(row)
        issue_flags: list[str] = []
        known_limitations: list[str] = []
        next_actions: list[str] = []

        if not has_perf:
            status = worse(status, "MISSING")
            issue_flags.append("missing_performance")
            known_limitations.append("canonical mapping exists but latest performance row is missing")
            next_actions.append("rebuild company canonical cycle performance and verify source financials")

        source_period_count = int(seg.get("source_period_count", 0) or 0)
        if segment == "Company_Fallback" or str(row.get("source_type", "")) == "company_cycle_mapping":
            issue_flags.append("fallback_mapping")
            known_limitations.append("company/cycle mapping proxy; no direct segment weight evidence applied")
            next_actions.append("use skill-company-revenue-segment-weights to collect direct segment evidence")
        elif source_period_count <= 1 and market == "Taiwan":
            issue_flags.append("single_snapshot_weight")
            known_limitations.append("segment mix has only one active source period; historical cycle intensity is proxy")
            next_actions.append("collect quarterly segment weights or mark trend inference as estimated")

        bad_sums = seg.get("bad_sums", {}) or {}
        if bad_sums:
            status = worse(status, "INVALID")
            issue_flags.append("segment_weight_sum_invalid")
            known_limitations.append("active exclusive segment weights do not sum to 100% in at least one period")
            next_actions.append("fix active segment weights before using for financial attribution")

        row_period = str(row.get("source_period", "") or latest_perf_period(perf, key_cols, key))
        conflict_spread = material_conflicts.get((stock, row_period))
        if conflict_spread is not None:
            status = worse(status, "CONFLICTING")
            issue_flags.append("duplicate_weight_conflict")
            known_limitations.append(f"same-period candidate evidence contains material segment weight conflict up to {conflict_spread:.1f}ppt")
            next_actions.append("reconcile same-period conflicting evidence before high-confidence inference")

        if "raw_performance1.csv" in str(row.get("note", "")) and fresh.get("data/Python-Actions.GoodInfo.Analyzer/raw_performance1.csv") == "stale":
            status = worse(status, "STALE")
            issue_flags.append("stale_performance_source")

        source_file = PERFORMANCE_DETAILS if has_perf else MAPPING
        rows.append({
            "generated_at": now_cst(),
            "market_scope": market,
            "stock_code": stock,
            "company_name": row.get("company_name", ""),
            "canonical_cycle": cycle,
            "trend_domain": infer_trend_domain(cycle),
            "metric": "latest company-cycle attributed revenue/profit/gross margin",
            "product_level": "company_cycle",
            "frequency": "quarterly" if market == "United_States" else "monthly_or_quarterly_source",
            "data_status": status,
            "source_tier": source_tier(str(row.get("source_type", "")), source_file),
            "source_file": source_file,
            "latest_period": row.get("source_period", "") or latest_perf_period(perf, key_cols, key),
            "attributed_revenue": "" if math.isnan(revenue_impact) else round(revenue_impact, 4),
            "cycle_revenue_share_pct": "" if math.isnan(cycle_revenue_share) else round(cycle_revenue_share, 4),
            "historical_depth": seg.get("source_period_count", ""),
            "confidence": row.get("confidence", ""),
            "known_limitation": "; ".join(dict.fromkeys(known_limitations)),
            "issue_flags": ";".join(dict.fromkeys(issue_flags)),
            "next_collection_action": "; ".join(dict.fromkeys(next_actions)),
            "source_type": row.get("source_type", ""),
            "evidence_or_tags": row.get("evidence_or_tags", ""),
            "note": row.get("note", ""),
        })

        for flag in dict.fromkeys(issue_flags):
            severity = issue_severity(flag, cycle_revenue_share)
            evidence_text = "; ".join(dict.fromkeys(known_limitations)) or flag
            if flag == "fallback_mapping" and not math.isnan(cycle_revenue_share):
                evidence_text = f"{evidence_text}; attributed revenue share of cycle {cycle_revenue_share:.1f}%"
            issues.append({
                "issue_id": f"AI-TREND-{issue_id:04d}",
                "company_or_market": f"{market}:{stock} {row.get('company_name', '')}",
                "canonical_cycle": cycle,
                "metric_or_row": segment,
                "period": row.get("source_period", "") or latest_perf_period(perf, key_cols, key),
                "issue_type": flag,
                "evidence": evidence_text,
                "severity": severity,
                "trend_impact": f"{cycle} revenue/profit attribution confidence may be distorted",
                "suspected_cause": suspected_cause(flag),
                "temporary_treatment": temporary_treatment(flag),
                "required_fix": "; ".join(dict.fromkeys(next_actions)) or "review source evidence and rerun analytics",
                "replacement_source": replacement_source(flag),
                "owner": owner_for(flag),
                "status": "open",
                "recalculation_required": "Yes",
                "before_after_result": "",
                "closed_date": "",
                "version": "0.2.2",
            })
            issue_id += 1

    return pd.DataFrame(rows), issues


def latest_perf_period(perf: pd.DataFrame, key_cols: list[str], key: tuple[str, str, str, str]) -> str:
    if perf.empty or "period_label" not in perf.columns:
        return ""
    mask = pd.Series([True] * len(perf))
    for col, value in zip(key_cols, key):
        mask &= perf[col].astype(str).eq(str(value))
    return latest_period(perf.loc[mask, "period_label"])


def infer_trend_domain(cycle: str) -> str:
    if cycle in {"AI_Server_Rack", "AI_Network_Infra", "Cloud_AI_Compute"}:
        return "system_and_infrastructure_deployment"
    if cycle in {"AI_Accelerator", "AI_Foundry_Packaging", "AI_Memory_HBM", "Memory_Commodity", "Memory"}:
        return "semiconductor_and_component_supply"
    if cycle in {"Software_SaaS"}:
        return "adoption_and_monetization"
    return "company_financial_realization"


def issue_severity(flag: str, cycle_revenue_share_pct: float = math.nan) -> str:
    if flag in {"segment_weight_sum_invalid", "duplicate_weight_conflict"}:
        return "P0"
    if flag == "missing_performance":
        return "P1"
    if flag == "fallback_mapping":
        if not math.isnan(cycle_revenue_share_pct) and cycle_revenue_share_pct >= 5.0:
            return "P1"
        return "P2"
    if flag in {"single_snapshot_weight", "stale_performance_source"}:
        return "P2"
    return "P3"


def suspected_cause(flag: str) -> str:
    return {
        "segment_weight_sum_invalid": "exclusive financial attribution weights not reconciled",
        "duplicate_weight_conflict": "multiple source rows disagree for same company/period/segment",
        "missing_performance": "financial source or performance build gap",
        "fallback_mapping": "missing direct segment evidence",
        "single_snapshot_weight": "only latest active segment snapshot is available",
        "stale_performance_source": "upstream data freshness issue",
    }.get(flag, "unknown")


def temporary_treatment(flag: str) -> str:
    return {
        "segment_weight_sum_invalid": "quarantine",
        "duplicate_weight_conflict": "quarantine",
        "missing_performance": "exclude_from_high_confidence_inference",
        "fallback_mapping": "retain_as_proxy_with_caveat",
        "single_snapshot_weight": "downgrade_to_estimated",
        "stale_performance_source": "downgrade_to_stale",
    }.get(flag, "review")


def replacement_source(flag: str) -> str:
    if flag in {"fallback_mapping", "single_snapshot_weight", "duplicate_weight_conflict"}:
        return "company IR / annual report / MOPS / InvestorConference Markdown evidence"
    if flag == "missing_performance":
        return "GoodInfo raw_performance1.csv or ConceptStocks income CSV"
    return "primary company disclosure"


def owner_for(flag: str) -> str:
    if flag in {"fallback_mapping", "single_snapshot_weight", "duplicate_weight_conflict", "segment_weight_sum_invalid"}:
        return "skill-company-revenue-segment-weights"
    if flag == "missing_performance":
        return "skill-company-cycle-index"
    return "skill-ai-trend-analytics"


def write_outputs(root: Path, coverage: pd.DataFrame, issues: list[dict[str, object]]) -> None:
    issue_df = pd.DataFrame(issues)
    coverage_path = root / OUT_COVERAGE_CSV
    issue_path = root / OUT_ISSUES_CSV
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    issue_df.to_csv(issue_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    write_coverage_md(root, coverage)
    write_issue_md(root, issue_df)
    write_inference_md(root, coverage, issue_df)


def write_coverage_md(root: Path, df: pd.DataFrame) -> None:
    lines = [
        "# AI Trend Coverage Matrix",
        "",
        f"Generated: {now_cst()}",
        "",
        "This file is generated by `skill-ai-trend-analytics` from canonical cycle mapping, performance, segment weights, QA, and freshness outputs.",
        "",
        "## Summary",
        "",
        f"- Rows: `{len(df)}`",
        f"- Companies: `{df['stock_code'].nunique() if not df.empty else 0}`",
        f"- Canonical cycles: `{df['canonical_cycle'].nunique() if not df.empty else 0}`",
        "",
        "### Data Status Counts",
        "",
        "| Data status | Rows |",
        "|---|---:|",
    ]
    if not df.empty:
        for status, count in df["data_status"].value_counts().sort_index().items():
            lines.append(f"| `{status}` | {count} |")
    lines.extend(["", "### Cycle Coverage", "", "| Canonical cycle | Rows | Companies | Dominant status |", "|---|---:|---:|---|"])
    if not df.empty:
        for cycle, g in df.groupby("canonical_cycle"):
            dominant = g["data_status"].value_counts().idxmax()
            lines.append(f"| `{cycle}` | {len(g)} | {g['stock_code'].nunique()} | `{dominant}` |")
    lines.extend(["", "### Highest-Risk Rows", "", "| Market | Company | Cycle | Status | Issue flags | Next action |", "|---|---|---|---|---|---|"])
    risky = df[df["issue_flags"].astype(str).ne("")].copy()
    if not risky.empty:
        risky["_rank"] = risky["data_status"].map(lambda x: STATUS_RANK.get(str(x), 0))
        for _, row in risky.sort_values(["_rank", "canonical_cycle", "stock_code"], ascending=[False, True, True]).head(40).iterrows():
            lines.append(
                f"| {row['market_scope']} | `{row['stock_code']}` {row['company_name']} | `{row['canonical_cycle']}` | "
                f"`{row['data_status']}` | {row['issue_flags']} | {row['next_collection_action']} |"
            )
    (root / OUT_COVERAGE_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_issue_md(root: Path, df: pd.DataFrame) -> None:
    lines = [
        "# AI Trend Data Issue Register",
        "",
        f"Generated: {now_cst()}",
        "",
        "## Summary",
        "",
        f"- Open issues: `{len(df)}`",
        "",
        "| Severity | Issues |",
        "|---|---:|",
    ]
    if not df.empty:
        for severity, count in df["severity"].value_counts().sort_index().items():
            lines.append(f"| `{severity}` | {count} |")
    lines.extend(["", "## Open Issues", "", "| ID | Severity | Company / market | Cycle | Type | Temporary treatment | Required fix |", "|---|---|---|---|---|---|---|"])
    if not df.empty:
        severity_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        ordered = df.assign(_sev=df["severity"].map(lambda x: severity_order.get(str(x), 9))).sort_values(["_sev", "canonical_cycle", "company_or_market"])
        for _, row in ordered.head(80).iterrows():
            lines.append(
                f"| `{row['issue_id']}` | `{row['severity']}` | {row['company_or_market']} | `{row['canonical_cycle']}` | "
                f"`{row['issue_type']}` | {row['temporary_treatment']} | {row['required_fix']} |"
            )
    (root / OUT_ISSUES_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")



def fmt_num(value: object, digits: int = 1) -> str:
    num = to_num(value)
    if math.isnan(num):
        return "NA"
    return f"{num:,.{digits}f}"


def fmt_pct(value: object) -> str:
    num = to_num(value)
    if math.isnan(num):
        return "NA"
    sign = "+" if num >= 0 else ""
    return f"{sign}{num:.1f}%"


def fmt_ppt(value: object) -> str:
    num = to_num(value)
    if math.isnan(num):
        return "NA"
    sign = "+" if num >= 0 else ""
    return f"{sign}{num:.1f} ppt"


def confidence_from_quality(cov: pd.DataFrame, issues: pd.DataFrame) -> tuple[str, str]:
    if not issues.empty and (issues["severity"].astype(str) == "P0").any():
        return "Low", "P0 data conflict exists; inference must be quarantined until reconciled."
    if cov.empty:
        return "Low", "No coverage rows support this cycle."
    status_counts = cov["data_status"].value_counts().to_dict()
    rows = len(cov)
    valid_rows = status_counts.get("VALID_DIRECT", 0) + status_counts.get("VALID_DERIVED", 0)
    proxy_rows = status_counts.get("PROXY", 0) + status_counts.get("MISSING", 0)
    if valid_rows / rows >= 0.6 and proxy_rows == 0:
        return "Medium-high", "Most rows are valid or reproducibly derived, with no proxy/missing dominance."
    if valid_rows / rows >= 0.4:
        return "Medium", "Valid rows exist, but estimated/proxy rows still limit precision."
    if proxy_rows / rows >= 0.5:
        return "Low-medium", "Proxy or missing rows dominate coverage; use directionally only."
    return "Medium-low", "Evidence is mixed and should be treated as estimated."


def cycle_issue_summary(issues: pd.DataFrame) -> str:
    if issues.empty:
        return "No open issue registered."
    parts = []
    for severity, g in issues.groupby("severity"):
        parts.append(f"{severity}={len(g)}")
    top_types = ", ".join(issues["issue_type"].value_counts().head(3).index.astype(str))
    return f"{'; '.join(parts)}; top issue types: {top_types}."


def top_contributors(details: pd.DataFrame, market: str, cycle: str, limit: int = 3) -> str:
    if details.empty:
        return "NA"
    df = details[(details["market_scope"].astype(str).eq(market)) & (details["canonical_cycle"].astype(str).eq(cycle))].copy()
    if df.empty:
        return "NA"
    df["revenue_num"] = df["revenue"].map(to_num)
    df = df.dropna(subset=["revenue_num"]).sort_values("revenue_num", ascending=False).head(limit)
    if df.empty:
        return "NA"
    return "; ".join(
        f"{row.stock_code} {row.company_name} {fmt_num(row.revenue_num)} {row.currency_unit}"
        for row in df.itertuples(index=False)
    )


def scenario_text(yoy: float, gm_change: float, confidence: str) -> tuple[str, str, str]:
    if math.isnan(yoy):
        return (
            "Base: keep this cycle in monitoring mode until comparable revenue data is restored.",
            "Bull: evidence quality improves and revenue acceleration becomes measurable.",
            "Bear: missing or proxy data hides deterioration or double counting.",
        )
    if yoy >= 30:
        base = "Base: growth remains positive but decelerates as comparisons get harder."
        bull = "Bull: backlog/capacity conversion keeps YoY above current-cycle peers."
        bear = "Bear: order timing, inventory digestion, or customer acceptance delays compress YoY."
    elif yoy >= 10:
        base = "Base: cycle continues expanding at a moderate pace."
        bull = "Bull: upstream demand or customer deployment converts faster than current run-rate."
        bear = "Bear: growth falls back toward company-wide baseline if AI-specific evidence weakens."
    elif yoy >= 0:
        base = "Base: cycle is stable but not yet a strong acceleration signal."
        bull = "Bull: leading indicators improve and revenue growth broadens across companies."
        bear = "Bear: weak proxy coverage reveals that current growth is not AI-specific."
    else:
        base = "Base: cycle remains under pressure until revenue direction improves."
        bull = "Bull: decline is a base/timing effect and reverses in the next 1-4 quarters."
        bear = "Bear: weakness confirms inventory correction, pricing pressure, or demand slowdown."
    if gm_change < -2:
        bear += " Gross-margin deterioration is an additional warning."
    if confidence.startswith("Low"):
        base += " Confidence is constrained by coverage issues."
    return base, bull, bear


def write_inference_md(root: Path, coverage: pd.DataFrame, issues: pd.DataFrame) -> None:
    perf = read_csv(root, PERFORMANCE)
    details = read_csv(root, PERFORMANCE_DETAILS)
    if perf.empty:
        lines = [
            "# AI Trend Inference",
            "",
            f"Generated: {now_cst()}",
            "",
            f"Cannot build inference because `{PERFORMANCE}` is missing or empty.",
        ]
        (root / OUT_INFERENCE_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    for col in ["revenue", "revenue_yoy_pct", "operating_profit_yoy_pct", "gross_margin_change_ppt"]:
        if col not in perf.columns:
            perf[col] = ""
    lines = [
        "# AI Trend Inference",
        "",
        f"Generated: {now_cst()}",
        "",
        "This report is generated by `skill-ai-trend-analytics`. It is intentionally constrained by the coverage matrix and issue register; low-quality evidence is not promoted into high-confidence conclusions.",
        "",
        "## Quality Gate",
        "",
        f"- Coverage rows: `{len(coverage)}`",
        f"- Open issues: `{len(issues)}`",
    ]
    if not issues.empty and "severity" in issues.columns:
        severity_text = ", ".join(f"{sev}={count}" for sev, count in issues["severity"].value_counts().sort_index().items())
        lines.append(f"- Issue severity: `{severity_text}`")
    lines.extend([
        "- Any cycle with P0 issues is treated as quarantined for high-confidence inference.",
        "- Company-wide margin attribution remains an estimate unless segment-level profit is disclosed.",
        "",
        "## Cycle Inference",
        "",
    ])

    perf = perf[perf["canonical_cycle"].astype(str).str.startswith(AI_CYCLE_PREFIXES)].copy()
    perf["sort_revenue"] = perf["revenue"].map(to_num)
    perf = perf.sort_values(["market_scope", "sort_revenue"], ascending=[True, False])
    for _, row in perf.iterrows():
        market = str(row.get("market_scope", ""))
        cycle = str(row.get("canonical_cycle", ""))
        cov = coverage[(coverage["market_scope"].astype(str).eq(market)) & (coverage["canonical_cycle"].astype(str).eq(cycle))].copy()
        if not issues.empty:
            cyc_issues = issues[(issues["canonical_cycle"].astype(str).eq(cycle)) & (issues["company_or_market"].astype(str).str.startswith(f"{market}:"))].copy()
        else:
            cyc_issues = pd.DataFrame()
        confidence, confidence_reason = confidence_from_quality(cov, cyc_issues)
        yoy = to_num(row.get("revenue_yoy_pct", ""))
        gm_change = to_num(row.get("gross_margin_change_ppt", ""))
        base, bull, bear = scenario_text(yoy, gm_change, confidence)
        status_mix = "NA" if cov.empty else ", ".join(f"{k}={v}" for k, v in cov["data_status"].value_counts().sort_index().items())
        top = top_contributors(details, market, cycle)
        issue_summary = cycle_issue_summary(cyc_issues)
        period = str(row.get("period_range", ""))
        unit = str(row.get("currency_unit", ""))

        lines.extend([
            f"### {market} / `{cycle}`",
            "",
            f"**Observed facts:** Period `{period}` revenue is `{fmt_num(row.get('revenue'))}` {unit}; YoY is `{fmt_pct(row.get('revenue_yoy_pct'))}`; operating profit YoY is `{fmt_pct(row.get('operating_profit_yoy_pct'))}`; gross margin change is `{fmt_ppt(row.get('gross_margin_change_ppt'))}`.",
            "",
            f"**Derived indicators:** Coverage status mix is `{status_mix}`. Top contributors: {top}.",
            "",
            f"**Causal interpretation:** `{cycle}` is mapped to `{infer_trend_domain(cycle)}`. Treat the revenue/profit signal as company-cycle attribution, not pure AI end-demand, unless source rows are `VALID_DIRECT` or `VALID_DERIVED`.",
            "",
            "**Alternative explanations:** Timing of revenue recognition, fiscal/calendar period mismatch, single-snapshot segment weights, fallback supply-chain mapping, customer concentration, product mix changes, or non-AI revenue inside the same company segment may explain part of the move.",
            "",
            "**Timeline:** Nowcast to near term, normally current quarter through next 1-4 quarters. Do not extend beyond this horizon without leading indicators such as backlog, capex, RPO, order or utilization data.",
            "",
            f"**Scenario forecast:** {base} {bull} {bear}",
            "",
            "**Confirmation indicators:** direct segment revenue, backlog/bookings, customer deployment acceptance, upstream component shipments, inventory normalization, and repeated multi-quarter breadth across companies.",
            "",
            "**Invalidation indicators:** duplicate source conflicts, weight sums outside 100%, missing latest performance, sudden segment taxonomy changes, top-contributor concentration, inventory build, order pushout, or gross-margin deterioration.",
            "",
            f"**Confidence:** `{confidence}`. {confidence_reason}",
            "",
            f"**Main missing data:** {issue_summary}",
            "",
        ])

    (root / OUT_INFERENCE_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    root = root_dir()
    for rel in [GUIDELINE, MAPPING, PERFORMANCE_DETAILS]:
        if not (root / rel).is_file():
            raise SystemExit(f"Missing required input: {rel}")
    coverage, issues = build_coverage(root)
    write_outputs(root, coverage, issues)
    issue_df = pd.DataFrame(issues)
    print(f"Project root: {root}")
    print(f"Coverage rows: {len(coverage)} -> {OUT_COVERAGE_CSV}")
    print(f"Issue rows: {len(issue_df)} -> {OUT_ISSUES_CSV}")
    if not issue_df.empty:
        print("Issue severity counts:")
        for severity, count in issue_df["severity"].value_counts().sort_index().items():
            print(f"  {severity}: {count}")
    print(f"Markdown outputs: {OUT_COVERAGE_MD}, {OUT_ISSUES_MD}, {OUT_INFERENCE_MD}")


if __name__ == "__main__":
    main()
