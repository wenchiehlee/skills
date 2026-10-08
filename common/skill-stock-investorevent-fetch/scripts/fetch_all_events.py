"""Run selected investor-event producers from the consuming repository root."""

import argparse
import importlib
import sys
from pathlib import Path


FETCHERS = {
    "crashes": ("fetch_historical_crashes", "generate_historical_crashes"),
    "stock": ("fetch_stock_events", "generate_stock_events"),
    "ai": ("fetch_ai_events", "generate_ai_events"),
    "nvidia": ("fetch_nvidia_events", "generate_nvidia_events"),
    "earnings": ("fetch_upcoming_earnings", "generate_upcoming_earnings"),
    "dividends": ("fetch_dividends_announce", "main"),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="*", metavar="EVENT",
                        help="Select: " + ", ".join(FETCHERS) + "; default: all six")
    args = parser.parse_args(argv)
    keys = args.events or list(FETCHERS)
    invalid = [key for key in keys if key not in FETCHERS]
    if invalid:
        parser.error("Unknown event(s): " + ", ".join(invalid))
    scripts = str(Path(__file__).resolve().parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    for key in keys:
        module, function = FETCHERS[key]
        print(f"Running {key}")
        getattr(importlib.import_module(module), function)()


if __name__ == "__main__":
    main()
