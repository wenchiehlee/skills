#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical Taiwan MOPS quarterly financial-report filing deadline schedule.

General (non-holding) listed companies must file each quarterly report with
公開資訊觀測站 (MOPS) within a fixed window after quarter-end; the Q4 filing
is the annual report, due the following March. Financial holding companies
and banks get a short additional extension. These dates are the same ones
already encoded ad hoc as month/day checks in MOPS/.github/workflows/*.yaml;
this module is the single source of truth so every consumer (workflows,
generate_mops_health.py, update_readme_status.py) computes the same answer.

Usage as a script (prints the current filing focus quarter as JSON):

    python filing_deadlines.py
    python filing_deadlines.py --as-of 2026-09-09
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# (month, day) of the general filing deadline for each quarter's report.
# Q4's deadline falls in the following calendar year (it's the annual report).
GENERAL_DEADLINE = {
    1: (5, 15),
    2: (8, 14),
    3: (11, 14),
    4: (3, 31),
}

# Financial holding companies / banks get a short additional extension.
# (No documented extension for the Q4/annual report.)
HOLDING_DEADLINE = {
    1: (5, 30),
    2: (8, 31),
    3: (11, 29),
    4: (3, 31),
}

QUARTER_LABELS = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}


@dataclass(frozen=True)
class QuarterDeadline:
    year: int
    quarter: int
    deadline: date
    holding_deadline: date

    @property
    def label(self) -> str:
        """Matches the "<year> Q<quarter>" column headers used in
        data/reports/mops_matrix_latest.csv and the README status table."""
        return f"{self.year} {QUARTER_LABELS[self.quarter]}"


def deadline_for(year: int, quarter: int) -> QuarterDeadline:
    """Deadline for a given fiscal year/quarter's MOPS filing."""
    if quarter not in GENERAL_DEADLINE:
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    m, d = GENERAL_DEADLINE[quarter]
    hm, hd = HOLDING_DEADLINE[quarter]
    deadline_year = year + 1 if quarter == 4 else year
    return QuarterDeadline(year, quarter, date(deadline_year, m, d), date(deadline_year, hm, hd))


def all_deadlines_up_to(as_of: date, lookback_years: int = 2) -> list[QuarterDeadline]:
    """All quarter deadlines within `lookback_years` of `as_of`, sorted oldest first."""
    result = []
    for y in range(as_of.year - lookback_years, as_of.year + 1):
        for q in (1, 2, 3, 4):
            result.append(deadline_for(y, q))
    return sorted(result, key=lambda qd: qd.deadline)


def current_focus_quarter(as_of: date | None = None) -> QuarterDeadline:
    """The most recently closed reporting quarter as of `as_of`.

    "Closed" means its general filing deadline has already passed, so this
    is the quarter a health/overdue check should be measuring right now.
    """
    as_of = as_of or date.today()
    past = [qd for qd in all_deadlines_up_to(as_of) if qd.deadline <= as_of]
    if not past:
        raise ValueError(f"no filing deadline found on/before {as_of.isoformat()}")
    return past[-1]


def days_since_deadline(qd: QuarterDeadline, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    return (as_of - qd.deadline).days


def deadline_note(year: int, quarter: int, as_of: date | None = None) -> str:
    """Human-readable Notes-column text for a README quarter row."""
    as_of = as_of or date.today()
    qd = deadline_for(year, quarter)
    days = days_since_deadline(qd, as_of)
    if days < 0:
        return f"申報期限 {qd.deadline.isoformat()}（尚有 {-days} 天）"
    return f"申報期限 {qd.deadline.isoformat()}（已逾期 {days} 天）"


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="ISO date to evaluate as 'today' (default: real today)")
    args = parser.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    qd = current_focus_quarter(as_of)
    print(json.dumps({
        "as_of": as_of.isoformat(),
        "focus_year": qd.year,
        "focus_quarter": qd.quarter,
        "label": qd.label,
        "deadline": qd.deadline.isoformat(),
        "holding_deadline": qd.holding_deadline.isoformat(),
        "days_since_deadline": days_since_deadline(qd, as_of),
    }, ensure_ascii=False, indent=2))
