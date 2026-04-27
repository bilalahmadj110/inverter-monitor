"""Pure-function tests for fesco_bill: cycle boundaries, aggregation,
forecast, protected-status detection, flip prediction."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

import fesco_bill


# -------------------------- compute_cycle_boundaries --------------------------

def _cfg(**overrides):
    base = {
        "reading_day_of_month": 26,
        "weekend_rolls_to_monday": True,
    }
    base.update(overrides)
    return base


def test_boundaries_weekday_no_rollover(tmp_db):
    # 26 Mar 2026 = Thursday, no rollover. Today inside the cycle.
    today = date(2026, 3, 15)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert end == date(2026, 3, 26)
    # Previous reading: 26 Feb 2026 = Thursday. Start = 27 Feb.
    assert start == date(2026, 2, 27)


def test_boundaries_today_after_reading_day_rolls_to_next_month(tmp_db):
    # Today = 27 Mar (after the 26 Mar reading) → next cycle ends 26 Apr.
    today = date(2026, 3, 27)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert end == date(2026, 4, 27)  # 26 Apr 2026 is Sunday → Mon 27
    assert start == date(2026, 3, 27)


def test_boundaries_saturday_rolls_to_monday(tmp_db):
    # Find a month where the 26th is Saturday: 26 Sep 2026 is Saturday.
    today = date(2026, 9, 15)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert end == date(2026, 9, 28)  # Sat → Mon (+2)


def test_boundaries_sunday_rolls_to_monday(tmp_db):
    # 26 Apr 2026 is Sunday.
    today = date(2026, 4, 15)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert end == date(2026, 4, 27)  # Sun → Mon (+1)


def test_boundaries_target_31_clamps_to_last_day(tmp_db):
    # reading_day_of_month=31 in February (non-leap) → clamp to Feb 28.
    today = date(2027, 2, 15)
    start, end = fesco_bill.compute_cycle_boundaries(
        today, _cfg(reading_day_of_month=31), tmp_db
    )
    # 28 Feb 2027 is Sunday → Mon 1 Mar.
    assert end == date(2027, 3, 1)
    # Previous reading: clamp 31 in Jan → Jan 31. Jan 31 2027 is Sunday → Mon Feb 1.
    # Start = day after = Feb 2.
    assert start == date(2027, 2, 2)
    # And the cycle must not be inverted.
    assert start <= end


def test_boundaries_year_boundary_dec_to_jan(tmp_db):
    # 26 Dec 2026 is Saturday → Mon 28 Dec. Today before that → cycle ends Dec 28.
    today = date(2026, 12, 15)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert end == date(2026, 12, 28)
    # Previous reading: 26 Nov 2026 = Thursday, no roll. Start = 27 Nov.
    assert start == date(2026, 11, 27)

    # Today after 28 Dec → next cycle ends 26 Jan 2027 (Tuesday, no roll).
    today2 = date(2026, 12, 30)
    start2, end2 = fesco_bill.compute_cycle_boundaries(today2, _cfg(), tmp_db)
    assert end2 == date(2027, 1, 26)
    # Previous = 26 Dec → Mon 28 Dec. Start = 29 Dec.
    assert start2 == date(2026, 12, 29)


def test_boundaries_uses_last_closed_cycle_when_present(tmp_db):
    # If a closed cycle's end_date is later than the rule-derived prev reading,
    # use that as the boundary (handles user-overridden reading dates).
    with sqlite3.connect(tmp_db) as conn:
        conn.execute('''
            CREATE TABLE billing_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_label TEXT NOT NULL UNIQUE,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL,
                units_estimated REAL, units_actual INTEGER,
                bill_amount_estimated REAL, bill_amount_actual REAL,
                payment_amount REAL, fpa_per_unit_actual REAL,
                notes TEXT, updated_at INTEGER NOT NULL
            )
        ''')
        # User said the actual Feb-Mar reading was on 28 Feb, not the rule's 26.
        conn.execute(
            '''INSERT INTO billing_cycles
               (cycle_label, start_date, end_date, status, updated_at)
               VALUES ('Feb26', '2026-01-27', '2026-02-28', 'closed', 0)''',
        )
        conn.commit()
    today = date(2026, 3, 15)
    start, end = fesco_bill.compute_cycle_boundaries(today, _cfg(), tmp_db)
    assert start == date(2026, 3, 1)  # day after 28 Feb
    assert end == date(2026, 3, 26)


# -------------------------- aggregate_cycle --------------------------

def test_aggregate_cycle_sums_daily_stats_kwh(tmp_db, seed_daily):
    # Seed 5 daily rows in Wh; sum should come back in kWh.
    seed_daily("2026-03-25", solar_wh=10000, grid_wh=2000, load_wh=11000)  # outside (before)
    seed_daily("2026-03-27", solar_wh=8000,  grid_wh=3000, load_wh=10000)
    seed_daily("2026-03-28", solar_wh=9000,  grid_wh=2500, load_wh=10500)
    seed_daily("2026-04-01", solar_wh=7000,  grid_wh=4000, load_wh=10000)
    seed_daily("2026-04-26", solar_wh=6000,  grid_wh=5000, load_wh=10000)
    seed_daily("2026-04-27", solar_wh=5000,  grid_wh=6000, load_wh=10000)  # outside (after)

    result = fesco_bill.aggregate_cycle(date(2026, 3, 27), date(2026, 4, 26), tmp_db)
    assert result["solar_kwh"] == pytest.approx(30.0)   # 8+9+7+6
    assert result["grid_kwh"]  == pytest.approx(14.5)   # 3+2.5+4+5
    assert result["load_kwh"]  == pytest.approx(40.5)   # 10+10.5+10+10


def test_aggregate_cycle_empty_range_returns_zeros(tmp_db):
    result = fesco_bill.aggregate_cycle(date(2026, 1, 1), date(2026, 1, 31), tmp_db)
    assert result == {"solar_kwh": 0.0, "grid_kwh": 0.0, "load_kwh": 0.0}


def test_aggregate_cycle_inclusive_bounds(tmp_db, seed_daily):
    seed_daily("2026-03-27", solar_wh=1000, grid_wh=1000, load_wh=1000)
    seed_daily("2026-04-26", solar_wh=1000, grid_wh=1000, load_wh=1000)
    # Start and end days both included.
    result = fesco_bill.aggregate_cycle(date(2026, 3, 27), date(2026, 4, 26), tmp_db)
    assert result["solar_kwh"] == pytest.approx(2.0)
