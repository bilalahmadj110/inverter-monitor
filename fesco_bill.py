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


_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def cycle_label_for(end: date) -> str:
    """Convert an end_date to FESCO-style 'Mar26' label."""
    return f"{_MONTH_ABBR[end.month - 1]}{end.year % 100:02d}"


def _label_minus_one_year(label: str) -> str | None:
    """'Mar26' → 'Mar25'. Returns None on parse failure."""
    if len(label) < 5:
        return None
    mon = label[:3]
    try:
        yy = int(label[3:])
    except ValueError:
        return None
    return f"{mon}{(yy - 1) % 100:02d}"


def _lookup_units_actual_by_label(db_path: str, label: str) -> int | None:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT units_actual FROM billing_cycles "
                "WHERE cycle_label = ?",
                (label,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row or row[0] is None:
        return None
    return int(row[0])


def forecast_open_cycle(
    today: date, cfg: dict[str, Any], db_path: str
) -> dict[str, Any]:
    """Run-rate forecast for the open cycle containing `today`.

    Returns:
      {
        start, end, days_elapsed, days_remaining,
        units_so_far, daily_avg_kwh, projected_units,
        forecast_bill: {...full compute_bill result with fix_charges...},
        same_month_last_year_label, same_month_last_year_units
      }
    """
    start, end = compute_cycle_boundaries(today, cfg, db_path)
    total_days = (end - start).days + 1
    elapsed_days = max(0, (today - start).days + 1)
    elapsed_days = min(elapsed_days, total_days)
    days_remaining = max(0, total_days - elapsed_days)

    energy = aggregate_cycle(start, today if today <= end else end, db_path)
    units_so_far = energy["grid_kwh"]

    if elapsed_days > 0:
        daily_avg = units_so_far / elapsed_days
        projected = units_so_far * (total_days / elapsed_days)
    else:
        daily_avg = 0.0
        projected = 0.0

    forecast_bill = lesco_tariff.compute_bill(projected, cfg)

    label = cycle_label_for(end)
    last_year_label = _label_minus_one_year(label)
    last_year_units = (
        _lookup_units_actual_by_label(db_path, last_year_label)
        if last_year_label else None
    )

    return {
        "label": label,
        "start": start,
        "end": end,
        "days_elapsed": elapsed_days,
        "days_remaining": days_remaining,
        "total_days": total_days,
        "units_so_far": round(units_so_far, 3),
        "daily_avg_kwh": round(daily_avg, 3),
        "projected_units": round(projected, 3),
        "forecast_bill": forecast_bill,
        "same_month_last_year_label": last_year_label,
        "same_month_last_year_units": last_year_units,
    }


def _cycle_units(cycle: dict[str, Any]) -> float | None:
    """Pick units_actual if present, else units_estimated. None if both missing."""
    if cycle.get("units_actual") is not None:
        return float(cycle["units_actual"])
    if cycle.get("units_estimated") is not None:
        return float(cycle["units_estimated"])
    return None


def detect_protected_status(closed_cycles: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply NEPRA rule: protected if last 6 closed cycles all <= 200 units.

    closed_cycles must be ordered oldest-first. Only entries with status='closed'
    are considered; the function picks the last 6.
    """
    closed = [c for c in closed_cycles if c.get("status", "closed") == "closed"]
    if len(closed) < PROTECTED_WINDOW_CYCLES:
        return {
            "status": "unknown",
            "reason": f"need {PROTECTED_WINDOW_CYCLES} closed cycles, have {len(closed)}",
            "window": [c["cycle_label"] for c in closed],
            "max_units_in_window": None,
            "violator_cycle": None,
        }

    window = closed[-PROTECTED_WINDOW_CYCLES:]
    units_pairs = [(c["cycle_label"], _cycle_units(c) or 0.0) for c in window]
    max_label, max_units = max(units_pairs, key=lambda p: p[1])

    if max_units <= PROTECTED_THRESHOLD_UNITS:
        return {
            "status": "protected",
            "reason": "all 6 cycles within threshold",
            "window": [c["cycle_label"] for c in window],
            "max_units_in_window": max_units,
            "violator_cycle": None,
        }
    return {
        "status": "unprotected",
        "reason": f"{max_label} = {int(max_units)} > {PROTECTED_THRESHOLD_UNITS}",
        "window": [c["cycle_label"] for c in window],
        "max_units_in_window": max_units,
        "violator_cycle": max_label,
    }


PREDICTION_HORIZON_MONTHS = 6
TRAILING_AVG_WINDOW = 3
NEXT_LABEL_PLACEHOLDER = "+{i}"  # for hypothetical future cycles


def _next_cycle_label(prev_label: str) -> str:
    """'Mar26' → 'Apr26'; 'Dec26' → 'Jan27'. Falls back to '+i' style for
    unparseable labels (used by tests that don't care about real labels)."""
    if len(prev_label) < 5:
        return prev_label + "+1"
    mon = prev_label[:3]
    try:
        yy = int(prev_label[3:])
    except ValueError:
        return prev_label + "+1"
    if mon not in _MONTH_ABBR:
        return prev_label + "+1"
    idx = _MONTH_ABBR.index(mon)
    if idx == 11:
        return f"Jan{(yy + 1) % 100:02d}"
    return f"{_MONTH_ABBR[idx + 1]}{yy:02d}"


def predict_status_flip(
    closed_cycles: list[dict[str, Any]],
    open_forecast: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Walk a forward timeline (closed + open forecast + 6 hypothetical cycles
    using trailing-3-month average) and return the first cycle where the
    rolling-6-cycle protected status differs from the current status.

    Returns: { flips_to, at_cycle, condition, horizon_end }
    """
    closed = [c for c in closed_cycles if c.get("status", "closed") == "closed"]

    timeline: list[tuple[str, float]] = [
        (c["cycle_label"], _cycle_units(c) or 0.0) for c in closed
    ]
    forecast_label = open_forecast.get("label") or "open"
    timeline.append((forecast_label, float(open_forecast.get("projected_units") or 0.0)))

    # Trailing average from the last TRAILING_AVG_WINDOW timeline entries.
    tail = timeline[-TRAILING_AVG_WINDOW:]
    if tail:
        trailing_avg = sum(u for _, u in tail) / len(tail)
    else:
        trailing_avg = 0.0

    # Append PREDICTION_HORIZON_MONTHS hypothetical cycles.
    last_label = timeline[-1][0]
    for _ in range(PREDICTION_HORIZON_MONTHS):
        last_label = _next_cycle_label(last_label)
        timeline.append((last_label, trailing_avg))

    current_status = detect_protected_status(closed)["status"]
    if current_status == "unknown":
        # With < 6 closed, the first flip happens once we accumulate 6 in timeline.
        prev_status = None
    else:
        prev_status = current_status

    # Scan from the index of the open-forecast entry onward.
    forecast_idx = len(closed)  # 0-based index of open_forecast in timeline

    for i in range(forecast_idx, len(timeline)):
        if i < PROTECTED_WINDOW_CYCLES - 1:
            continue
        window = timeline[i - PROTECTED_WINDOW_CYCLES + 1: i + 1]
        max_units = max(u for _, u in window)
        status = (
            "protected"
            if max_units <= PROTECTED_THRESHOLD_UNITS
            else "unprotected"
        )
        if prev_status is None:
            prev_status = status
            continue
        if status != prev_status:
            is_forecast_or_hypo = i >= forecast_idx
            condition = None
            if is_forecast_or_hypo and status == "protected":
                condition = (
                    f"if {timeline[i][0]} <= {PROTECTED_THRESHOLD_UNITS} units"
                )
            return {
                "flips_to": status,
                "at_cycle": timeline[i][0],
                "condition": condition,
                "horizon_end": timeline[-1][0],
            }
        prev_status = status

    return {
        "flips_to": None,
        "at_cycle": None,
        "condition": None,
        "horizon_end": timeline[-1][0],
    }
