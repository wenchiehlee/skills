#!/usr/bin/env python3
"""Run the same page files serially through Baidu and Paddle, saving paired results."""
import argparse
import json
import statistics
import time
from pathlib import Path

from ocr_client import transcribe_document_to_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path, help="Same page images or one-page PDFs for both engines")
    parser.add_argument("--out", type=Path, default=Path("ocr-benchmark"))
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--app-name", default="ocr-engine-benchmark")
    parser.add_argument("--first-engine", choices=("baidu", "paddle"), default="baidu",
                        help="Run this engine's full batch first; swap order on repeat runs")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    jsonl = args.out / "timings.jsonl"
    jsonl.write_text("", encoding="utf-8")
    engines = (args.first_engine, "paddle" if args.first_engine == "baidu" else "baidu")
    for engine in engines:
        for index, path in enumerate(args.files):
            started = time.monotonic()
            record = {"file": path.name, "engine": engine, "run_order": index + 1,
                      "cold_or_warm": "first-request" if index == 0 else "warm"}
            try:
                result = transcribe_document_to_markdown(
                    path, dpi=args.dpi, engine=engine, return_metadata=True,
                    app_name=args.app_name)
                record.update(result)
                (args.out / f"{path.stem}.{engine}.md").write_text(result["markdown"], encoding="utf-8")
                record["success"] = True
            except Exception as exc:
                record.update(success=False, error_type=type(exc).__name__, error=str(exc))
            record["client_elapsed_s"] = round(time.monotonic() - started, 3)
            records.append(record)
            with jsonl.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(json.dumps({k: record.get(k) for k in
                              ("file", "engine", "success", "client_elapsed_s", "timings", "error")},
                             ensure_ascii=False))
    for engine in ("baidu", "paddle"):
        warm = [r["client_elapsed_s"] for r in records
                if r["engine"] == engine and r.get("success") and r["cold_or_warm"] == "warm"]
        if warm:
            p95 = sorted(warm)[min(len(warm) - 1, int(0.95 * len(warm)))]
            infer = [r["timings"]["inference_s"] for r in records
                     if r["engine"] == engine and r.get("success")
                     and r["cold_or_warm"] == "warm" and "inference_s" in r.get("timings", {})]
            inference_median = statistics.median(infer) if infer else float("nan")
            print(f"{engine} warm client median={statistics.median(warm):.3f}s p95={p95:.3f}s; "
                  f"model inference median={inference_median:.3f}s; n={len(warm)}")
    print(f"Detailed timings: {jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
