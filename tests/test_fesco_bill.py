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


# -------------------------- forecast_open_cycle --------------------------

def test_forecast_open_cycle_run_rate(tmp_db, seed_daily):
    """At day 10 of a 30-day cycle, having used 50 kWh, projection = 150 kWh."""
    # Cycle: 27 Feb..26 Mar 2026 (28 days). Today: midpoint, 13 Mar.
    # Seed grid usage for days 1-15 of cycle (27 Feb..13 Mar).
    cycle_start = date(2026, 2, 27)
    today = date(2026, 3, 13)
    elapsed = (today - cycle_start).days + 1  # 15
    # Cycle ends 26 Mar (total = 28 days), so projection = units_so_far × 28/15.

    # Seed exactly 30 kWh of grid in the first 15 days (so projection ≈ 56).
    for i in range(elapsed):
        d = (cycle_start + timedelta(days=i)).isoformat()
        seed_daily(d, grid_wh=2000)  # 2 kWh/day

    cfg = _cfg()
    result = fesco_bill.forecast_open_cycle(today, cfg, tmp_db)
    assert result["start"] == cycle_start
    assert result["end"] == date(2026, 3, 26)
    assert result["days_elapsed"] == 15
    assert result["days_remaining"] == 13
    assert result["units_so_far"] == pytest.approx(30.0)
    # projected = 30 * 28/15 = 56.0
    assert result["projected_units"] == pytest.approx(56.0)
    # bill breakdown returned
    assert "forecast_bill" in result
    assert result["forecast_bill"]["units"] == pytest.approx(56.0)


def test_forecast_open_cycle_zero_elapsed_returns_zero_projection(tmp_db, seed_daily):
    today = date(2026, 2, 27)  # day 1 of cycle, no data yet
    cfg = _cfg()
    result = fesco_bill.forecast_open_cycle(today, cfg, tmp_db)
    assert result["units_so_far"] == 0.0
    assert result["projected_units"] == 0.0


def test_forecast_open_cycle_includes_same_month_last_year(tmp_db, seed_daily):
    """When billing_cycles has a Mar25 row, forecast surfaces its units_actual."""
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
        conn.execute(
            "INSERT INTO billing_cycles "
            "(cycle_label, start_date, end_date, status, units_actual, updated_at) "
            "VALUES ('Mar25', '2025-02-27', '2025-03-26', 'closed', 115, 0)"
        )
        conn.commit()

    today = date(2026, 3, 13)
    cfg = _cfg()
    result = fesco_bill.forecast_open_cycle(today, cfg, tmp_db)
    assert result["same_month_last_year_units"] == 115
    assert result["same_month_last_year_label"] == "Mar25"


# -------------------------- detect_protected_status --------------------------

def _make_cycle(label: str, units_actual: int | None = None,
                units_estimated: float | None = None, status: str = "closed"):
    """Test helper: build a dict shaped like a billing_cycles row."""
    return {
        "cycle_label": label,
        "status": status,
        "units_actual": units_actual,
        "units_estimated": units_estimated,
        "end_date": "2026-01-01",  # ordering set by caller via list order
    }


def test_detect_protected_status_real_user_data():
    """User's actual 12-month series — Sep25=306, Oct25=229 → unprotected."""
    cycles = [
        _make_cycle("Sep25", 306),
        _make_cycle("Oct25", 229),
        _make_cycle("Nov25", 153),
        _make_cycle("Dec25", 137),
        _make_cycle("Jan26", 124),
        _make_cycle("Feb26", 133),
    ]
    result = fesco_bill.detect_protected_status(cycles)
    assert result["status"] == "unprotected"
    assert result["max_units_in_window"] == 306
    assert result["violator_cycle"] == "Sep25"


def test_detect_protected_status_all_under_200():
    cycles = [
        _make_cycle(f"M{i:02d}", 150) for i in range(6)
    ]
    result = fesco_bill.detect_protected_status(cycles)
    assert result["status"] == "protected"
    assert result["max_units_in_window"] == 150
    assert result["violator_cycle"] is None


def test_detect_protected_status_fewer_than_6_returns_unknown():
    cycles = [_make_cycle(f"M{i:02d}", 150) for i in range(5)]
    result = fesco_bill.detect_protected_status(cycles)
    assert result["status"] == "unknown"
    assert "need 6 closed cycles" in result["reason"].lower()


def test_detect_uses_units_actual_else_estimated():
    cycles = [
        _make_cycle("M01", units_actual=None, units_estimated=120.5),
        _make_cycle("M02", units_actual=180),
        _make_cycle("M03", units_actual=190),
        _make_cycle("M04", units_actual=150),
        _make_cycle("M05", units_actual=100),
        _make_cycle("M06", units_actual=199),
    ]
    result = fesco_bill.detect_protected_status(cycles)
    assert result["status"] == "protected"


def test_detect_picks_only_last_6_closed():
    # 8 cycles, oldest two have 250 (would violate), but only last 6 are checked.
    cycles = [
        _make_cycle("OLDA", 250), _make_cycle("OLDB", 250),
        _make_cycle("M01", 100), _make_cycle("M02", 100),
        _make_cycle("M03", 100), _make_cycle("M04", 100),
        _make_cycle("M05", 100), _make_cycle("M06", 100),
    ]
    result = fesco_bill.detect_protected_status(cycles)
    assert result["status"] == "protected"


# -------------------------- predict_status_flip --------------------------

def _user_real_series():
    """Bilal's actual last-12-months series ending Feb26 (from FESCO bill)."""
    pairs = [
        ("Mar25", 115), ("Apr25", 171), ("May25", 190), ("Jun25", 272),
        ("Jul25", 357), ("Aug25", 396), ("Sep25", 306), ("Oct25", 229),
        ("Nov25", 153), ("Dec25", 137), ("Jan26", 124), ("Feb26", 133),
    ]
    return [_make_cycle(label, units) for label, units in pairs]


def test_predict_flip_with_low_apr_forecast_flips_protected_in_may26():
    cycles = _user_real_series()
    open_forecast = {"label": "Mar26", "projected_units": 162.0}
    result = fesco_bill.predict_status_flip(cycles, open_forecast, _cfg())
    # Walk: closed=Mar25..Feb26, plus pseudo Mar26=162. After Feb26 the
    # rolling window Sep25..Feb26 contains 306 → unprotected. With Mar26=162
    # the window Oct25..Mar26 contains 229 → still unprotected.
    # Pseudo cycles after Mar26 use trailing-3-month avg = (124+133+162)/3 ≈ 140.
    # So Apr forecast = 140, May forecast = 140, etc.
    # Window Nov25..Apr (153,137,124,133,162,140) max=162 → protected.
    assert result["flips_to"] == "protected"
    assert result["at_cycle"] == "Apr26"


def test_predict_flip_with_high_apr_forecast_no_flip_in_horizon():
    cycles = _user_real_series()
    open_forecast = {"label": "Mar26", "projected_units": 250.0}
    result = fesco_bill.predict_status_flip(cycles, open_forecast, _cfg())
    # trailing avg = (124+133+250)/3 ≈ 169, but Mar26=250 sits in window for 6 months.
    # window Oct25..Mar26 has 229 and 250 → unprotected.
    # window Nov25..Apr has 250 → unprotected.
    # window Mar26..Aug has 250 → unprotected.
    # After Mar26 ages out (window Apr..Sep), all 169 → protected.
    # That's a flip — at Sep26.
    assert result["flips_to"] == "protected"
    assert result["at_cycle"] == "Sep26"


def test_predict_flip_already_protected_can_flip_unprotected():
    # Use real month labels so _next_cycle_label produces sensible hypothetical names.
    pairs = [
        ("Sep25", 150), ("Oct25", 150), ("Nov25", 150),
        ("Dec25", 150), ("Jan26", 150), ("Feb26", 150),
    ]
    cycles = [_make_cycle(label, units) for label, units in pairs]
    open_forecast = {"label": "Mar26", "projected_units": 250.0}
    result = fesco_bill.predict_status_flip(cycles, open_forecast, _cfg())
    # Already protected. Adding 250 → window Oct25..Mar26 max=250 → unprotected.
    assert result["flips_to"] == "unprotected"
    assert result["at_cycle"] == "Mar26"


def test_predict_flip_no_change_returns_null():
    pairs = [
        ("Sep25", 150), ("Oct25", 150), ("Nov25", 150),
        ("Dec25", 150), ("Jan26", 150), ("Feb26", 150),
    ]
    cycles = [_make_cycle(label, units) for label, units in pairs]
    open_forecast = {"label": "Mar26", "projected_units": 150.0}
    result = fesco_bill.predict_status_flip(cycles, open_forecast, _cfg())
    assert result["flips_to"] is None
