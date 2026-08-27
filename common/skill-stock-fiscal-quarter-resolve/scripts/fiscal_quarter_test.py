"""
fiscal_quarter_test.py — Regression cases for resolve_fiscal_quarter(), pinned to
real announcement dates (yfinance get_earnings_dates()), NVIDIA's own SEC 8-K,
and existing verified InvestorConference README rows. Gathered 2026-08-27.

Run: python fiscal_quarter_test.py
"""
from fiscal_quarter import resolve_fiscal_quarter

CASES = [
    # ticker, announce_date, expected_label, source
    ("NVDA", "2026-08-26", "FY2027 Q2", "SEC 8-K q2fy27pr.htm (period ended 2026-07-26)"),
    ("NVDA", "2026-05-20", "FY2027 Q1", "yfinance get_earnings_dates"),
    ("NVDA", "2026-02-25", "FY2026 Q4", "yfinance get_earnings_dates"),
    ("NVDA", "2025-11-19", "FY2026 Q3", "yfinance get_earnings_dates"),
    ("DELL", "2026-09-01", "FY2027 Q2", "yfinance get_earnings_dates + web search "
        "confirms this is Dell's Q2 FY2027 call, NOT Q4 as raw_event_upcoming_earnings.csv "
        "had it labeled"),
    ("DELL", "2026-05-28", "FY2027 Q1", "InvestorConference README (verified correct row)"),
    ("DELL", "2025-11-25", "FY2026 Q3", "yfinance get_earnings_dates"),
    ("DELL", "2026-02-26", "FY2026 Q4", "yfinance get_earnings_dates"),
    ("QCOM", "2026-04-29", "FY2026 Q2", "InvestorConference README (verified correct row)"),
    ("QCOM", "2026-02-04", "FY2026 Q1", "InvestorConference README (verified correct row)"),
    ("AAPL", "2026-01-29", "FY2026 Q1", "yfinance get_earnings_dates"),
    ("AAPL", "2026-04-30", "FY2026 Q2", "yfinance get_earnings_dates"),
    ("AAPL", "2026-07-30", "FY2026 Q3", "yfinance get_earnings_dates"),
    ("AAPL", "2025-10-30", "FY2025 Q4", "Apple Newsroom: \"fiscal 2025 fourth quarter\" "
        "(apple.com/newsroom/2025/10/apple-reports-fourth-quarter-results)"),
    ("MSFT", "2025-10-29", "FY2026 Q1", "Microsoft IR: \"Fiscal Year 2026 First Quarter\" "
        "(microsoft.com/en-us/investor/earnings/fy-2026-q1)"),
    ("MSFT", "2026-01-28", "FY2026 Q2", "yfinance get_earnings_dates"),
    ("MSFT", "2026-04-29", "FY2026 Q3", "yfinance get_earnings_dates"),
    ("MSFT", "2026-07-29", "FY2026 Q4", "yfinance get_earnings_dates"),
]


def main() -> int:
    failures = 0
    for ticker, date_str, expected, source in CASES:
        result = resolve_fiscal_quarter(ticker, date_str)
        ok = result["label"] == expected
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {ticker} {date_str} -> {result['label']} (expected {expected}) — {source}")
        if not ok:
            failures += 1
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
