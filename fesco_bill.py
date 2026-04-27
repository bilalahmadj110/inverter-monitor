"""Pure functions for FESCO billing-cycle math.

Boundaries, daily-stats aggregation, run-rate forecast, NEPRA Protected-status
detection, and forward flip prediction. Everything is deterministic given its
inputs — the only side effect is the SQL read inside aggregate_cycle and the
optional last-closed-cycle lookup inside compute_cycle_boundaries.

This module never writes. fesco_cycles.CycleStore handles persistence.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date, timedelta
from typing import Any

import lesco_tariff


# Number of days from reading_date to due_date on a FESCO bill.
# Verified against the Mar26 bill: reading 26 Mar → due 8 Apr = 13 days.
DUE_DATE_OFFSET_DAYS = 13

# Late-payment surcharge phases (days past due_date).
LP_PHASE_1_DAYS = 0    # Surcharge starts the day after due_date.
LP_PHASE_2_DAYS = 5    # Higher surcharge starts 5 days after due_date.
LP_PHASE_1_PERCENT = 4.0
LP_PHASE_2_PERCENT = 8.0

# Protected-status threshold (NEPRA): consumed ≤ 200 units in EVERY of the
# last 6 closed cycles.
PROTECTED_THRESHOLD_UNITS = 200
PROTECTED_WINDOW_CYCLES = 6


def _clamp_to_month_end(year: int, month: int, day: int) -> date:
    """Clamp `day` to the last day of `month` if it overflows."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _apply_weekend_rule(d: date, enabled: bool) -> date:
    """Saturday → +2 days, Sunday → +1 day. Both land on Monday."""
    if not enabled:
        return d
    wd = d.weekday()  # 0=Mon ... 5=Sat, 6=Sun
    if wd == 5:
        return d + timedelta(days=2)
    if wd == 6:
        return d + timedelta(days=1)
    return d


def _next_month(d: date) -> date:
    """First day of the next month."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _prev_month(d: date) -> date:
    """First day of the previous month."""
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _last_closed_end_date(db_path: str) -> date | None:
    """Most recent end_date among closed cycles, or None.

    Tolerates whitespace and an ISO-8601 time suffix (`YYYY-MM-DDTHH:MM:SS`).
    A row whose end_date is malformed will raise — silent fallback would
    mask data corruption with a plausible-looking wrong answer.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT end_date FROM billing_cycles "
                "WHERE status = 'closed' ORDER BY end_date DESC LIMIT 1"
            ).fetchone()
    except sqlite3.OperationalError:
        # billing_cycles table doesn't exist yet (fresh install).
        return None
    if not row or not row[0]:
        return None
    raw = row[0].strip().split("T")[0]
    return date.fromisoformat(raw)


def compute_cycle_boundaries(
    today: date, cfg: dict[str, Any], db_path: str
) -> tuple[date, date]:
    """Return (start_date, end_date) for the cycle containing `today`.

    end_date = next reading-day on or after today (clamped to month-end,
               weekend-adjusted if the cfg flag is on).
    start_date = day after the previous closed cycle's end_date if one
                 exists, else day after the rule-derived previous reading.
    """
    target_day = int(cfg.get("reading_day_of_month", 26) or 26)
    weekend = bool(cfg.get("weekend_rolls_to_monday", True))

    # Step 1: walk forward by month until candidate >= today.
    iter_anchor = date(today.year, today.month, 1)
    while True:
        candidate = _clamp_to_month_end(iter_anchor.year, iter_anchor.month, target_day)
        candidate = _apply_weekend_rule(candidate, weekend)
        if candidate >= today:
            end = candidate
            break
        iter_anchor = _next_month(iter_anchor)

    # Step 2: prefer a closed cycle's end_date if it predates `end`.
    last_closed = _last_closed_end_date(db_path)
    if last_closed is not None and last_closed < end:
        return last_closed + timedelta(days=1), end

    # Fallback: rule-derived previous reading. Walk back from the *unrolled*
    # month anchor (iter_anchor), not from `end` — `end` may have rolled into
    # the next month via the weekend rule, which would give a wrong previous.
    prev_anchor = _prev_month(iter_anchor)
    prev_candidate = _clamp_to_month_end(prev_anchor.year, prev_anchor.month, target_day)
    prev_candidate = _apply_weekend_rule(prev_candidate, weekend)
    start = prev_candidate + timedelta(days=1)
    assert start <= end, f"inverted cycle: {start} > {end}"
    return start, end


def aggregate_cycle(start: date, end: date, db_path: str) -> dict[str, float]:
    """Sum daily_stats energy fields between start and end (inclusive).
    Returns kWh values (daily_stats stores Wh)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            '''
            SELECT
                COALESCE(SUM(solar_energy), 0) AS solar_wh,
                COALESCE(SUM(grid_energy),  0) AS grid_wh,
                COALESCE(SUM(load_energy),  0) AS load_wh
            FROM daily_stats
            WHERE date BETWEEN ? AND ?
            ''',
            (start.isoformat(), end.isoformat()),
        ).fetchone()
    return {
        "solar_kwh": (row["solar_wh"] or 0) / 1000.0,
        "grid_kwh":  (row["grid_wh"]  or 0) / 1000.0,
        "load_kwh":  (row["load_wh"]  or 0) / 1000.0,
    }
