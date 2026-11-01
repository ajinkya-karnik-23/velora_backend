"""The testing phases a control moves through, and the fixed rules for each.

A control attached to a matrix-sampled cycle is tested in phases, in order:
design effectiveness (DE), operating effectiveness (OE), roll forward (RF)
and — for annual controls only — year end (YE), which follows RF and is sized
from the matrix's YE column (one sample for an annual control). A phase that fails
is remediated (RM) before the control moves on: the RM round is sized from the
matrix's RM column and tested on fresh samples from the failed phase's window.

These rules are global. Nothing here varies by control.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

DE, OE, RF, YE, RM = "DE", "OE", "RF", "YE", "RM"

PHASE_NAMES = {
    DE: "Design effectiveness",
    OE: "Operating effectiveness",
    RF: "Roll forward",
    YE: "Year end",
    RM: "Remediation",
}

# The order a cycle moves through its phases. Every control attached to a
# cycle moves in step: a phase opens only once every control that tests an
# earlier phase has cleared it (see PhaseService.cycle_phase).
CYCLE_ORDER = [DE, OE, RF, YE]

# Design effectiveness always tests exactly one sample, whatever the control.
DE_SAMPLE_SIZE = 1

# Where each phase's evidence must fall: the client's testing calendar for the
# FY2026 cycle — DE in May, OE in September–October, RF in December and YE
# (the year's close) the following January. The supporting documents date
# from January to July 2025; the demo calendar (demo_calendar.py) places them
# on these windows. A remediation round draws from the window of the phase it
# remediates.
EVIDENCE_WINDOWS: dict[str, tuple[date, date]] = {
    DE: (date(2026, 5, 1), date(2026, 5, 31)),
    OE: (date(2026, 9, 1), date(2026, 10, 31)),
    RF: (date(2026, 12, 1), date(2026, 12, 31)),
    YE: (date(2027, 1, 1), date(2027, 1, 31)),
}
PERIOD_UNDER_REVIEW = (date(2026, 5, 1), date(2027, 1, 31))

# When each phase is tested, on the same calendar: (first month, last month),
# each as (years after the cycle's start year, month).
TESTING_CALENDAR: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    DE: ((0, 5), (0, 5)),
    OE: ((0, 9), (0, 10)),
    RF: ((0, 12), (0, 12)),
    YE: ((1, 1), (1, 1)),
}


def is_annual(frequency: str | None) -> bool:
    return (frequency or "").strip().lower() in ("annual", "annually", "yearly")


def phase_path(frequency: str | None) -> list[str]:
    """The phases a control passes through, in order."""
    return [DE, OE, RF, YE] if is_annual(frequency) else [DE, OE, RF]


def planned_window(phase: str, start: int, due: int) -> tuple[int, int]:
    """(start, end) epoch seconds of a phase's planned testing months, in the
    year the cycle starts (YE: the year after). `due` is kept for callers.

    Both ends sit at midday UTC on the first and last day, so the dates read
    the same in any timezone the screens show them in."""
    year = datetime.fromtimestamp(start, tz=UTC).year
    (y0, m0), (y1, m1) = TESTING_CALENDAR[phase]
    first = datetime(year + y0, m0, 1, 12, tzinfo=UTC)
    after = datetime(year + y1 + m1 // 12, m1 % 12 + 1, 1, 12, tzinfo=UTC)
    return int(first.timestamp()), int((after - timedelta(days=1)).timestamp())
