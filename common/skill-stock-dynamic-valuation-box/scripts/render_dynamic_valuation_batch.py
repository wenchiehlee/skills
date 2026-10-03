"""Render dynamic valuation charts for every numeric company JSON ticker.

The per-symbol renderer remains the source of truth.  This wrapper only
orchestrates it: it skips complete artifacts, rotates the configured FinMind
tokens across workers, and writes a retryable failure report without making a
failed company page look complete.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _load_local_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_local_dotenv()


ARTIFACT_SUFFIXES = ("_dynamic_valuation_box_3y.png", "_dynamic_valuation_box_3y.svg", "_dynamic_valuation_box_3y.csv")


def _symbols(json_dir: Path) -> tuple[list[str], dict[str, str]]:
    symbols: set[str] = set()
    names: dict[str, str] = {}
    for path in sorted(json_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ticker = str(record.get("ticker", "")).strip()
        if ticker.isdigit():
            symbol = ticker.zfill(4)
            symbols.add(symbol)
            names[symbol] = str(record.get("company_name", "")).strip()
    return sorted(symbols), names


SKILL_METADATA_PATH = Path(__file__).resolve().parents[1] / "metadata.json"
try:
    _skill_metadata = json.loads(SKILL_METADATA_PATH.read_text(encoding="utf-8"))
    CHART_MARKER = f"chart-version: {_skill_metadata['name']}@{_skill_metadata['version']}"
except (OSError, ValueError, KeyError):
    CHART_MARKER = "chart-version: skill-stock-dynamic-valuation-box@unknown"


def _complete(output_dir: Path, symbol: str) -> bool:
    artifacts = [output_dir / f"{symbol}{suffix}" for suffix in ARTIFACT_SUFFIXES]
    if not all(path.is_file() for path in artifacts):
        return False
    try:
        svg_text = artifacts[1].read_text(encoding="utf-8")
        csv_text = artifacts[2].read_text(encoding="utf-8")
        svg_ok = CHART_MARKER in svg_text and "Updated: " in svg_text
        csv_ok = CHART_MARKER in csv_text and "Updated: " in csv_text
        png_ok = False
        try:
            from PIL import Image
            with Image.open(artifacts[0]) as image:
                png_ok = (
                    image.info.get("ChartVersion", "") == CHART_MARKER.removeprefix("chart-version: ")
                    and bool(image.info.get("Updated", ""))
                )
        except (ImportError, OSError):
            pass
        return svg_ok and csv_ok and png_ok
    except (OSError, UnicodeDecodeError):
        return False


def _quota_remaining(token: str) -> int:
    try:
        response = requests.get(
            "https://api.web.finmindtrade.com/v2/user_info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        body = response.json()
        limit = int(body.get("api_request_limit", 0) or 0)
        used = int(body.get("user_count", 0) or 0)
        return max(limit - used, 0) if limit > 0 else 0
    except (requests.RequestException, ValueError, TypeError):
        return 0


def _run_one(
    symbol: str,
    company_name: str,
    token: str,
    renderer: Path,
    output_dir: Path,
    analyzer_revenue: str,
    finmind_revenue: str | None,
    financial_ratio: str | None,
    yahoo_consensus: str | None,
    factset_report: str | None,
    require_forward_eps: bool,
    years: int,
    end_date: str | None,
) -> tuple[str, bool, str]:
    env = os.environ.copy()
    # Each child must see only its assigned token.  If the parent environment
    # exposes the whole token pool, the renderer would rotate across all tokens
    # inside every worker and defeat the batch-level quota allocation.
    token_env_names = [
        "FINMIND_TOKEN", "FINMIND_API_TOKEN",
        *(f"FINMIND_TOKEN{index}" for index in range(1, 21)),
        "FINDMIND_GMAIL_TOKEN", *(f"FINDMIND_GMAIL_TOKEN{index}" for index in range(1, 21)),
    ]
    for name in token_env_names:
        env[name] = ""
    if token:
        env["FINMIND_TOKEN"] = token
    command = [
        sys.executable,
        str(renderer),
        "--symbols",
        symbol,
        "--company-name",
        company_name,
        "--years",
        str(years),
        "--output-dir",
        str(output_dir),
        "--analyzer-revenue-csv",
        analyzer_revenue,
    ]
    if finmind_revenue:
        command.extend(["--finmind-revenue-csv", finmind_revenue])
    if financial_ratio:
        command.extend(["--finmind-financial-ratio-csv", financial_ratio])
    if yahoo_consensus:
        command.extend(["--yahoo-consensus-csv", yahoo_consensus])
    if factset_report:
        command.extend(["--factset-report-csv", factset_report])
    if require_forward_eps:
        command.append("--require-forward-eps")
    if end_date:
        command.extend(["--end-date", end_date])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, env=env)
    except subprocess.TimeoutExpired:
        return symbol, False, "timeout after 300 seconds"
    if result.returncode == 0 and _complete(output_dir, symbol):
        return symbol, True, ""
    error = (result.stderr or result.stdout or f"renderer exited {result.returncode}").strip()
    # Never put a credential into the persisted failure report.
    for candidate in (token, os.environ.get("FINMIND_TOKEN", ""), os.environ.get("FINMIND_API_TOKEN", "")):
        if candidate:
            error = error.replace(candidate, "<redacted-token>")
    return symbol, False, error[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-dir", default="data/enrichment_all")
    parser.add_argument("--renderer", help="Per-symbol renderer; defaults to this skill's renderer")
    parser.add_argument("--output-dir", default="output/dynamic_valuation_box")
    parser.add_argument("--analyzer-revenue-csv", required=True)
    parser.add_argument("--finmind-revenue-csv")
    parser.add_argument("--finmind-financial-ratio-csv")
    parser.add_argument("--yahoo-consensus-csv")
    parser.add_argument("--factset-report-csv")
    parser.add_argument("--require-forward-eps", action="store_true")
    parser.add_argument("--failure-log", default="output/dynamic_valuation_box_failures.tsv")
    parser.add_argument("--deferred-log", default="output/dynamic_valuation_box_deferred_quota.tsv")
    parser.add_argument("--queue-state", default="output/dynamic_valuation_box_queue_state.json")
    parser.add_argument("--token-env-prefix", default="FINMIND_TOKEN")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--years", type=int, choices=(2, 3, 4, 5), default=3)
    parser.add_argument("--end-date")
    parser.add_argument("--force", action="store_true")
    # Kept for CLI compatibility; quota exhaustion is now fail-fast.
    parser.add_argument("--wait-for-quota", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--quota-wait-hours", type=float, default=0.0, help=argparse.SUPPRESS)
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = Path(args.renderer) if args.renderer else Path(__file__).with_name("render_dynamic_valuation_box.py")
    symbols, company_names = _symbols(json_dir)
    pending = [symbol for symbol in symbols if args.force or not _complete(output_dir, symbol)]

    state_path = Path(args.queue_state)
    state = {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    next_symbol = str(state.get("next_symbol", "")).strip()
    if pending and next_symbol in pending:
        pivot = pending.index(next_symbol)
        pending = pending[pivot:] + pending[:pivot]

    token_names = [f"{args.token_env_prefix}{index}" for index in range(1, 21)]
    token_names += [
        "FINMIND_TOKEN", "FINMIND_API_TOKEN",
        *(f"FINDMIND_GMAIL_TOKEN{index}" for index in range(1, 21)),
        "FINDMIND_GMAIL_TOKEN",
    ]
    configured_tokens = []
    for name in token_names:
        token = os.environ.get(name, "")
        if token and token not in configured_tokens:
            configured_tokens.append(token)

    def active_tokens() -> list[str]:
        return [token for token in configured_tokens if _quota_remaining(token) > 0]

    tokens = active_tokens() if configured_tokens else []
    if configured_tokens:
        print(f"quota_preflight active={len(tokens)} exhausted={len(configured_tokens) - len(tokens)}")
    if configured_tokens and not tokens:
        print("All configured FinMind tokens are exhausted; deferring the queue.", flush=True)
    if not tokens:
        tokens = [""]

    workers = max(1, min(args.workers, len(tokens), len(pending) or 1))
    print(f"symbols={len(symbols)} complete={len(symbols) - len(pending)} pending={len(pending)} workers={workers}")

    failures: dict[str, str] = {}
    deferred: list[tuple[str, str]] = []
    succeeded = 0
    attempted: list[str] = []
    cursor = 0
    while cursor < len(pending):
        chunk = pending[cursor:cursor + workers]
        with ThreadPoolExecutor(max_workers=len(chunk)) as pool:
            futures = {
                pool.submit(
                    _run_one,
                    symbol,
                    company_names.get(symbol, ""),
                    tokens[(cursor + index) % len(tokens)],
                    renderer,
                    output_dir,
                    args.analyzer_revenue_csv,
                    args.finmind_revenue_csv,
                    args.finmind_financial_ratio_csv,
                    args.yahoo_consensus_csv,
                    args.factset_report_csv,
                    args.require_forward_eps,
                    args.years,
                    args.end_date,
                ): symbol
                for index, symbol in enumerate(chunk)
            }
            quota_hit = False
            for future in as_completed(futures):
                symbol, ok, error = future.result()
                attempted.append(symbol)
                if ok:
                    succeeded += 1
                    print(f"OK {symbol}")
                    continue
                is_quota = any(term in error.lower() for term in (
                    "quota exhausted", "reach the upper limit", "payment required",
                ))
                if is_quota:
                    deferred.append((symbol, error))
                    quota_hit = True
                    print(f"DEFER {symbol}: FinMind quota", file=sys.stderr)
                else:
                    failures[symbol] = error
                    print(f"FAIL {symbol}: {error}", file=sys.stderr)
        cursor += len(chunk)
        if configured_tokens:
            live_tokens = active_tokens()
            if not live_tokens:
                if quota_hit:
                    deferred.extend((symbol, "FinMind quota exhausted; deferred to a later run") for symbol in pending[cursor:])
                break
            tokens = live_tokens
            workers = max(1, min(args.workers, len(tokens), len(pending) - cursor or 1))

    if pending:
        remaining_symbols = {symbol for symbol, _ in deferred}
        if cursor < len(pending):
            for symbol in pending[cursor:]:
                if symbol not in remaining_symbols:
                    deferred.append((symbol, "FinMind quota exhausted; deferred to a later run"))
    if pending and attempted:
        ordered_symbols = sorted(symbols)
        last = attempted[-1]
        next_index = (ordered_symbols.index(last) + 1) % len(ordered_symbols) if last in ordered_symbols else 0
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({
                "next_symbol": ordered_symbols[next_index] if ordered_symbols else "",
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "completed": succeeded,
                "deferred_quota": len(deferred),
                "failed_data": len(failures),
            }, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8"
        )

    failure_path = Path(args.failure_log)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        "symbol" + chr(9) + "error" + chr(10) + chr(10).join(
            f"{symbol}" + chr(9) + error.replace(chr(9), " ")
            for symbol, error in sorted(failures.items())
        ) + (chr(10) if failures else ""),
        encoding="utf-8",
    )
    deferred_path = Path(args.deferred_log)
    deferred_path.parent.mkdir(parents=True, exist_ok=True)
    deferred_path.write_text(
        "symbol" + chr(9) + "reason" + chr(10) + chr(10).join(
            f"{symbol}" + chr(9) + error.replace(chr(9), " ")
            for symbol, error in sorted(set(deferred))
        ) + (chr(10) if deferred else ""),
        encoding="utf-8",
    )
    summary = {
        "symbols": len(symbols),
        "completed": succeeded,
        "deferred_quota": len(deferred),
        "failed_data": len(failures),
        "queue_state": state_path.as_posix(),
    }
    Path("output/dynamic_valuation_box_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8"
    )
    print(
        f"completed={succeeded} deferred_quota={len(deferred)} "
        f"failed_data={len(failures)} failure_log={failure_path} deferred_log={deferred_path}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
