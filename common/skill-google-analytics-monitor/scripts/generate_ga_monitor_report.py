#!/usr/bin/env python3
"""Generate a GA4 monitoring Markdown report via Google Analytics Data API (Native REST or google-analytics-cli)."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import subprocess
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')
import urllib.request
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_METRICS = ["sessions", "totalUsers", "screenPageViews", "eventCount"]


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    data: Any | None
    json_path: Path | None = None


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(env: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or env.get(key) or default


def parse_windows(value: str) -> list[int]:
    windows = [int(item.strip()) for item in value.split(",") if item.strip()]
    return windows or [7, 28]


def subtract_months(day: date, months: int) -> date:
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, max_day))


def parse_json(text: str) -> Any | None:
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def subprocess_env(env: dict[str, str]) -> dict[str, str]:
    merged = os.environ.copy()
    for key, value in env.items():
        if value:
            merged[key] = value
    return merged


# ── Google Analytics REST Engine via Service Account ─────────────────────────

def resolve_service_account_credentials(arg_value: str | None, env: dict[str, str]) -> str | None:
    """Find Service Account JSON path or raw JSON string from args, env, or well-known local paths."""
    candidates = [
        arg_value,
        env_value(env, "GA4_SERVICE_ACCOUNT_KEY"),
        env_value(env, "GA_SERVICE_ACCOUNT_JSON"),
        env_value(env, "GOOGLE_APPLICATION_CREDENTIALS"),
    ]
    for c in candidates:
        if c and c.strip():
            return c.strip()

    # Search current & parent directories for key files
    for base in [Path.cwd(), Path.cwd().parent]:
        for fname in ["service_account_ga4.json", "service_account.json", "credentials.json"]:
            p = base / fname
            if p.exists():
                return str(p)

    return None


def get_rest_access_token(creds_input: str) -> str:
    """Acquire OAuth2 access token for GA4 Data API using Service Account."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    if os.path.exists(creds_input):
        creds = service_account.Credentials.from_service_account_file(
            creds_input,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )
    else:
        creds_info = json.loads(creds_input)
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"]
        )

    creds.refresh(Request())
    return creds.token


def run_ga_rest(
    name: str,
    property_id: str,
    token: str,
    report_type: str,
    metrics: list[str],
    dimensions: list[str] | None,
    start_date: date | None,
    end_date: date | None,
    filter_path: str | None,
    json_dir: Path | None,
) -> CommandResult:
    """Directly query GA4 Data API v1beta via REST."""
    if report_type == "realtime":
        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runRealtimeReport"
        payload: dict[str, Any] = {"metrics": [{"name": m} for m in metrics]}
        display_cmd = [f"ga4-rest:runRealtimeReport(property={property_id}, metrics={','.join(metrics)})"]
    else:
        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
        payload = {
            "dateRanges": [{"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}],
            "metrics": [{"name": m} for m in metrics],
            "dimensions": [{"name": d} for d in (dimensions or [])],
        }
        if filter_path:
            payload["dimensionFilter"] = {
                "filter": {
                    "fieldName": "pagePath",
                    "stringFilter": {
                        "matchType": "CONTAINS",
                        "value": filter_path
                    }
                }
            }
        display_cmd = [
            f"ga4-rest:runReport(property={property_id}, metrics={','.join(metrics)}, "
            f"dimensions={','.join(dimensions or [])}, filter={filter_path or 'none'})"
        ]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    json_path = None
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            stdout = json.dumps(data)
            returncode = 0
            stderr = ""
    except urllib.error.HTTPError as err:
        returncode = err.code
        stdout = ""
        stderr = err.read().decode("utf-8")
        data = None
    except Exception as exc:
        returncode = 1
        stdout = ""
        stderr = str(exc)
        data = None

    if json_dir is not None:
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{name}.json"
        payload_to_write = data if data is not None else {"stdout": stdout, "stderr": stderr}
        json_path.write_text(json.dumps(payload_to_write, ensure_ascii=False, indent=2), encoding="utf-8")

    return CommandResult(name, display_cmd, returncode, stdout, stderr, data, json_path)


# ── Legacy CLI Engine ────────────────────────────────────────────────────────

def run_ga(name: str, command: list[str], json_dir: Path | None, env: dict[str, str]) -> CommandResult:
    proc = subprocess.run(command, text=True, capture_output=True, check=False, env=subprocess_env(env))
    data = parse_json(proc.stdout)
    json_path = None
    if json_dir is not None:
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{name}.json"
        payload = data if data is not None else {"stdout": proc.stdout, "stderr": proc.stderr}
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CommandResult(name, command, proc.returncode, proc.stdout, proc.stderr, data, json_path)


def command_report(ga_bin: str, property_id: str, metrics: list[str], dimensions: list[str], start_date: date, end_date: date) -> list[str]:
    return [
        ga_bin,
        "reports",
        "run",
        "--property-id",
        property_id,
        "--metrics",
        ",".join(metrics),
        "--dimensions",
        ",".join(dimensions),
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--output",
        "json",
    ]


def command_realtime(ga_bin: str, property_id: str) -> list[str]:
    return [ga_bin, "reports", "realtime", "--property-id", property_id, "--metrics", "activeUsers", "--output", "json"]


# ── Data Formatting & Helpers ────────────────────────────────────────────────

def row_dicts(data: Any) -> list[dict[str, str]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [{str(k): str(v) for k, v in x.items()} for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    direct_rows = data.get("rows") or data.get("data") or data.get("results")
    if isinstance(direct_rows, list) and all(isinstance(x, dict) for x in direct_rows):
        dimension_headers = [h.get("name", f"dimension_{i}") for i, h in enumerate(data.get("dimensionHeaders", [])) if isinstance(h, dict)]
        metric_headers = [h.get("name", f"metric_{i}") for i, h in enumerate(data.get("metricHeaders", [])) if isinstance(h, dict)]
        converted = []
        for row in direct_rows:
            if "dimensionValues" in row or "metricValues" in row:
                item: dict[str, str] = {}
                for idx, value in enumerate(row.get("dimensionValues", [])):
                    key = dimension_headers[idx] if idx < len(dimension_headers) else f"dimension_{idx}"
                    item[key] = str(value.get("value", "")) if isinstance(value, dict) else str(value)
                for idx, value in enumerate(row.get("metricValues", [])):
                    key = metric_headers[idx] if idx < len(metric_headers) else f"metric_{idx}"
                    item[key] = str(value.get("value", "")) if isinstance(value, dict) else str(value)
                converted.append(item)
            else:
                converted.append({str(k): str(v) for k, v in row.items()})
        return converted
    for key in ("report", "response"):
        nested = data.get(key)
        if isinstance(nested, dict):
            rows = row_dicts(nested)
            if rows:
                return rows
    return []


def number(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def total(rows: list[dict[str, str]], metric: str) -> float:
    return sum(number(row.get(metric)) for row in rows)


def format_number(value: float) -> str:
    if value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def metric_summary(rows: list[dict[str, str]]) -> dict[str, float]:
    return {metric: total(rows, metric) for metric in DEFAULT_METRICS}


def percent_change(current: float, previous: float) -> str:
    if previous == 0:
        return "n/a" if current == 0 else "+100.0%"
    diff = ((current - previous) / previous) * 100
    prefix = "+" if diff > 0 else ""
    return f"{prefix}{diff:.1f}%"


def parse_ga_date(value: str) -> date | None:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def rows_between(rows: list[dict[str, str]], start_date: date, end_date: date) -> list[dict[str, str]]:
    matched: list[dict[str, str]] = []
    for row in rows:
        row_date = parse_ga_date(row.get("date", ""))
        if row_date and start_date <= row_date <= end_date:
            matched.append(row)
    return matched


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator_line = "-|-".join("-" * widths[i] for i in range(len(headers)))
    data_lines = [" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]
    return f"| {header_line} |\n| {separator_line} |\n" + "\n".join(f"| {line} |" for line in data_lines)


def dimension_table(rows: list[dict[str, str]], dimension_key: str, label: str, limit: int = 10) -> str:
    if not rows:
        return "No data returned."
    aggregated: dict[str, dict[str, float]] = {}
    for row in rows:
        key = row.get(dimension_key) or row.get("dimension_0") or "(not set)"
        if key not in aggregated:
            aggregated[key] = {m: 0.0 for m in DEFAULT_METRICS}
        for metric in DEFAULT_METRICS:
            aggregated[key][metric] += number(row.get(metric))
    sorted_items = sorted(aggregated.items(), key=lambda item: item[1]["screenPageViews"], reverse=True)[:limit]
    table_rows = [
        [
            key,
            format_number(metrics["sessions"]),
            format_number(metrics["totalUsers"]),
            format_number(metrics["screenPageViews"]),
            format_number(metrics["eventCount"]),
        ]
        for key, metrics in sorted_items
    ]
    return markdown_table([label, "Sessions", "Users", "Page Views", "Events"], table_rows)


def monthly_table(rows: list[dict[str, str]]) -> str:
    by_month: dict[str, dict[str, float]] = {}
    for row in rows:
        row_date = parse_ga_date(row.get("date", ""))
        if not row_date:
            continue
        key = row_date.strftime("%Y-%m")
        if key not in by_month:
            by_month[key] = {m: 0.0 for m in DEFAULT_METRICS}
        for metric in DEFAULT_METRICS:
            by_month[key][metric] += number(row.get(metric))
    table_rows = [
        [
            month,
            format_number(metrics["sessions"]),
            format_number(metrics["totalUsers"]),
            format_number(metrics["screenPageViews"]),
            format_number(metrics["eventCount"]),
        ]
        for month, metrics in sorted(by_month.items())
    ]
    return markdown_table(["Month", "Sessions", "Users", "Page Views", "Events"], table_rows) if table_rows else "No data returned."


def daily_tail_table(rows: list[dict[str, str]], days: int = 14) -> str:
    dated_rows: list[tuple[date, dict[str, str]]] = []
    for row in rows:
        row_date = parse_ga_date(row.get("date", ""))
        if row_date:
            dated_rows.append((row_date, row))
    dated_rows.sort(key=lambda item: item[0])
    tail = dated_rows[-days:]
    table_rows = [
        [
            d.isoformat(),
            format_number(number(r.get("sessions"))),
            format_number(number(r.get("totalUsers"))),
            format_number(number(r.get("screenPageViews"))),
            format_number(number(r.get("eventCount"))),
        ]
        for d, r in tail
    ]
    return markdown_table(["Date", "Sessions", "Users", "Page Views", "Events"], table_rows) if table_rows else "No data returned."


def realtime_active_users(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "0"
    value = rows[0].get("activeUsers")
    if value is None:
        value = next(iter(rows[0].values()), None)
    return format_number(number(value))


def generated_time_cst() -> str:
    cst = timezone(timedelta(hours=8), "CST")
    return datetime.now(cst).strftime("%Y-%m-%d %H:%M:%S CST")


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def truthy(value: str | None) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def masked_property_id(property_id: str, show_property_id: bool) -> str:
    if show_property_id:
        return property_id
    if len(property_id) <= 4:
        return "hidden"
    return f"hidden-{property_id[-4:]}"


def display_command(command: list[str], show_property_id: bool) -> str:
    if show_property_id:
        return " ".join(command)
    rendered: list[str] = []
    skip_next = False
    for i, token in enumerate(command):
        if skip_next:
            skip_next = False
            continue
        if token == "--property-id" and i + 1 < len(command):
            rendered.extend(["--property-id", masked_property_id(command[i + 1], False)])
            skip_next = True
        else:
            rendered.append(token)
    return " ".join(rendered)


def build_report(
    property_id: str,
    site_name: str,
    start_date: date,
    end_date: date,
    windows: list[int],
    results: dict[str, CommandResult],
    show_property_id: bool = False,
    filter_path: str | None = None,
) -> str:
    trend_rows = row_dicts(results["trend"].data)
    source_rows = row_dicts(results["sources"].data)
    page_rows = row_dicts(results["pages"].data)
    url_rows = row_dicts(results["urls"].data)
    event_rows = row_dicts(results["events"].data)
    realtime_rows = row_dicts(results["realtime"].data)
    summary = metric_summary(trend_rows)
    generated_at = generated_time_cst()
    public_property_id = masked_property_id(property_id, show_property_id)
    scope_label = f" (Path Filter: `{filter_path}`)" if filter_path else ""

    lines = [
        "---",
        "title: GA4 Website Monitoring Report",
        "report_type: ga4_monitor",
        "update_frequency: daily",
        f"site: {yaml_scalar((site_name or 'n/a') + scope_label)}",
        f"property_id: {yaml_scalar(public_property_id)}",
        f"historical_window_start: {yaml_scalar(start_date.isoformat())}",
        f"historical_window_end: {yaml_scalar(end_date.isoformat())}",
        f"generated_at: {yaml_scalar(generated_at)}",
        f"產生時間: {yaml_scalar(generated_at)}",
        "---",
        "",
        "# GA4 Website Monitoring Report",
        "",
        f"- Site: {site_name or 'n/a'}{scope_label}",
        f"- Property ID: `{public_property_id}`",
        f"- Historical window: {start_date.isoformat()} to {end_date.isoformat()}",
        f"- 產生時間: {generated_at}",
        "",
        "## Executive Summary",
        "",
        f"- Realtime active users: {realtime_active_users(realtime_rows)}",
        f"- 3-month sessions: {format_number(summary['sessions'])}",
        f"- 3-month users: {format_number(summary['totalUsers'])}",
        f"- 3-month page views: {format_number(summary['screenPageViews'])}",
        f"- 3-month events: {format_number(summary['eventCount'])}",
        "",
        "## Realtime",
        "",
        f"- Active users now: {realtime_active_users(realtime_rows)}",
        "",
        "## Short-Term Trend",
        "",
    ]

    short_term_rows: list[list[str]] = []
    for window in windows:
        current_start = end_date - timedelta(days=window - 1)
        current_rows = rows_between(trend_rows, current_start, end_date)
        current_summary = metric_summary(current_rows)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=window - 1)
        previous_rows = rows_between(trend_rows, previous_start, previous_end)
        previous_summary = metric_summary(previous_rows)
        for metric in DEFAULT_METRICS:
            c = current_summary[metric]
            p = previous_summary[metric]
            short_term_rows.append([f"Last {window}d", metric, format_number(c), format_number(p), percent_change(c, p)])
    lines.append(markdown_table(["Window", "Metric", "Current", "Previous", "Change"], short_term_rows) if short_term_rows else "No data returned.")
    lines.extend([
        "",
        "## 3-Month Trend",
        "",
        "### Monthly Rollup",
        "",
        monthly_table(trend_rows),
        "",
        "### Recent Daily Activity (Last 14 Days)",
        "",
        daily_tail_table(trend_rows, 14),
        "",
        "## Traffic Sources",
        "",
        dimension_table(source_rows, "sessionSourceMedium", "Source / Medium"),
        "",
        "## Top Pages",
        "",
        "### Top URLs",
        "",
        dimension_table(url_rows, "pageLocation", "Page URL"),
        "",
        "### Top Page Paths",
        "",
        dimension_table(page_rows, "pagePath", "Page Path"),
        "",
        "## Events",
        "",
        dimension_table(event_rows, "eventName", "Event Name"),
        "",
        "## Anomaly Observations",
        "",
    ])

    anomalies: list[str] = []
    for window in windows:
        current_start = end_date - timedelta(days=window - 1)
        current_summary = metric_summary(rows_between(trend_rows, current_start, end_date))
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=window - 1)
        previous_summary = metric_summary(rows_between(trend_rows, previous_start, previous_end))
        for metric in ("sessions", "screenPageViews"):
            c = current_summary[metric]
            p = previous_summary[metric]
            if p > 0:
                pct = ((c - p) / p) * 100
                if abs(pct) >= 30:
                    direction = "surged" if pct > 0 else "dropped"
                    anomalies.append(f"- Last {window}d {metric} {direction} by {abs(pct):.1f}% ({format_number(p)} -> {format_number(c)}).")
    if not anomalies:
        anomalies.append("- No sharp 30%+ swings detected across short-term monitoring windows.")
    lines.extend(anomalies)

    lines.extend([
        "",
        "## Raw Command Audit",
        "",
    ])
    audit_rows: list[list[str]] = []
    for result in results.values():
        status = "OK" if result.returncode == 0 else f"Failed ({result.returncode})"
        json_link = f"`{result.json_path}`" if result.json_path else "n/a"
        audit_rows.append([result.name, f"`{display_command(result.command, show_property_id)}`", status, json_link])
    lines.append(markdown_table(["Report", "Command", "Status", "JSON Dump"], audit_rows))

    failures = [r for r in results.values() if r.returncode != 0]
    if failures:
        lines.extend(["", "### Execution Warnings", ""])
        for failure in failures:
            lines.extend([
                f"- **{failure.name}**: {failure.stderr.strip() or 'Command failed without stderr.'}",
            ])

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Path to .env file.")
    parser.add_argument("--property-id", help="GA4 property ID. Overrides GOOGLE_ANALYTICS_KEY.")
    parser.add_argument("--site-name", help="Display name. Overrides GA_SITE_NAME.")
    parser.add_argument("--filter-path", help="Optional path filter (e.g. /mkdocs-life/). Overrides GA_FILTER_PATH.")
    parser.add_argument("--service-account", help="Path to Service Account JSON key or JSON string. Overrides GA4_SERVICE_ACCOUNT_KEY.")
    parser.add_argument("--months", type=int, help="Historical window in months. Defaults to GA_REPORT_MONTHS or 3.")
    parser.add_argument("--include-short-windows", help="Comma-separated day windows. Defaults to GA_INCLUDE_SHORT_WINDOWS or 7,28.")
    parser.add_argument("--start-date", help="Explicit start date YYYY-MM-DD. Overrides --months.")
    parser.add_argument("--end-date", help="Explicit end date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--output", help="Markdown output path. Overrides GA_REPORT_OUTPUT.")
    parser.add_argument("--json-dir", help="Optional raw JSON directory. Overrides GA_JSON_DIR.")
    parser.add_argument("--ga-bin", help="GA CLI binary path. Overrides GA_CLI_BIN.")
    parser.add_argument("--force-cli", action="store_true", help="Force using google-analytics-cli even if service account is available.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = load_env(Path(args.env_file))

    property_id = args.property_id or env_value(env, "GOOGLE_ANALYTICS_KEY") or env_value(env, "GA_PROPERTY_ID")
    if not property_id:
        print("Missing GOOGLE_ANALYTICS_KEY. Add it to .env or pass --property-id.", file=sys.stderr)
        return 2
    if property_id.upper().startswith("G-"):
        print(
            "GOOGLE_ANALYTICS_KEY must be the numeric GA4 property ID used by the Data API, "
            "not the G- measurement ID from a web data stream.",
            file=sys.stderr,
        )
        return 2

    site_name = args.site_name or env_value(env, "GA_SITE_NAME", "") or ""
    filter_path = args.filter_path or env_value(env, "GA_FILTER_PATH")
    months = args.months or int(env_value(env, "GA_REPORT_MONTHS", "3") or "3")
    windows = parse_windows(args.include_short_windows or env_value(env, "GA_INCLUDE_SHORT_WINDOWS", "7,28") or "7,28")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else subtract_months(end_date, months)

    output = Path(args.output or env_value(env, "GA_REPORT_OUTPUT", f"ga-monitor-{property_id}-{end_date.isoformat()}.md") or "")
    json_dir_value = args.json_dir or env_value(env, "GA_JSON_DIR")
    json_dir = Path(json_dir_value) if json_dir_value else None

    # Check for Service Account Authentication
    sa_creds = resolve_service_account_credentials(args.service_account, env)

    if sa_creds and not args.force_cli:
        print("[*] Using Native GA4 Data API REST Engine via Service Account...")
        try:
            token = get_rest_access_token(sa_creds)
            print("[+] Service Account access token acquired successfully.")
        except Exception as e:
            print(f"[!] Service account auth error: {e}", file=sys.stderr)
            return 1

        results = {
            "realtime": run_ga_rest("realtime", property_id, token, "realtime", ["activeUsers"], None, None, None, None, json_dir),
            "trend": run_ga_rest("trend", property_id, token, "report", DEFAULT_METRICS, ["date"], start_date, end_date, filter_path, json_dir),
            "sources": run_ga_rest("sources", property_id, token, "report", DEFAULT_METRICS, ["sessionSourceMedium"], start_date, end_date, filter_path, json_dir),
            "pages": run_ga_rest("pages", property_id, token, "report", DEFAULT_METRICS, ["pagePath"], start_date, end_date, filter_path, json_dir),
            "urls": run_ga_rest("urls", property_id, token, "report", DEFAULT_METRICS, ["pageLocation"], start_date, end_date, filter_path, json_dir),
            "events": run_ga_rest("events", property_id, token, "report", DEFAULT_METRICS, ["eventName"], start_date, end_date, filter_path, json_dir),
        }
    else:
        # Fallback to CLI
        ga_bin = args.ga_bin or env_value(env, "GA_CLI_BIN", "ga") or "ga"
        if shutil.which(ga_bin) is None:
            print(
                f"[!] Cannot find GA CLI binary `{ga_bin}` and no Service Account credentials found.\n"
                "Please configure GA4_SERVICE_ACCOUNT_KEY in .env or install google-analytics-cli.",
                file=sys.stderr,
            )
            return 127

        results = {
            "realtime": run_ga("realtime", command_realtime(ga_bin, property_id), json_dir, env),
            "trend": run_ga("trend", command_report(ga_bin, property_id, DEFAULT_METRICS, ["date"], start_date, end_date), json_dir, env),
            "sources": run_ga("sources", command_report(ga_bin, property_id, DEFAULT_METRICS, ["sessionSourceMedium"], start_date, end_date), json_dir, env),
            "pages": run_ga("pages", command_report(ga_bin, property_id, DEFAULT_METRICS, ["pagePath"], start_date, end_date), json_dir, env),
            "urls": run_ga("urls", command_report(ga_bin, property_id, DEFAULT_METRICS, ["pageLocation"], start_date, end_date), json_dir, env),
            "events": run_ga("events", command_report(ga_bin, property_id, DEFAULT_METRICS, ["eventName"], start_date, end_date), json_dir, env),
        }

    show_property_id = truthy(env_value(env, "GA_REPORT_SHOW_PROPERTY_ID", "false"))
    report = build_report(property_id, site_name, start_date, end_date, windows, results, show_property_id, filter_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"[+] Successfully generated GA monitor report: {output}")
    return 1 if any(result.returncode != 0 for result in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
