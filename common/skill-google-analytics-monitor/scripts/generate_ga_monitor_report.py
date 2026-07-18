#!/usr/bin/env python3
"""Generate a GA4 monitoring Markdown report via google-analytics-cli."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import subprocess
import sys
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
    if abs(value - int(value)) < 0.0001:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def metric_summary(rows: list[dict[str, str]], metrics: list[str] = DEFAULT_METRICS) -> dict[str, float]:
    return {metric: total(rows, metric) for metric in metrics}


def percent_change(current: float, previous: float) -> str:
    if previous == 0:
        return "n/a" if current == 0 else "new activity"
    return f"{((current - previous) / previous * 100):+.1f}%"


def parse_ga_date(raw: str) -> date | None:
    raw = str(raw)
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def rows_between(rows: list[dict[str, str]], start: date, end: date) -> list[dict[str, str]]:
    selected = []
    for row in rows:
        parsed = parse_ga_date(row.get("date", ""))
        if parsed and start <= parsed <= end:
            selected.append(row)
    return selected


def markdown_table(headers: list[str], rows: list[list[str]], limit: int | None = None) -> str:
    shown = rows[:limit] if limit else rows
    if not shown:
        return "_No data returned._"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in shown)
    return "\n".join(lines)


def dimension_table(rows: list[dict[str, str]], dimension: str, limit: int = 15, sort_metric: str = "sessions", label: str = "Dimension") -> str:
    sorted_rows = sorted(rows, key=lambda row: number(row.get(sort_metric)), reverse=True)
    table_rows = [
        [
            row.get(dimension, "(not set)"),
            format_number(number(row.get("sessions"))),
            format_number(number(row.get("totalUsers"))),
            format_number(number(row.get("screenPageViews"))),
            format_number(number(row.get("eventCount"))),
        ]
        for row in sorted_rows[:limit]
    ]
    return markdown_table([label, "Sessions", "Users", "Views", "Events"], table_rows)


def monthly_table(rows: list[dict[str, str]]) -> str:
    buckets: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        parsed = parse_ga_date(row.get("date", ""))
        if parsed:
            buckets.setdefault(parsed.strftime("%Y-%m"), []).append(row)
    table_rows = []
    for month in sorted(buckets):
        summary = metric_summary(buckets[month])
        table_rows.append([month, format_number(summary["sessions"]), format_number(summary["totalUsers"]), format_number(summary["screenPageViews"]), format_number(summary["eventCount"])])
    return markdown_table(["Month", "Sessions", "Users", "Views", "Events"], table_rows)


def daily_tail_table(rows: list[dict[str, str]], limit: int = 14) -> str:
    sorted_rows = sorted(rows, key=lambda row: parse_ga_date(row.get("date", "")) or date.min)
    table_rows = [
        [row.get("date", ""), format_number(number(row.get("sessions"))), format_number(number(row.get("totalUsers"))), format_number(number(row.get("screenPageViews"))), format_number(number(row.get("eventCount")))]
        for row in sorted_rows[-limit:]
    ]
    return markdown_table(["Date", "Sessions", "Users", "Views", "Events"], table_rows)


def realtime_active_users(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No realtime data returned."
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
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def masked_property_id(property_id: str, show: bool = False) -> str:
    if show:
        return property_id
    if len(property_id) <= 4:
        return "hidden"
    return "hidden-" + property_id[-4:]


def display_command(command: list[str], property_id: str, show_property_id: bool) -> list[str]:
    shown = list(command)
    for idx, part in enumerate(shown[:-1]):
        if part == "--property-id":
            shown[idx + 1] = masked_property_id(property_id, show_property_id)
    return shown


def build_report(
    property_id: str,
    site_name: str,
    start_date: date,
    end_date: date,
    windows: list[int],
    results: dict[str, CommandResult],
    show_property_id: bool = False,
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
    lines = [
        "---",
        "title: GA4 Website Monitoring Report",
        "report_type: ga4_monitor",
        "update_frequency: daily",
        f"site: {yaml_scalar(site_name or 'n/a')}",
        f"property_id: {yaml_scalar(public_property_id)}",
        f"historical_window_start: {yaml_scalar(start_date.isoformat())}",
        f"historical_window_end: {yaml_scalar(end_date.isoformat())}",
        f"generated_at: {yaml_scalar(generated_at)}",
        f"產生時間: {yaml_scalar(generated_at)}",
        "---",
        "",
        "# GA4 Website Monitoring Report",
        "",
        f"- Site: {site_name or 'n/a'}",
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
    for window in windows:
        current_start = end_date - timedelta(days=window - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=window - 1)
        current = metric_summary(rows_between(trend_rows, current_start, end_date))
        previous = metric_summary(rows_between(trend_rows, previous_start, previous_end))
        lines.extend([
            f"### Last {window} Days",
            "",
            markdown_table(["Metric", "Current", "Previous", "Change"], [[metric, format_number(current[metric]), format_number(previous[metric]), percent_change(current[metric], previous[metric])] for metric in DEFAULT_METRICS]),
            "",
        ])
    lines.extend([
        "## 3-Month Trend",
        "",
        "### Monthly Summary",
        "",
        monthly_table(trend_rows),
        "",
        "### Recent Daily Detail",
        "",
        daily_tail_table(trend_rows),
        "",
        "## Traffic Sources",
        "",
        dimension_table(source_rows, "sessionSourceMedium"),
        "",
        "## Top 10 URLs",
        "",
        dimension_table(url_rows, "pageLocation", limit=10, sort_metric="screenPageViews", label="URL"),
        "",
        "## Top Pages",
        "",
        dimension_table(page_rows, "pagePath", label="Page path"),
        "",
        "## Events",
        "",
        dimension_table(event_rows, "eventName"),
        "",
        "## Anomaly Observations",
        "",
    ])
    warnings = []
    for result in results.values():
        if result.returncode != 0:
            warnings.append(f"- `{result.name}` failed with exit code {result.returncode}: {result.stderr.strip()}")
        elif not row_dicts(result.data):
            warnings.append(f"- `{result.name}` returned no parseable rows.")
    lines.extend(warnings or ["- No command failures detected. Review short-term changes above for traffic movement."])
    lines.extend(["", "## Raw Command Audit", ""])
    for result in results.values():
        lines.extend([f"### {result.name}", "", "```bash", " ".join(display_command(result.command, property_id, show_property_id)), "```", "", f"- Exit code: {result.returncode}"])
        if result.json_path:
            lines.append(f"- Raw JSON: `{result.json_path}`")
        if result.stderr.strip():
            lines.append(f"- stderr: `{result.stderr.strip()}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", help="Path to .env file.")
    parser.add_argument("--property-id", help="GA4 property ID. Overrides GOOGLE_ANALYTICS_KEY.")
    parser.add_argument("--site-name", help="Display name. Overrides GA_SITE_NAME.")
    parser.add_argument("--months", type=int, help="Historical window in months. Defaults to GA_REPORT_MONTHS or 3.")
    parser.add_argument("--include-short-windows", help="Comma-separated day windows. Defaults to GA_INCLUDE_SHORT_WINDOWS or 7,28.")
    parser.add_argument("--start-date", help="Explicit start date YYYY-MM-DD. Overrides --months.")
    parser.add_argument("--end-date", help="Explicit end date YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--output", help="Markdown output path. Overrides GA_REPORT_OUTPUT.")
    parser.add_argument("--json-dir", help="Optional raw JSON directory. Overrides GA_JSON_DIR.")
    parser.add_argument("--ga-bin", help="GA CLI binary path. Overrides GA_CLI_BIN.")
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
    months = args.months or int(env_value(env, "GA_REPORT_MONTHS", "3") or "3")
    windows = parse_windows(args.include_short_windows or env_value(env, "GA_INCLUDE_SHORT_WINDOWS", "7,28") or "7,28")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else date.today()
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else subtract_months(end_date, months)
    output = Path(args.output or env_value(env, "GA_REPORT_OUTPUT", f"ga-monitor-{property_id}-{end_date.isoformat()}.md") or "")
    json_dir_value = args.json_dir or env_value(env, "GA_JSON_DIR")
    json_dir = Path(json_dir_value) if json_dir_value else None
    ga_bin = args.ga_bin or env_value(env, "GA_CLI_BIN", "ga") or "ga"
    if shutil.which(ga_bin) is None:
        print(f"Cannot find GA CLI binary `{ga_bin}`. Install google-analytics-cli and ensure it is on PATH.", file=sys.stderr)
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
    report = build_report(property_id, site_name, start_date, end_date, windows, results, show_property_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output}")
    return 1 if any(result.returncode != 0 for result in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
