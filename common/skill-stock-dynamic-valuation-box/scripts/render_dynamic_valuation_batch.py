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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ARTIFACT_SUFFIXES = ("_dynamic_valuation_box_2y.png", "_dynamic_valuation_box_2y.svg", "_dynamic_valuation_box_2y.csv")


def _symbols(json_dir: Path) -> list[str]:
    symbols: set[str] = set()
    for path in sorted(json_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ticker = str(record.get("ticker", "")).strip()
        if ticker.isdigit():
            symbols.add(ticker.zfill(4))
    return sorted(symbols)


def _complete(output_dir: Path, symbol: str) -> bool:
    return all((output_dir / f"{symbol}{suffix}").is_file() for suffix in ARTIFACT_SUFFIXES)


def _run_one(
    symbol: str,
    token: str,
    renderer: Path,
    output_dir: Path,
    analyzer_revenue: str,
    years: int,
    end_date: str | None,
) -> tuple[str, bool, str]:
    env = os.environ.copy()
    command = [
        sys.executable,
        str(renderer),
        "--symbols",
        symbol,
        "--years",
        str(years),
        "--output-dir",
        str(output_dir),
        "--analyzer-revenue-csv",
        analyzer_revenue,
    ]
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
    parser.add_argument("--failure-log", default="output/dynamic_valuation_box_failures.tsv")
    parser.add_argument("--token-env-prefix", default="FINMIND_TOKEN")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--years", type=int, choices=(2, 3, 4, 5), default=2)
    parser.add_argument("--end-date")
    parser.add_argument("--force", action="store_true", help="Re-render symbols whose three artifacts already exist")
    args = parser.parse_args()

    json_dir = Path(args.json_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = Path(args.renderer) if args.renderer else Path(__file__).with_name("render_dynamic_valuation_box.py")
    symbols = _symbols(json_dir)
    pending = [symbol for symbol in symbols if args.force or not _complete(output_dir, symbol)]
    tokens = [os.environ.get(f"{args.token_env_prefix}{index}", "") for index in range(1, 7)]
    tokens = [token for token in tokens if token]
    if not tokens:
        # A tokenless run remains useful for public/demo environments.  The
        # renderer will report the actual API response instead of failing here.
        tokens = [""]
    workers = max(1, min(args.workers, len(tokens), len(pending) or 1))
    print(f"symbols={len(symbols)} complete={len(symbols) - len(pending)} pending={len(pending)} workers={workers}")

    failures: list[tuple[str, str]] = []
    succeeded = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _run_one,
                symbol,
                tokens[index % len(tokens)],
                renderer,
                output_dir,
                args.analyzer_revenue_csv,
                args.years,
                args.end_date,
            ): symbol
            for index, symbol in enumerate(pending)
        }
        for future in as_completed(futures):
            symbol, ok, error = future.result()
            if ok:
                succeeded += 1
                print(f"OK {symbol}")
            else:
                failures.append((symbol, error))
                print(f"FAIL {symbol}: {error}", file=sys.stderr)

    failure_path = Path(args.failure_log)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        "symbol\terror\n" + "\n".join(f"{symbol}\t{error.replace(chr(9), ' ')}" for symbol, error in sorted(failures)) + ("\n" if failures else ""),
        encoding="utf-8",
    )
    print(f"completed={succeeded} failed={len(failures)} failure_log={failure_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
