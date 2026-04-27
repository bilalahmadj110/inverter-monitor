# FESCO Bill Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the savings/billing model from calendar-month to FESCO's 26th-to-26th billing cycle, add a new top-level **FESCO Bill** page that mirrors the actual bill, and auto-detect NEPRA Protected status from a 12-month bill history.

**Architecture:** Two new Python modules (`fesco_bill.py` for pure functions, `fesco_cycles.py` for SQLite CRUD), one new HTML template, one new JS file, additive changes to `lesco_tariff.py` / `cost_savings.py` / `cost_config.py` / `app.py`, and one new SQLite table `billing_cycles`. The pure-function core makes everything unit-testable in isolation.

**Tech Stack:** Python 3, Flask 3, Flask-WTF (CSRF), SQLite, Tailwind CSS, Font Awesome, vanilla JS (fetch + DOM). Pytest + freezegun for tests. No new runtime dependencies in production.

**Spec:** [docs/superpowers/specs/2026-04-27-fesco-bill-cycle-design.md](../specs/2026-04-27-fesco-bill-cycle-design.md)

---

## File Structure

**Created:**
- `fesco_bill.py` — pure functions: cycle boundaries, aggregation, forecast, protected status detection, flip prediction
- `fesco_cycles.py` — `CycleStore` class: thread-safe CRUD over `billing_cycles` table, plus `bootstrap_history` + `ensure_open_cycle`
- `templates/fesco_bill.html` — the new page (mirrors FESCO bill layout)
- `static/js/fesco_bill.js` — cycle picker, edit modal, bootstrap form
- `tests/__init__.py` — empty marker
- `tests/conftest.py` — pytest fixtures (`tmp_db`, `seed_daily`)
- `tests/test_lesco_tariff_fix_charges.py`
- `tests/test_cost_config_defaults.py`
- `tests/test_fesco_bill.py`
- `tests/test_fesco_cycles.py`
- `tests/test_cost_savings_cycle.py`
- `tests/test_fesco_routes.py`
- `pytest.ini` — pytest config (testpaths)

**Modified:**
- `lesco_tariff.py` — add `fix_charges_total()`; include `fix_charges` line in `compute_bill()`
- `cost_config.py` — extend `DEFAULT_NON_TARIFF` with reading-day + meter metadata keys
- `cost_savings.py` — add `compute_savings_for_cycle()`; switch `build_full_payload()` to cycle-based aggregation
- `app.py` — register page route `/fesco-bill` + JSON routes `/fesco/cycles` `/fesco/bill` `/fesco/status` `/fesco/cycle` `/fesco/bootstrap` `/fesco/cycle/<label>` (DELETE)
- `templates/dashboard.html` — add "Record Mar26 bill" banner + nav link
- `templates/solar_flow.html` — add nav link
- `templates/savings.html` — add nav link; relabel "this month" → "this cycle" + show cycle dates
- `templates/history.html` — add nav link
- `requirements.txt` — add `pytest`, `freezegun`

---

## Task 1: Pytest setup

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add test dependencies**

Edit `requirements.txt` — append at the end:

```
pytest==8.3.4
freezegun==1.5.1
```

Run: `pip install pytest==8.3.4 freezegun==1.5.1`

- [ ] **Step 2: Create pytest config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
```

- [ ] **Step 3: Create tests package marker**

Create `tests/__init__.py` as an empty file.

- [ ] **Step 4: Create shared fixtures**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures for the inverter-monitor test suite."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date

import pytest

# Make project modules importable from tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB with the schemas the app's modules expect.
    Returns the path. Each test gets its own file."""
    db_path = str(tmp_path / "test.db")
    with sqlite3.connect(db_path) as conn:
        # Mirrors power_stats.py daily_stats schema (subset that fesco_bill needs).
        conn.execute('''
            CREATE TABLE daily_stats (
                id INTEGER PRIMARY KEY,
                date TEXT UNIQUE NOT NULL,
                solar_min REAL, solar_max REAL, solar_avg REAL, solar_energy REAL,
                grid_min REAL, grid_max REAL, grid_avg REAL, grid_energy REAL,
                load_min REAL, load_max REAL, load_avg REAL, load_energy REAL,
                battery_min REAL, battery_max REAL,
                battery_charge_energy REAL, battery_discharge_energy REAL
            )
        ''')
        conn.commit()
    return db_path


@pytest.fixture
def seed_daily(tmp_db):
    """Helper: returns a function that inserts a daily_stats row.
    Energy values are in Wh (matches power_stats convention)."""
    def _seed(date_str: str, *, solar_wh: float = 0, grid_wh: float = 0, load_wh: float = 0):
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO daily_stats
                   (date, solar_energy, grid_energy, load_energy)
                   VALUES (?, ?, ?, ?)''',
                (date_str, solar_wh, grid_wh, load_wh),
            )
            conn.commit()
    return _seed
```

- [ ] **Step 5: Verify pytest discovers the empty suite**

Run: `pytest`
Expected: `no tests ran in 0.0Xs` (exits 5, but discovery succeeded).

- [ ] **Step 6: Commit**

```bash
git add pytest.ini tests/__init__.py tests/conftest.py requirements.txt
git commit -m "chore: add pytest + freezegun + shared fixtures"
```

---

## Task 2: Add fix_charges to lesco_tariff

**Files:**
- Modify: `lesco_tariff.py:137-221` (compute_bill)
- Modify: `lesco_tariff.py:27-64` (DEFAULT_CONFIG)
- Create: `tests/test_lesco_tariff_fix_charges.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lesco_tariff_fix_charges.py`:

```python
"""Verify that compute_bill includes fix charges (sanctioned_load_kW × per-kW rate)
and that GST/ED apply on top of them, matching the FESCO bill layout."""
from __future__ import annotations

import lesco_tariff


def _cfg(**overrides):
    cfg = lesco_tariff.default_config()
    cfg["consumer_type"] = "unprotected"
    cfg["sanctioned_load_kw"] = 3.0
    cfg["fix_charges_per_kw"] = 300
    cfg["fpa_per_unit"] = 0
    cfg["fc_surcharge_per_unit"] = 0
    cfg["nj_surcharge_per_unit"] = 0
    cfg["qtr_adjustment_per_unit"] = 0
    cfg["gst_percent"] = 0
    cfg["electricity_duty_percent"] = 0
    cfg["tv_fee_pkr"] = 0
    cfg["min_bill_below_5kw"] = 0
    cfg.update(overrides)
    return cfg


def test_fix_charges_total_helper():
    cfg = _cfg(sanctioned_load_kw=3.0, fix_charges_per_kw=300)
    assert lesco_tariff.fix_charges_total(cfg) == 900


def test_fix_charges_total_zero_when_unset():
    cfg = _cfg(fix_charges_per_kw=0)
    assert lesco_tariff.fix_charges_total(cfg) == 0


def test_compute_bill_includes_fix_charges_in_breakdown():
    # 162 units × Rs 28.91 (slab 101-200, unprotected, flat) = 4683.42
    # + 900 fix charges = 5583.42 pre_tax (no GST/ED in this minimal cfg)
    bill = lesco_tariff.compute_bill(162, _cfg())
    assert bill["fix_charges"] == 900
    assert bill["energy_charge"] == 4683.42
    assert bill["subtotal"] == 5583.42


def test_gst_applies_on_top_of_fix_charges():
    # With 17% GST: pre_tax = 4683.42 + 900 = 5583.42
    # GST = 5583.42 × 0.17 = 949.18 (rounded)
    bill = lesco_tariff.compute_bill(162, _cfg(gst_percent=17.0))
    assert bill["fix_charges"] == 900
    assert bill["gst"] == 949.18
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lesco_tariff_fix_charges.py -v`
Expected: FAIL — `AttributeError: module 'lesco_tariff' has no attribute 'fix_charges_total'` (and `KeyError: 'fix_charges'` once you get past that).

- [ ] **Step 3: Add fix_charges_per_kw to DEFAULT_CONFIG**

Edit `lesco_tariff.py`. In `DEFAULT_CONFIG` (around line 27), add a new key after `qtr_adjustment_per_unit`:

```python
    "qtr_adjustment_per_unit": 0.0,   # Quarterly Tariff Adjustment (optional)
    "fix_charges_per_kw": 300,        # Fixed monthly charge per kW of sanctioned load (FESCO ~300).
```

- [ ] **Step 4: Add fix_charges_total helper**

Edit `lesco_tariff.py`. After `merge_config()` (around line 82), add:

```python
def fix_charges_total(cfg: dict[str, Any]) -> float:
    """Monthly fixed charges = per-kW rate × sanctioned load (kW). Returned
    flat — no slab math. Included as a line item in compute_bill()."""
    rate = float(cfg.get("fix_charges_per_kw", 0) or 0)
    load = float(cfg.get("sanctioned_load_kw", 0) or 0)
    return round(rate * load, 2)
```

- [ ] **Step 5: Wire fix_charges into compute_bill**

Edit `lesco_tariff.py`. In `compute_bill()`, after the FPA/QTA/surcharge calculation (around line 156-159), before `pre_tax`:

Replace:
```python
    fpa = units * float(cfg.get("fpa_per_unit", 0) or 0)
    qta = units * float(cfg.get("qtr_adjustment_per_unit", 0) or 0)
    fc_surcharge = units * float(cfg.get("fc_surcharge_per_unit", 0) or 0)
    nj_surcharge = units * float(cfg.get("nj_surcharge_per_unit", 0) or 0)

    # GST and electricity duty are calculated on (energy + FPA + QTA + surcharges).
    pre_tax = energy_charge + fpa + qta + fc_surcharge + nj_surcharge
```

With:
```python
    fpa = units * float(cfg.get("fpa_per_unit", 0) or 0)
    qta = units * float(cfg.get("qtr_adjustment_per_unit", 0) or 0)
    fc_surcharge = units * float(cfg.get("fc_surcharge_per_unit", 0) or 0)
    nj_surcharge = units * float(cfg.get("nj_surcharge_per_unit", 0) or 0)
    fix_charges = fix_charges_total(cfg)

    # GST and electricity duty are calculated on (energy + fix + FPA + QTA + surcharges).
    pre_tax = energy_charge + fix_charges + fpa + qta + fc_surcharge + nj_surcharge
```

Then in the returned dict (around line 201-221), add `"fix_charges": round(fix_charges, 2),` between `"energy_lines"` and `"fpa"`:

```python
    return {
        "units": round(units, 3),
        "consumer_type": consumer_type,
        "slab_mode": slab_mode,
        "slab_info": slab_info,
        "energy_charge": round(energy_charge, 2),
        "energy_lines": slab_lines,
        "fix_charges": round(fix_charges, 2),
        "fpa": round(fpa, 2),
        ...
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_lesco_tariff_fix_charges.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add lesco_tariff.py tests/test_lesco_tariff_fix_charges.py
git commit -m "feat(tariff): add fix_charges line to compute_bill (FESCO 300/kW)"
```

---

## Task 3: Add new cost_config defaults

**Files:**
- Modify: `cost_config.py:23-29` (DEFAULT_NON_TARIFF)
- Create: `tests/test_cost_config_defaults.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cost_config_defaults.py`:

```python
"""DEFAULT_NON_TARIFF must include FESCO billing-cycle and meter-metadata keys."""
from __future__ import annotations

import cost_config


def test_default_includes_reading_day():
    cfg = cost_config.DEFAULT_NON_TARIFF
    assert cfg["reading_day_of_month"] == 26
    assert cfg["weekend_rolls_to_monday"] is True


def test_default_includes_meter_metadata():
    cfg = cost_config.DEFAULT_NON_TARIFF
    assert "consumer_id" in cfg
    assert "tariff_code" in cfg
    assert "connection_date" in cfg
    assert "meter_no" in cfg
    assert cfg["discom_name"] == "FESCO"


def test_load_returns_new_keys(tmp_db):
    cc = cost_config.CostConfig(tmp_db)
    cfg = cc.load()
    assert cfg["reading_day_of_month"] == 26
    assert cfg["discom_name"] == "FESCO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cost_config_defaults.py -v`
Expected: FAIL with `KeyError: 'reading_day_of_month'`.

- [ ] **Step 3: Extend DEFAULT_NON_TARIFF**

Edit `cost_config.py`. Replace `DEFAULT_NON_TARIFF` (around line 24-29) with:

```python
# Non-tariff settings (defaults). Tariff defaults live in lesco_tariff.py.
DEFAULT_NON_TARIFF: dict[str, Any] = {
    "install_cost_pkr": 0,           # User enters this on the savings page.
    "system_start_date": None,       # ISO date 'YYYY-MM-DD'. None until set.
    "monthly_billing_day": 1,        # Legacy: kept for back-compat, ignored by new cycle code.

    # FESCO billing-cycle settings.
    "reading_day_of_month": 26,
    "weekend_rolls_to_monday": True,

    # Bill metadata (shown on the FESCO Bill page header).
    "consumer_id": "",
    "tariff_code": "A-1a(01)",
    "connection_date": None,         # ISO 'YYYY-MM-DD'.
    "meter_no": "",
    "discom_name": "FESCO",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cost_config_defaults.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add cost_config.py tests/test_cost_config_defaults.py
git commit -m "feat(config): add FESCO reading-day + meter metadata defaults"
```

---

## Task 4: fesco_bill.compute_cycle_boundaries

**Files:**
- Create: `fesco_bill.py`
- Modify: `tests/test_fesco_bill.py` (creating it now, will be extended in later tasks)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fesco_bill.py`:

```python
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
    # 28 Feb 2027 is Sunday → Mon 1 Mar
    assert end == date(2027, 3, 1)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_bill.py -v`
Expected: ImportError — `No module named 'fesco_bill'`.

- [ ] **Step 3: Create fesco_bill module skeleton**

Create `fesco_bill.py`:

```python
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
    """Most recent end_date among closed cycles, or None."""
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
    try:
        y, m, d = row[0].split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


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

    # Fallback: rule-derived previous reading.
    prev_anchor = _prev_month(end)
    prev_candidate = _clamp_to_month_end(prev_anchor.year, prev_anchor.month, target_day)
    prev_candidate = _apply_weekend_rule(prev_candidate, weekend)
    return prev_candidate + timedelta(days=1), end
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_bill.py -v -k boundaries`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add fesco_bill.py tests/test_fesco_bill.py
git commit -m "feat(fesco): compute_cycle_boundaries with weekend-roll + override"
```

---

## Task 5: fesco_bill.aggregate_cycle

**Files:**
- Modify: `fesco_bill.py`
- Modify: `tests/test_fesco_bill.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_fesco_bill.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_bill.py -v -k aggregate`
Expected: FAIL with `AttributeError: module 'fesco_bill' has no attribute 'aggregate_cycle'`.

- [ ] **Step 3: Implement aggregate_cycle**

Append to `fesco_bill.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_bill.py -v -k aggregate`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add fesco_bill.py tests/test_fesco_bill.py
git commit -m "feat(fesco): aggregate_cycle SUMs daily_stats by date range"
```

---

## Task 6: fesco_bill.forecast_open_cycle

**Files:**
- Modify: `fesco_bill.py`
- Modify: `tests/test_fesco_bill.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_fesco_bill.py`:

```python
# -------------------------- forecast_open_cycle --------------------------

def test_forecast_open_cycle_run_rate(tmp_db, seed_daily):
    """At day 10 of a 30-day cycle, having used 50 kWh, projection = 150 kWh."""
    # Cycle: 27 Feb..26 Mar 2026 (28 days). Today: midpoint, 13 Mar.
    # Seed grid usage for days 1-15 of cycle (27 Feb..13 Mar).
    cycle_start = date(2026, 2, 27)
    today = date(2026, 3, 13)
    elapsed = (today - cycle_start).days + 1  # 15
    total = (date(2026, 3, 26) - cycle_start).days + 1  # 28

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_bill.py -v -k forecast`
Expected: FAIL with `AttributeError: module 'fesco_bill' has no attribute 'forecast_open_cycle'`.

- [ ] **Step 3: Implement forecast_open_cycle**

Append to `fesco_bill.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_bill.py -v -k forecast`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add fesco_bill.py tests/test_fesco_bill.py
git commit -m "feat(fesco): run-rate forecast with same-month-last-year reference"
```

---

## Task 7: fesco_bill.detect_protected_status

**Files:**
- Modify: `fesco_bill.py`
- Modify: `tests/test_fesco_bill.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_fesco_bill.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_bill.py -v -k detect`
Expected: FAIL with `AttributeError: ... 'detect_protected_status'`.

- [ ] **Step 3: Implement detect_protected_status**

Append to `fesco_bill.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_bill.py -v -k detect`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add fesco_bill.py tests/test_fesco_bill.py
git commit -m "feat(fesco): NEPRA Protected-status detection from 6-cycle window"
```

---

## Task 8: fesco_bill.predict_status_flip

**Files:**
- Modify: `fesco_bill.py`
- Modify: `tests/test_fesco_bill.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_fesco_bill.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_bill.py -v -k predict`
Expected: FAIL with `AttributeError: ... 'predict_status_flip'`.

- [ ] **Step 3: Implement predict_status_flip**

Append to `fesco_bill.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_bill.py -v -k predict`
Expected: 4 passed.

- [ ] **Step 5: Run the whole fesco_bill suite**

Run: `pytest tests/test_fesco_bill.py -v`
Expected: All 18 tests pass (6 boundaries + 3 aggregate + 3 forecast + 5 detect + 4 predict — but adjust if counts differ; minimum is everything green).

- [ ] **Step 6: Commit**

```bash
git add fesco_bill.py tests/test_fesco_bill.py
git commit -m "feat(fesco): predict_status_flip walks forward timeline"
```

---

## Task 9: fesco_cycles.CycleStore (CRUD + bootstrap + ensure_open_cycle)

**Files:**
- Create: `fesco_cycles.py`
- Create: `tests/test_fesco_cycles.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fesco_cycles.py`:

```python
"""Tests for the billing_cycles CRUD store."""
from __future__ import annotations

from datetime import date

import pytest

import fesco_cycles


@pytest.fixture
def store(tmp_db):
    return fesco_cycles.CycleStore(tmp_db)


def _cfg(**overrides):
    base = {
        "reading_day_of_month": 26,
        "weekend_rolls_to_monday": True,
        "sanctioned_load_kw": 3.0,
        "fix_charges_per_kw": 300,
        "fpa_per_unit": 0,
        "fc_surcharge_per_unit": 0,
        "nj_surcharge_per_unit": 0,
        "qtr_adjustment_per_unit": 0,
        "gst_percent": 0,
        "electricity_duty_percent": 0,
        "tv_fee_pkr": 0,
        "min_bill_below_5kw": 0,
        "consumer_type": "unprotected",
        "unprotected_slabs": [
            {"up_to": 100, "rate": 22.44, "label": "1-100"},
            {"up_to": 200, "rate": 28.91, "label": "101-200"},
            {"up_to": None, "rate": 33.10, "label": "Above 200"},
        ],
    }
    base.update(overrides)
    return base


def test_table_created_on_init(tmp_db):
    fesco_cycles.CycleStore(tmp_db)
    import sqlite3
    with sqlite3.connect(tmp_db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(billing_cycles)")}
    assert "cycle_label" in cols
    assert "units_actual" in cols
    assert "fpa_per_unit_actual" in cols


def test_upsert_and_get(store):
    cycle = {
        "cycle_label": "Mar26",
        "start_date": "2026-02-27",
        "end_date": "2026-03-26",
        "status": "closed",
        "units_actual": 162,
        "bill_amount_actual": 7597,
        "payment_amount": 7597,
    }
    store.upsert_cycle(cycle)
    got = store.get_cycle("Mar26")
    assert got["units_actual"] == 162
    assert got["bill_amount_actual"] == 7597
    assert got["status"] == "closed"


def test_upsert_overwrites_existing(store):
    store.upsert_cycle({
        "cycle_label": "Mar26", "start_date": "2026-02-27",
        "end_date": "2026-03-26", "status": "open", "units_actual": None,
    })
    store.upsert_cycle({
        "cycle_label": "Mar26", "start_date": "2026-02-27",
        "end_date": "2026-03-26", "status": "closed", "units_actual": 162,
    })
    got = store.get_cycle("Mar26")
    assert got["status"] == "closed"
    assert got["units_actual"] == 162


def test_list_cycles_sorted_desc(store):
    for label, end in [("Jan26", "2026-01-26"), ("Mar26", "2026-03-26"),
                       ("Feb26", "2026-02-26")]:
        store.upsert_cycle({
            "cycle_label": label, "start_date": "2025-12-27",
            "end_date": end, "status": "closed",
        })
    rows = store.list_cycles()
    assert [r["cycle_label"] for r in rows] == ["Mar26", "Feb26", "Jan26"]


def test_delete_cycle(store):
    store.upsert_cycle({
        "cycle_label": "Mar26", "start_date": "2026-02-27",
        "end_date": "2026-03-26", "status": "closed",
    })
    store.delete_cycle("Mar26")
    assert store.get_cycle("Mar26") is None


def test_bootstrap_history_inserts_rows(store):
    rows = [
        {"cycle_label": "Mar25", "units_actual": 115, "bill_amount_actual": 2948,
         "payment_amount": 0},
        {"cycle_label": "Apr25", "units_actual": 171, "bill_amount_actual": 5283,
         "payment_amount": 8526},
        {"cycle_label": "May25", "units_actual": 190, "bill_amount_actual": -1376,
         "payment_amount": 0},
    ]
    inserted = store.bootstrap_history(rows, _cfg())
    assert inserted == 3
    got = store.get_cycle("Mar25")
    assert got["units_actual"] == 115
    assert got["status"] == "closed"
    # start/end dates are back-computed from the rule.
    assert got["end_date"] == "2025-03-26"


def test_bootstrap_history_skips_existing_labels(store):
    store.upsert_cycle({
        "cycle_label": "Mar25", "start_date": "2025-02-27",
        "end_date": "2025-03-26", "status": "closed", "units_actual": 999,
    })
    inserted = store.bootstrap_history(
        [{"cycle_label": "Mar25", "units_actual": 115}], _cfg()
    )
    assert inserted == 0
    got = store.get_cycle("Mar25")
    assert got["units_actual"] == 999  # untouched


def test_ensure_open_cycle_creates_open_when_none(store):
    today = date(2026, 3, 15)
    cycle = store.ensure_open_cycle(today, _cfg())
    assert cycle["status"] == "open"
    assert cycle["cycle_label"] == "Mar26"
    assert cycle["end_date"] == "2026-03-26"


def test_ensure_open_cycle_closes_stale_open(store):
    # An open cycle for Feb26 exists; today is past its end_date.
    store.upsert_cycle({
        "cycle_label": "Feb26", "start_date": "2026-01-27",
        "end_date": "2026-02-26", "status": "open",
        "units_estimated": 130,
    })
    today = date(2026, 3, 15)
    new_open = store.ensure_open_cycle(today, _cfg())
    assert new_open["cycle_label"] == "Mar26"
    assert new_open["status"] == "open"
    closed = store.get_cycle("Feb26")
    assert closed["status"] == "closed"
    # bill_amount_estimated populated from compute_bill on units_estimated
    assert closed["bill_amount_estimated"] is not None
    assert closed["bill_amount_estimated"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_cycles.py -v`
Expected: ImportError — `No module named 'fesco_cycles'`.

- [ ] **Step 3: Create fesco_cycles module**

Create `fesco_cycles.py`:

```python
"""SQLite-backed CRUD store for FESCO billing cycles.

Modeled on cost_config.CostConfig: thread-safe, lazy table-init, simple dict-in /
dict-out API. Cycle math (boundary computation, bill compute) is delegated to
fesco_bill and lesco_tariff — this module handles only persistence.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import date, timedelta
from typing import Any

import fesco_bill
import lesco_tariff


logger = logging.getLogger(__name__)


_CYCLE_COLUMNS = (
    "id", "cycle_label", "start_date", "end_date", "status",
    "units_estimated", "units_actual",
    "bill_amount_estimated", "bill_amount_actual",
    "payment_amount", "fpa_per_unit_actual",
    "notes", "updated_at",
)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


class CycleStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS billing_cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_label TEXT NOT NULL UNIQUE,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    units_estimated REAL,
                    units_actual INTEGER,
                    bill_amount_estimated REAL,
                    bill_amount_actual REAL,
                    payment_amount REAL,
                    fpa_per_unit_actual REAL,
                    notes TEXT,
                    updated_at INTEGER NOT NULL
                )
            ''')
            conn.execute(
                'CREATE INDEX IF NOT EXISTS idx_cycles_end_date '
                'ON billing_cycles(end_date DESC)'
            )
            conn.commit()

    def list_cycles(self, limit: int = 24) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM billing_cycles ORDER BY end_date DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_cycle(self, label: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM billing_cycles WHERE cycle_label = ?',
                (label,),
            ).fetchone()
        return _row_to_dict(row)

    def upsert_cycle(self, cycle: dict[str, Any]) -> dict[str, Any]:
        if "cycle_label" not in cycle:
            raise ValueError("cycle_label is required")
        if "start_date" not in cycle or "end_date" not in cycle:
            raise ValueError("start_date and end_date are required")
        with self._lock:
            existing = self.get_cycle(cycle["cycle_label"])
            merged = dict(existing) if existing else {}
            for k, v in cycle.items():
                merged[k] = v
            merged.setdefault("status", "closed")
            merged["updated_at"] = int(time.time())
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    '''
                    INSERT INTO billing_cycles
                        (cycle_label, start_date, end_date, status,
                         units_estimated, units_actual,
                         bill_amount_estimated, bill_amount_actual,
                         payment_amount, fpa_per_unit_actual,
                         notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cycle_label) DO UPDATE SET
                        start_date = excluded.start_date,
                        end_date = excluded.end_date,
                        status = excluded.status,
                        units_estimated = excluded.units_estimated,
                        units_actual = excluded.units_actual,
                        bill_amount_estimated = excluded.bill_amount_estimated,
                        bill_amount_actual = excluded.bill_amount_actual,
                        payment_amount = excluded.payment_amount,
                        fpa_per_unit_actual = excluded.fpa_per_unit_actual,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    ''',
                    (
                        merged["cycle_label"], merged["start_date"], merged["end_date"],
                        merged["status"],
                        merged.get("units_estimated"), merged.get("units_actual"),
                        merged.get("bill_amount_estimated"), merged.get("bill_amount_actual"),
                        merged.get("payment_amount"), merged.get("fpa_per_unit_actual"),
                        merged.get("notes"), merged["updated_at"],
                    ),
                )
                conn.commit()
        return self.get_cycle(cycle["cycle_label"])

    def delete_cycle(self, label: str) -> None:
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'DELETE FROM billing_cycles WHERE cycle_label = ?',
                    (label,),
                )
                conn.commit()

    def bootstrap_history(
        self, rows: list[dict[str, Any]], cfg: dict[str, Any]
    ) -> int:
        """Bulk-insert historical rows. Each row needs cycle_label and
        units_actual; bill_amount_actual + payment_amount are optional.
        Skips rows whose label already exists. Back-computes start/end dates
        from the reading-day rule. Returns count inserted."""
        inserted = 0
        target_day = int(cfg.get("reading_day_of_month", 26) or 26)
        weekend = bool(cfg.get("weekend_rolls_to_monday", True))
        for r in rows:
            label = r.get("cycle_label")
            if not label or self.get_cycle(label):
                continue
            end = _end_date_from_label(label, target_day, weekend)
            if end is None:
                continue
            start = _back_one_cycle(end, target_day, weekend) + timedelta(days=1)
            self.upsert_cycle({
                "cycle_label": label,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status": "closed",
                "units_actual": r.get("units_actual"),
                "bill_amount_actual": r.get("bill_amount_actual"),
                "payment_amount": r.get("payment_amount"),
                "notes": r.get("notes") or "bootstrap",
            })
            inserted += 1
        return inserted

    def ensure_open_cycle(
        self, today: date, cfg: dict[str, Any]
    ) -> dict[str, Any]:
        """Idempotently maintain exactly one 'open' cycle.

        - If no open cycle exists → create one for today's bounds.
        - If the open cycle's end_date < today → close it (auto-fill
          units_estimated and bill_amount_estimated from daily_stats), then
          create a new open cycle.
        """
        with self._lock:
            existing_open = self._find_open_locked()
            if existing_open is not None:
                end_iso = existing_open["end_date"]
                end_d = _parse_iso(end_iso)
                if end_d is not None and today <= end_d:
                    return existing_open
                # Close the stale open cycle.
                start_d = _parse_iso(existing_open["start_date"])
                if start_d:
                    energy = fesco_bill.aggregate_cycle(start_d, end_d, self.db_path)
                    units_est = energy["grid_kwh"]
                    bill_est = lesco_tariff.compute_bill(units_est, cfg)["total"]
                else:
                    units_est = existing_open.get("units_estimated") or 0
                    bill_est = existing_open.get("bill_amount_estimated") or 0
                self._unlocked_upsert({
                    **existing_open,
                    "status": "closed",
                    "units_estimated": round(units_est, 3),
                    "bill_amount_estimated": round(bill_est, 2),
                })

            # Create the new open cycle.
            start, end = fesco_bill.compute_cycle_boundaries(today, cfg, self.db_path)
            label = fesco_bill.cycle_label_for(end)
            existing = self.get_cycle(label)
            if existing and existing["status"] == "closed":
                # Reopen unlikely but possible (user-edited dates); leave it closed.
                return existing
            self._unlocked_upsert({
                "cycle_label": label,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status": "open",
            })
            return self.get_cycle(label)

    def _find_open_locked(self) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT * FROM billing_cycles WHERE status = "open" '
                'ORDER BY end_date DESC LIMIT 1'
            ).fetchone()
        return _row_to_dict(row)

    def _unlocked_upsert(self, cycle: dict[str, Any]) -> None:
        """Same as upsert_cycle but assumes the lock is already held by caller."""
        cycle = dict(cycle)
        cycle["updated_at"] = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''
                INSERT INTO billing_cycles
                    (cycle_label, start_date, end_date, status,
                     units_estimated, units_actual,
                     bill_amount_estimated, bill_amount_actual,
                     payment_amount, fpa_per_unit_actual,
                     notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_label) DO UPDATE SET
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    status = excluded.status,
                    units_estimated = excluded.units_estimated,
                    units_actual = excluded.units_actual,
                    bill_amount_estimated = excluded.bill_amount_estimated,
                    bill_amount_actual = excluded.bill_amount_actual,
                    payment_amount = excluded.payment_amount,
                    fpa_per_unit_actual = excluded.fpa_per_unit_actual,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                ''',
                (
                    cycle["cycle_label"], cycle["start_date"], cycle["end_date"],
                    cycle["status"],
                    cycle.get("units_estimated"), cycle.get("units_actual"),
                    cycle.get("bill_amount_estimated"), cycle.get("bill_amount_actual"),
                    cycle.get("payment_amount"), cycle.get("fpa_per_unit_actual"),
                    cycle.get("notes"), cycle["updated_at"],
                ),
            )
            conn.commit()


# ---------------------- module-level helpers ----------------------

def _parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _end_date_from_label(label: str, target_day: int, weekend: bool) -> date | None:
    """'Mar25' → 26 Mar 2025 (weekend-adjusted), full date object."""
    if len(label) < 5:
        return None
    mon = label[:3]
    try:
        yy = int(label[3:])
    except ValueError:
        return None
    if mon not in fesco_bill._MONTH_ABBR:
        return None
    month_idx = fesco_bill._MONTH_ABBR.index(mon) + 1
    year = 2000 + yy if yy < 70 else 1900 + yy
    candidate = fesco_bill._clamp_to_month_end(year, month_idx, target_day)
    return fesco_bill._apply_weekend_rule(candidate, weekend)


def _back_one_cycle(end: date, target_day: int, weekend: bool) -> date:
    """Given an end_date, return the previous cycle's end_date (one month back,
    rule-adjusted)."""
    prev_anchor = fesco_bill._prev_month(end)
    candidate = fesco_bill._clamp_to_month_end(
        prev_anchor.year, prev_anchor.month, target_day
    )
    return fesco_bill._apply_weekend_rule(candidate, weekend)


# ---------------------- module-level singleton (matches CostConfig pattern) ----

_instance: CycleStore | None = None


def get_instance(db_path: str | None = None) -> CycleStore:
    global _instance
    if _instance is None:
        if db_path is None:
            import os
            db_path = os.path.join(os.path.dirname(__file__), 'data', 'power_stats.db')
        _instance = CycleStore(db_path)
    return _instance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fesco_cycles.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add fesco_cycles.py tests/test_fesco_cycles.py
git commit -m "feat(fesco): CycleStore CRUD + bootstrap_history + ensure_open_cycle"
```

---

## Task 10: cost_savings — compute_savings_for_cycle + updated build_full_payload

**Files:**
- Modify: `cost_savings.py`
- Create: `tests/test_cost_savings_cycle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cost_savings_cycle.py`:

```python
"""compute_savings_for_cycle aggregates by date range, not calendar month."""
from __future__ import annotations

from datetime import date

import lesco_tariff
import cost_savings


def _cfg():
    cfg = lesco_tariff.default_config()
    cfg["consumer_type"] = "unprotected"
    cfg["sanctioned_load_kw"] = 3.0
    cfg["fix_charges_per_kw"] = 0
    cfg["fpa_per_unit"] = 0
    cfg["fc_surcharge_per_unit"] = 0
    cfg["nj_surcharge_per_unit"] = 0
    cfg["qtr_adjustment_per_unit"] = 0
    cfg["gst_percent"] = 0
    cfg["electricity_duty_percent"] = 0
    cfg["tv_fee_pkr"] = 0
    cfg["min_bill_below_5kw"] = 0
    return cfg


def test_savings_for_cycle_uses_date_range(tmp_db, seed_daily):
    # Seed: load=200 kWh, grid=80 kWh in cycle 27 Feb..26 Mar 2026.
    # Solar = 120 kWh.
    # bill_without = compute_bill(200) at unprotected → slab 101-200 (28.91) → 5782
    # bill_with    = compute_bill(80) → slab 1-100 (22.44) → 1795.20
    # savings = 5782.00 - 1795.20 = 3986.80
    seed_daily("2026-02-27", load_wh=200_000, grid_wh=80_000)
    cfg = _cfg()
    result = cost_savings.compute_savings_for_cycle(
        tmp_db, date(2026, 2, 27), date(2026, 3, 26), cfg
    )
    assert result["energy"]["load_kwh"] == 200.0
    assert result["energy"]["grid_kwh"] == 80.0
    assert result["bill_without_solar"]["total"] == 5782.0
    assert result["bill_with_solar"]["total"] == 1795.2
    assert result["savings_pkr"] == 3986.8
    assert result["start"] == "2026-02-27"
    assert result["end"] == "2026-03-26"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cost_savings_cycle.py -v`
Expected: FAIL with `AttributeError: ... 'compute_savings_for_cycle'`.

- [ ] **Step 3: Add compute_savings_for_cycle**

Edit `cost_savings.py`. After `compute_savings_for_month()` (around line 84), add:

```python
def _cycle_energy_kwh(db_path: str, start: date, end: date) -> dict[str, float]:
    """SUM daily_stats energy fields between start and end (inclusive)."""
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


def compute_savings_for_cycle(
    db_path: str, start: date, end: date, config: dict[str, Any]
) -> dict[str, Any]:
    """Solar savings for a billing cycle (date range). Same formula as
    compute_savings_for_month but with explicit start/end bounds."""
    energy = _cycle_energy_kwh(db_path, start, end)
    bill_without = lesco_tariff.compute_bill(energy["load_kwh"], config)
    bill_with    = lesco_tariff.compute_bill(energy["grid_kwh"], config)
    savings = bill_without["total"] - bill_with["total"]
    return {
        "start": start.isoformat(),
        "end":   end.isoformat(),
        "energy": {k: round(v, 3) for k, v in energy.items()},
        "bill_without_solar": bill_without,
        "bill_with_solar": bill_with,
        "savings_pkr": round(savings, 2),
    }
```

- [ ] **Step 4: Update build_full_payload to use cycle bounds**

Edit `cost_savings.py`. Replace `build_full_payload()` (around line 260-281) with:

```python
def build_full_payload(stats_manager, cost_config) -> dict[str, Any]:
    """One-shot payload for the savings page: today + this cycle + lifetime
    + slab projection + payback. The frontend gets everything in a single GET.
    """
    import fesco_bill
    import fesco_cycles

    cfg = cost_config.load()
    today_block = compute_today(stats_manager, cfg)

    today = date.today()
    start, end = fesco_bill.compute_cycle_boundaries(today, cfg, stats_manager.db_path)
    cycle_block = compute_savings_for_cycle(stats_manager.db_path, start, end, cfg)
    cycle_block["label"] = fesco_bill.cycle_label_for(end)

    lifetime = compute_lifetime_from_cycles(stats_manager.db_path, cfg)
    payback = compute_payback(cfg.get("install_cost_pkr") or 0, lifetime["avg_daily_savings_pkr"])
    projection = compute_slab_projection(stats_manager.db_path, cfg)

    return {
        "config": cfg,
        "today": today_block,
        "cycle": cycle_block,
        "lifetime": lifetime,
        "payback": payback,
        "projection": projection,
    }


def compute_lifetime_from_cycles(db_path: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Walk the billing_cycles table for closed cycles and sum savings.
    Falls back to the calendar-month version if no cycles exist."""
    import fesco_cycles
    store = fesco_cycles.CycleStore(db_path)
    cycles = [c for c in store.list_cycles(limit=240) if c["status"] == "closed"]
    if not cycles:
        return compute_lifetime(db_path, cfg, cfg.get("system_start_date"))

    cycles.sort(key=lambda c: c["end_date"])  # oldest first
    months = []
    total_savings = 0.0
    total_solar = 0.0

    for c in cycles:
        # Reuse compute_savings_for_cycle for consistency with the cycle block.
        try:
            s = date.fromisoformat(c["start_date"])
            e = date.fromisoformat(c["end_date"])
        except (ValueError, TypeError):
            continue
        result = compute_savings_for_cycle(db_path, s, e, cfg)
        months.append({
            "month": c["cycle_label"],
            "solar_kwh": result["energy"]["solar_kwh"],
            "grid_kwh":  result["energy"]["grid_kwh"],
            "load_kwh":  result["energy"]["load_kwh"],
            "savings_pkr": result["savings_pkr"],
        })
        total_savings += result["savings_pkr"]
        total_solar += result["energy"]["solar_kwh"]

    first = date.fromisoformat(cycles[0]["start_date"])
    today = date.today()
    days_elapsed = max(1, (today - first).days + 1)

    return {
        "system_start_date": first.isoformat(),
        "days_elapsed": days_elapsed,
        "total_savings_pkr": round(total_savings, 2),
        "total_solar_kwh": round(total_solar, 3),
        "avg_daily_savings_pkr": round(total_savings / days_elapsed, 2),
        "months": months,
    }
```

The `compute_slab_projection` function in cost_savings.py uses calendar-month bounds; **leave it alone for now** — its existing slab-cliff math is still useful and will be updated when the savings page is reskinned (Task 11+ touch the FESCO Bill page; the Savings page slab projection can be migrated later or left as a known minor inconsistency).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cost_savings_cycle.py -v`
Expected: 1 passed.

- [ ] **Step 6: Run full test suite to confirm nothing regressed**

Run: `pytest -v`
Expected: All previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add cost_savings.py tests/test_cost_savings_cycle.py
git commit -m "feat(savings): compute_savings_for_cycle + cycle-based lifetime/build_full_payload"
```

---

## Task 11: Flask routes for FESCO Bill

**Files:**
- Modify: `app.py` (after savings routes, around line 369)
- Create: `tests/test_fesco_routes.py`

- [ ] **Step 1: Write smoke tests for the routes**

Create `tests/test_fesco_routes.py`:

```python
"""Smoke tests for the /fesco/* routes. Uses Flask test_client; no real
inverter, no real Socket.IO, no auth (we monkeypatch login_required to a no-op)."""
from __future__ import annotations

import os
import sys
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The app reads INVERTER_ADMIN_PASSWORD + INVERTER_SECRET_KEY from env via auth.init_auth.
    monkeypatch.setenv("INVERTER_ADMIN_PASSWORD", "test-pass")
    monkeypatch.setenv("INVERTER_SECRET_KEY", "test-secret-key-32chars-padding-more")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "False")  # disable CSRF for these tests

    # Point power_stats at a temp DB so we don't touch real data.
    fake_db = str(tmp_path / "test.db")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Force module-level singletons to use temp DB before app.py imports them.
    import power_stats
    power_stats._instance = power_stats.PowerStats(fake_db)
    import cost_config
    cost_config._instance = cost_config.CostConfig(fake_db)
    import fesco_cycles
    fesco_cycles._instance = fesco_cycles.CycleStore(fake_db)

    # Avoid touching the inverter at startup — patch ContinuousReader.
    with patch("continuous_reader.ContinuousReader") as MockReader:
        mock_inst = MagicMock()
        mock_inst.get_latest_data.return_value = None
        mock_inst.get_config.return_value = {}
        mock_inst.get_statistics.return_value = {}
        MockReader.return_value = mock_inst
        import importlib
        import app as app_module
        importlib.reload(app_module)
        flask_app = app_module.app
        flask_app.config["WTF_CSRF_ENABLED"] = False

        # Mark session as logged in for all requests.
        with flask_app.test_client() as c:
            with c.session_transaction() as sess:
                sess["logged_in"] = True
            yield c


def test_get_cycles_empty(client):
    resp = client.get("/fesco/cycles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cycles"] == []


def test_bootstrap_then_list(client):
    payload = {"rows": [
        {"cycle_label": "Jan26", "units_actual": 124, "bill_amount_actual": 4645,
         "payment_amount": 4645},
        {"cycle_label": "Feb26", "units_actual": 133, "bill_amount_actual": 5691,
         "payment_amount": 5691},
    ]}
    resp = client.post(
        "/fesco/bootstrap",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["inserted"] == 2

    listing = client.get("/fesco/cycles").get_json()
    labels = [c["cycle_label"] for c in listing["cycles"]]
    assert "Jan26" in labels and "Feb26" in labels


def test_bill_returns_open_cycle_payload(client):
    resp = client.get("/fesco/bill")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cycle" in data
    assert "header" in data
    assert "history" in data
    assert "status" in data
    assert data["cycle"]["status"] == "open"


def test_upsert_actual_then_status_updates(client):
    # Bootstrap 6 closed cycles all <= 200 → status should be 'protected'.
    rows = [
        {"cycle_label": "Aug25", "units_actual": 150},
        {"cycle_label": "Sep25", "units_actual": 150},
        {"cycle_label": "Oct25", "units_actual": 150},
        {"cycle_label": "Nov25", "units_actual": 150},
        {"cycle_label": "Dec25", "units_actual": 150},
        {"cycle_label": "Jan26", "units_actual": 150},
    ]
    client.post("/fesco/bootstrap", data=json.dumps({"rows": rows}),
                content_type="application/json")
    status = client.get("/fesco/status").get_json()
    assert status["status"] == "protected"


def test_delete_cycle(client):
    client.post("/fesco/bootstrap",
                data=json.dumps({"rows": [{"cycle_label": "Jan26", "units_actual": 124}]}),
                content_type="application/json")
    resp = client.delete("/fesco/cycle/Jan26")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    listing = client.get("/fesco/cycles").get_json()
    assert all(c["cycle_label"] != "Jan26" for c in listing["cycles"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fesco_routes.py -v`
Expected: 404 errors on the `/fesco/*` paths.

- [ ] **Step 3: Wire fesco_cycles singleton in app.py**

Edit `app.py`. After the `cost_cfg = cost_config_module.get_instance(...)` line (line 68), add:

```python
import fesco_cycles as fesco_cycles_module
import fesco_bill
cycle_store = fesco_cycles_module.get_instance(stats_manager.db_path)
```

- [ ] **Step 4: Add the page route**

Edit `app.py`. After the `/savings` page route (around line 154), add:

```python
@app.route('/fesco-bill')
@login_required
def fesco_bill_page():
    return render_template('fesco_bill.html')
```

- [ ] **Step 5: Add the JSON routes**

Edit `app.py`. After the savings JSON routes (around line 369, before `/ai/status`), add:

```python
# ---- FESCO Bill JSON endpoints --------------------------------------------

def _build_bill_payload(label: str | None) -> dict:
    """Assemble the full /fesco/bill response for one cycle (open if label=None)."""
    from datetime import date as _date
    cfg = cost_cfg.load()
    today = _date.today()
    cycle_store.ensure_open_cycle(today, cfg)

    if label:
        cycle = cycle_store.get_cycle(label)
        if cycle is None:
            return {"error": f"unknown cycle: {label}"}
    else:
        cycle = next(
            (c for c in cycle_store.list_cycles(limit=24) if c["status"] == "open"),
            None,
        )
        if cycle is None:
            return {"error": "no open cycle"}

    start = _date.fromisoformat(cycle["start_date"])
    end = _date.fromisoformat(cycle["end_date"])

    # Forecast block (only meaningful for open cycle).
    forecast = (
        fesco_bill.forecast_open_cycle(today, cfg, stats_manager.db_path)
        if cycle["status"] == "open" else None
    )

    # Bill breakdown — for open cycle use forecast units; for closed use actual or estimated.
    if cycle["status"] == "open":
        units_for_bill = forecast["projected_units"] if forecast else 0
    else:
        units_for_bill = (
            cycle["units_actual"]
            if cycle["units_actual"] is not None
            else (cycle["units_estimated"] or 0)
        )
    bill_breakdown = lesco_tariff.compute_bill(units_for_bill, cfg)

    # Late-payment surcharge projections.
    payable = bill_breakdown["total"]
    lp = {
        "phase_1_pkr": round(payable * fesco_bill.LP_PHASE_1_PERCENT / 100, 2),
        "phase_2_pkr": round(payable * fesco_bill.LP_PHASE_2_PERCENT / 100, 2),
    }

    # Reading + due dates.
    from datetime import timedelta as _td
    reading_date = end
    due_date = reading_date + _td(days=fesco_bill.DUE_DATE_OFFSET_DAYS)
    lp_phase_2_date = due_date + _td(days=fesco_bill.LP_PHASE_2_DAYS)

    # 12-month history (most-recent 12 closed cycles, newest-first).
    all_cycles = cycle_store.list_cycles(limit=24)
    history = [
        {
            "label": c["cycle_label"],
            "units": c["units_actual"] if c["units_actual"] is not None
                     else c["units_estimated"],
            "bill_amount": c["bill_amount_actual"]
                           if c["bill_amount_actual"] is not None
                           else c["bill_amount_estimated"],
            "paid": c["payment_amount"],
            "is_actual": c["units_actual"] is not None,
        }
        for c in all_cycles if c["status"] == "closed"
    ][:12]

    # Status detection (uses oldest-first list).
    closed_oldest_first = list(reversed([c for c in all_cycles if c["status"] == "closed"]))
    status_block = fesco_bill.detect_protected_status(closed_oldest_first)
    if forecast:
        flip = fesco_bill.predict_status_flip(closed_oldest_first, forecast, cfg)
        status_block["flip_prediction"] = flip

    return {
        "cycle": cycle,
        "header": {
            "consumer_id": cfg.get("consumer_id"),
            "tariff_code": cfg.get("tariff_code"),
            "load_kw": cfg.get("sanctioned_load_kw"),
            "connection_date": cfg.get("connection_date"),
            "meter_no": cfg.get("meter_no"),
            "discom_name": cfg.get("discom_name"),
            "reading_date": reading_date.isoformat(),
            "due_date": due_date.isoformat(),
            "lp_phase_2_date": lp_phase_2_date.isoformat(),
        },
        "forecast": forecast,
        "bill_breakdown": bill_breakdown,
        "lp_surcharge": lp,
        "history": history,
        "status": status_block,
    }


@app.route('/fesco/cycles')
@login_required
def fesco_list_cycles():
    return jsonify({"cycles": cycle_store.list_cycles(limit=24)})


@app.route('/fesco/bill')
@login_required
def fesco_bill_data():
    label = request.args.get('cycle')
    return jsonify(_build_bill_payload(label))


@app.route('/fesco/status')
@login_required
def fesco_status():
    from datetime import date as _date
    cfg = cost_cfg.load()
    cycle_store.ensure_open_cycle(_date.today(), cfg)
    cycles = cycle_store.list_cycles(limit=24)
    closed_oldest_first = list(reversed([c for c in cycles if c["status"] == "closed"]))
    status = fesco_bill.detect_protected_status(closed_oldest_first)

    open_cycle = next((c for c in cycles if c["status"] == "open"), None)
    if open_cycle:
        forecast = fesco_bill.forecast_open_cycle(
            _date.today(), cfg, stats_manager.db_path
        )
        status["flip_prediction"] = fesco_bill.predict_status_flip(
            closed_oldest_first, forecast, cfg
        )
    return jsonify(status)


@app.route('/fesco/cycle', methods=['POST'])
@login_required
@limiter.limit('30 per minute')
def fesco_upsert_cycle():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or "cycle_label" not in body:
        return jsonify({"success": False, "error": "cycle_label required"}), 400
    try:
        result = cycle_store.upsert_cycle(body)
        audit('fesco_cycle_upsert', label=body.get("cycle_label"))
        return jsonify({"success": True, "cycle": result})
    except Exception as e:
        logger.error(f"fesco_upsert failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/fesco/bootstrap', methods=['POST'])
@login_required
@limiter.limit('5 per minute')
def fesco_bootstrap():
    body = request.get_json(silent=True) or {}
    rows = body.get("rows") or []
    if not isinstance(rows, list):
        return jsonify({"success": False, "error": "rows must be a list"}), 400
    try:
        cfg = cost_cfg.load()
        inserted = cycle_store.bootstrap_history(rows, cfg)
        audit('fesco_bootstrap', count=inserted)
        return jsonify({"success": True, "inserted": inserted})
    except Exception as e:
        logger.error(f"fesco_bootstrap failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/fesco/cycle/<label>', methods=['DELETE'])
@login_required
@limiter.limit('10 per minute')
def fesco_delete_cycle(label):
    try:
        cycle_store.delete_cycle(label)
        audit('fesco_cycle_delete', label=label)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"fesco_delete failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

- [ ] **Step 6: Create a placeholder template so /fesco-bill returns 200**

Create `templates/fesco_bill.html` (real content in Task 12):

```html
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>FESCO Bill</title></head>
<body><h1>FESCO Bill</h1><p>Coming soon.</p></body></html>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_fesco_routes.py -v`
Expected: 5 passed.

- [ ] **Step 8: Run the full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add app.py templates/fesco_bill.html tests/test_fesco_routes.py
git commit -m "feat(fesco): /fesco-bill page + JSON routes (cycles, bill, status, upsert, bootstrap)"
```

---

## Task 12: FESCO Bill page template

**Files:**
- Modify: `templates/fesco_bill.html` (replacing the placeholder from Task 11)
- Create: `static/js/fesco_bill.js`

- [ ] **Step 1: Write the template**

Replace the contents of `templates/fesco_bill.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>FESCO Bill - Inverter Monitor</title>
    <link rel="icon" type="image/png" href="/static/icons/favicon.png">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; }
        .pulse-est { animation: pulse-est 2s ease-in-out infinite; }
        @keyframes pulse-est {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-indigo-900">

    <nav class="bg-black/30 backdrop-blur-sm border-b border-white/10">
        <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <div class="flex items-center gap-2 text-white font-semibold">
                <i class="fas fa-solar-panel text-yellow-300"></i>
                <div class="leading-tight">
                    <div>Inverter Monitor</div>
                    <div class="text-[8px] font-mono font-normal text-white/25 tracking-wide">build {{ app_version }}</div>
                </div>
            </div>
            <div class="flex items-center gap-1">
                <a href="/" class="px-4 py-1.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 transition-colors">Live</a>
                <a href="/reports" class="px-4 py-1.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 transition-colors">Reports</a>
                <a href="/savings" class="px-4 py-1.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 transition-colors">Savings</a>
                <a href="/fesco-bill" class="px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 text-white">FESCO Bill</a>
                <form method="post" action="{{ url_for('auth.logout') }}" class="inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="px-3 py-1.5 rounded-lg text-sm font-medium text-white/60 hover:bg-white/10 hover:text-white transition-colors" title="Sign out">
                        <i class="fas fa-right-from-bracket"></i>
                    </button>
                </form>
            </div>
        </div>
    </nav>

    <div class="max-w-4xl mx-auto px-4 py-6" id="page-root">

        <!-- Bootstrap state (shown only when no cycles exist) -->
        <div id="bootstrap-pane" class="hidden bg-white/5 border border-white/10 rounded-xl p-6 mb-6">
            <h2 class="text-2xl font-bold text-white mb-2">Welcome — record your last 12 months first</h2>
            <p class="text-white/70 text-sm mb-4">
                Open any recent FESCO bill. Type the 12 rows from its
                <em>"MONTH / UNITS / BILL / PAYMENT"</em> grid below. We'll use
                this to detect Protected status and seed your history.
            </p>
            <form id="bootstrap-form" class="space-y-2">
                <div class="grid grid-cols-12 gap-2 text-xs text-white/50 px-2">
                    <div class="col-span-3">Month</div>
                    <div class="col-span-3">Units</div>
                    <div class="col-span-3">Bill (PKR)</div>
                    <div class="col-span-3">Paid (PKR)</div>
                </div>
                <div id="bootstrap-rows"></div>
                <button type="submit" class="w-full mt-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold">
                    <i class="fas fa-database mr-2"></i> Save 12-month history
                </button>
            </form>
        </div>

        <!-- Main bill view (hidden during bootstrap state) -->
        <div id="bill-pane" class="hidden">
            <!-- Cycle picker -->
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                    <i class="fas fa-file-invoice text-blue-300 text-2xl"></i>
                    <div>
                        <div class="text-white text-2xl font-bold" id="bill-title">FESCO Bill</div>
                        <div class="text-white/50 text-xs" id="bill-subtitle"></div>
                    </div>
                </div>
                <select id="cycle-picker" class="bg-white/10 border border-white/20 text-white text-sm rounded-lg px-3 py-2"></select>
            </div>

            <!-- Header strip (consumer + dates) -->
            <div id="header-strip" class="bg-white/5 border border-white/10 rounded-xl p-4 mb-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm"></div>

            <!-- Status banner (estimated/actual + Protected) -->
            <div id="status-banner" class="rounded-xl p-4 mb-4"></div>

            <!-- Charges grid (2 columns: FESCO | GOVT) -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div class="bg-white/5 border border-white/10 rounded-xl p-4">
                    <div class="text-xs uppercase tracking-wider text-white/50 mb-3">FESCO Charges</div>
                    <div id="fesco-charges" class="space-y-1.5 text-sm"></div>
                </div>
                <div class="bg-white/5 border border-white/10 rounded-xl p-4">
                    <div class="text-xs uppercase tracking-wider text-white/50 mb-3">Govt Charges</div>
                    <div id="govt-charges" class="space-y-1.5 text-sm"></div>
                </div>
            </div>

            <!-- Slab breakdown -->
            <div class="bg-white/5 border border-white/10 rounded-xl p-4 mb-4">
                <div class="text-xs uppercase tracking-wider text-white/50 mb-3">Slab Breakdown</div>
                <div id="slab-breakdown" class="text-sm"></div>
            </div>

            <!-- Payable -->
            <div id="payable-block" class="bg-blue-900/30 border border-blue-500/30 rounded-xl p-4 mb-4"></div>

            <!-- 12-month history -->
            <div class="bg-white/5 border border-white/10 rounded-xl p-4 mb-4">
                <div class="text-xs uppercase tracking-wider text-white/50 mb-3">Last 12 months</div>
                <table class="w-full text-sm">
                    <thead class="text-white/50 text-xs uppercase">
                        <tr>
                            <th class="text-left py-2">Month</th>
                            <th class="text-right py-2">Units</th>
                            <th class="text-right py-2">Bill</th>
                            <th class="text-right py-2">Paid</th>
                            <th class="text-right py-2 w-8"></th>
                        </tr>
                    </thead>
                    <tbody id="history-body"></tbody>
                </table>
            </div>

            <!-- Record actual bill CTA (only on open cycle) -->
            <button id="record-actual-btn" class="hidden w-full py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold">
                <i class="fas fa-pen-to-square mr-2"></i> Enter actual bill for <span id="record-actual-label"></span>
            </button>
        </div>

        <!-- Edit modal -->
        <div id="edit-modal" class="hidden fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-white/10 rounded-xl w-full max-w-md p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-white text-lg font-bold">Enter actual bill</h3>
                    <button id="edit-close" class="text-white/50 hover:text-white"><i class="fas fa-xmark"></i></button>
                </div>
                <form id="edit-form" class="space-y-3">
                    <input type="hidden" id="edit-label">
                    <div>
                        <label class="block text-white/70 text-xs mb-1">Reading date</label>
                        <input id="edit-reading-date" type="date" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm" required>
                    </div>
                    <div>
                        <label class="block text-white/70 text-xs mb-1">Units consumed</label>
                        <input id="edit-units" type="number" min="0" step="1" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm" required>
                    </div>
                    <div>
                        <label class="block text-white/70 text-xs mb-1">Bill amount (PKR)</label>
                        <input id="edit-bill" type="number" step="0.01" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm" required>
                    </div>
                    <div>
                        <label class="block text-white/70 text-xs mb-1">Paid amount (PKR, optional)</label>
                        <input id="edit-paid" type="number" step="0.01" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm">
                    </div>
                    <div>
                        <label class="block text-white/70 text-xs mb-1">FPA per unit (PKR, optional)</label>
                        <input id="edit-fpa" type="number" step="0.0001" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm">
                    </div>
                    <div>
                        <label class="block text-white/70 text-xs mb-1">Notes</label>
                        <textarea id="edit-notes" rows="2" class="w-full bg-white/10 border border-white/20 text-white rounded-lg px-3 py-2 text-sm"></textarea>
                    </div>
                    <button type="submit" class="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold">
                        Save
                    </button>
                </form>
            </div>
        </div>

    </div>

    <script src="/static/js/fesco_bill.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify the template renders**

Run: `python -c "from app import app; c = app.test_client(); print(c.get('/fesco-bill').status_code)"`
*(This requires INVERTER_ADMIN_PASSWORD + INVERTER_SECRET_KEY env vars set; if they aren't, set fake ones for the smoke check.)*
Expected: prints `302` (redirect to login) or `200` if logged in. Either is fine — confirms no template syntax error.

Alternative: just run `pytest tests/test_fesco_routes.py -v -k bill_returns_open_cycle_payload` — passing means the template parses OK.

- [ ] **Step 3: Commit (template only — JS comes next)**

```bash
git add templates/fesco_bill.html
git commit -m "feat(fesco): bill page template (Tailwind, dark theme, mirrors FESCO bill)"
```

---

## Task 13: FESCO Bill page JavaScript

**Files:**
- Create: `static/js/fesco_bill.js`

- [ ] **Step 1: Implement the page logic**

Create `static/js/fesco_bill.js`:

```javascript
/* FESCO Bill page — fetches /fesco/* and renders into the template's slots.

   No frameworks; vanilla DOM. CSRF token read from <meta name="csrf-token">.
   Reused for: cycle picker, edit modal, bootstrap form, banner dismissal. */

(function () {
  'use strict';

  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const fmtPkr = (n) => (n == null) ? '—' :
    new Intl.NumberFormat('en-PK', { maximumFractionDigits: 2 }).format(n);
  const fmtKwh = (n) => (n == null) ? '—' : Number(n).toFixed(0);
  const fmtDate = (iso) => {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-');
    return `${d} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m, 10) - 1]} ${y}`;
  };

  async function fetchJSON(url, options = {}) {
    const opts = { credentials: 'same-origin', ...options };
    if (opts.method && opts.method !== 'GET') {
      opts.headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken, ...(opts.headers || {}) };
    }
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }

  // -------------------------- Bootstrap pane --------------------------

  function buildBootstrapRows() {
    const container = $('bootstrap-rows');
    container.innerHTML = '';
    const months = lastNMonthLabels(12);
    months.forEach((label) => {
      const row = document.createElement('div');
      row.className = 'grid grid-cols-12 gap-2';
      row.innerHTML = `
        <input type="text" value="${label}" data-field="label" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" readonly>
        <input type="number" min="0" step="1" data-field="units" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="kWh">
        <input type="number" step="0.01" data-field="bill" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="PKR">
        <input type="number" step="0.01" data-field="paid" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="PKR">
      `;
      container.appendChild(row);
    });
  }

  function lastNMonthLabels(n) {
    const ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const today = new Date();
    const labels = [];
    // Most-recent CLOSED cycle is the prior calendar month.
    let y = today.getFullYear();
    let m = today.getMonth(); // 0-based; -1 = previous month
    for (let i = 0; i < n; i++) {
      m = m - 1;
      if (m < 0) { m = 11; y -= 1; }
      labels.unshift(`${ABBR[m]}${String(y).slice(-2)}`);
    }
    return labels;
  }

  async function submitBootstrap(ev) {
    ev.preventDefault();
    const rows = [];
    document.querySelectorAll('#bootstrap-rows > div').forEach((row) => {
      const label = row.querySelector('[data-field="label"]').value;
      const units = parseFloat(row.querySelector('[data-field="units"]').value);
      const bill = parseFloat(row.querySelector('[data-field="bill"]').value);
      const paid = parseFloat(row.querySelector('[data-field="paid"]').value);
      if (!isNaN(units)) {
        rows.push({
          cycle_label: label,
          units_actual: units,
          bill_amount_actual: isNaN(bill) ? null : bill,
          payment_amount: isNaN(paid) ? null : paid,
        });
      }
    });
    if (rows.length === 0) {
      alert('Enter at least one row.');
      return;
    }
    await fetchJSON('/fesco/bootstrap', {
      method: 'POST',
      body: JSON.stringify({ rows }),
    });
    location.reload();
  }

  // -------------------------- Bill rendering --------------------------

  function renderHeader(payload) {
    const h = payload.header;
    $('header-strip').innerHTML = `
      <div><div class="text-white/50 text-xs">Consumer ID</div><div class="text-white">${h.consumer_id || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Tariff</div><div class="text-white">${h.tariff_code || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Load</div><div class="text-white">${h.load_kw || '—'} kW</div></div>
      <div><div class="text-white/50 text-xs">Meter</div><div class="text-white">${h.meter_no || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Reading date</div><div class="text-white">${fmtDate(h.reading_date)}</div></div>
      <div><div class="text-white/50 text-xs">Due date</div><div class="text-white">${fmtDate(h.due_date)}</div></div>
      <div class="col-span-2 md:col-span-4 text-xs text-white/40">
        Connection: ${fmtDate(h.connection_date)} · ${h.discom_name || 'FESCO'}
      </div>
    `;
  }

  function renderStatusBanner(payload) {
    const cycle = payload.cycle;
    const isOpen = cycle.status === 'open';
    const isActual = !isOpen && cycle.units_actual != null;
    const status = payload.status || {};
    let badgeBg = isActual ? 'bg-emerald-500/20 border-emerald-500/40' : 'bg-amber-500/20 border-amber-500/40';
    let badgeIcon = isActual ? 'fa-check-circle text-emerald-300' : 'fa-bolt text-amber-300';
    let badgeLabel = isActual ? 'ACTUAL' : 'ESTIMATED';
    let detail = '';
    if (isOpen && payload.forecast) {
      detail = `cycle in progress · ${payload.forecast.days_elapsed} of ${payload.forecast.total_days} days elapsed`;
      const lastYr = payload.forecast.same_month_last_year_units;
      if (lastYr != null) {
        detail += ` · vs ${payload.forecast.same_month_last_year_label}: ${lastYr}`;
      }
    } else if (!isOpen && !isActual) {
      detail = 'awaiting bill — record actuals to lock in';
    }

    let statusLine = '';
    if (status.status) {
      const flip = status.flip_prediction;
      let flipText = '';
      if (flip && flip.flips_to) {
        flipText = ` · flips ${flip.flips_to} ${flip.at_cycle}${flip.condition ? ' (' + flip.condition + ')' : ''}`;
      }
      const tone = status.status === 'protected' ? 'text-emerald-300' : 'text-amber-300';
      statusLine = `<div class="text-xs ${tone} mt-1">Status: <strong>${status.status.toUpperCase()}</strong>${flipText}</div>`;
    }

    $('status-banner').className = `rounded-xl p-4 mb-4 border ${badgeBg}`;
    $('status-banner').innerHTML = `
      <div class="flex items-start gap-3">
        <i class="fas ${badgeIcon} mt-0.5 ${isOpen ? 'pulse-est' : ''}"></i>
        <div>
          <div class="text-white text-sm"><strong>${badgeLabel}</strong> · ${detail}</div>
          ${statusLine}
        </div>
      </div>
    `;
  }

  function renderCharges(payload) {
    const b = payload.bill_breakdown;
    const fesco = $('fesco-charges');
    fesco.innerHTML = `
      <div class="flex justify-between"><span class="text-white/70">Cost of electricity (${fmtKwh(b.units)} units)</span><span class="text-white">${fmtPkr(b.energy_charge)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">Fix charges</span><span class="text-white">${fmtPkr(b.fix_charges)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">FPA</span><span class="text-white">${fmtPkr(b.fpa)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">FC surcharge</span><span class="text-white">${fmtPkr(b.fc_surcharge)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">QTR tariff adj</span><span class="text-white">${fmtPkr(b.qta)}</span></div>
    `;
    const govt = $('govt-charges');
    govt.innerHTML = `
      <div class="flex justify-between"><span class="text-white/70">Electricity duty</span><span class="text-white">${fmtPkr(b.electricity_duty)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">TV fee</span><span class="text-white">${fmtPkr(b.tv_fee)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">GST</span><span class="text-white">${fmtPkr(b.gst)}</span></div>
    `;
  }

  function renderSlab(payload) {
    const b = payload.bill_breakdown;
    const lines = (b.energy_lines || []).map((l) =>
      `<div class="text-white">${fmtKwh(l.units)} units × Rs ${l.rate} (${l.label}) = Rs ${fmtPkr(l.amount)}</div>`
    ).join('');
    let cliff = '';
    if (b.slab_info && b.slab_info.units_to_next_slab != null && b.slab_info.units_to_next_slab > 0) {
      cliff = `<div class="text-amber-300 text-xs mt-2">⚠ ${b.slab_info.units_to_next_slab.toFixed(0)} units to next slab cliff</div>`;
    }
    $('slab-breakdown').innerHTML = lines + cliff;
  }

  function renderPayable(payload) {
    const b = payload.bill_breakdown;
    const lp = payload.lp_surcharge || {};
    const h = payload.header;
    $('payable-block').innerHTML = `
      <div class="flex items-center justify-between text-lg">
        <span class="text-white/80">Payable within due date (${fmtDate(h.due_date)})</span>
        <span class="text-white font-bold">Rs ${fmtPkr(b.total)}</span>
      </div>
      <div class="flex items-center justify-between text-sm mt-1">
        <span class="text-white/50">L.P. surcharge after due date (4%)</span>
        <span class="text-white/70">+ Rs ${fmtPkr(lp.phase_1_pkr)}</span>
      </div>
      <div class="flex items-center justify-between text-sm">
        <span class="text-white/50">L.P. surcharge after ${fmtDate(h.lp_phase_2_date)} (8%)</span>
        <span class="text-white/70">+ Rs ${fmtPkr(lp.phase_2_pkr)}</span>
      </div>
    `;
  }

  function renderHistory(payload) {
    const tbody = $('history-body');
    const rows = (payload.history || []).map((row) => {
      const billCol = row.bill_amount != null && row.bill_amount < 0
        ? `<span class="text-rose-400">${fmtPkr(row.bill_amount)} (refund)</span>`
        : fmtPkr(row.bill_amount);
      const editPencil = row.is_actual
        ? `<button class="text-white/30 hover:text-white" data-edit-label="${row.label}"><i class="fas fa-pen"></i></button>`
        : `<button class="text-amber-300 hover:text-amber-100" data-edit-label="${row.label}" title="Awaiting actual"><i class="fas fa-pen-to-square"></i></button>`;
      return `<tr class="border-t border-white/5">
        <td class="py-1.5 text-white">${row.label}</td>
        <td class="py-1.5 text-right text-white">${fmtKwh(row.units)}</td>
        <td class="py-1.5 text-right text-white">${billCol}</td>
        <td class="py-1.5 text-right text-white/70">${fmtPkr(row.paid)}</td>
        <td class="py-1.5 text-right">${editPencil}</td>
      </tr>`;
    }).join('');
    tbody.innerHTML = rows;
    tbody.querySelectorAll('[data-edit-label]').forEach((btn) => {
      btn.addEventListener('click', () => openEditModal(btn.dataset.editLabel));
    });
  }

  function renderRecordActualBtn(payload) {
    const btn = $('record-actual-btn');
    if (payload.cycle.status === 'open') {
      btn.classList.remove('hidden');
      $('record-actual-label').textContent = payload.cycle.cycle_label;
      btn.onclick = () => openEditModal(payload.cycle.cycle_label);
    } else {
      btn.classList.add('hidden');
    }
  }

  function populateCyclePicker(allCycles, currentLabel) {
    const sel = $('cycle-picker');
    sel.innerHTML = '';
    allCycles.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c.cycle_label;
      const tag = c.status === 'open' ? ' (open)' : '';
      opt.textContent = `${c.cycle_label}${tag}`;
      if (c.cycle_label === currentLabel) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.onchange = () => {
      const next = sel.value;
      const url = new URL(window.location.href);
      url.searchParams.set('cycle', next);
      window.location.href = url.toString();
    };
  }

  // -------------------------- Edit modal --------------------------

  function openEditModal(label) {
    $('edit-modal').classList.remove('hidden');
    $('edit-label').value = label;
    fetchJSON(`/fesco/bill?cycle=${encodeURIComponent(label)}`).then((p) => {
      $('edit-reading-date').value = p.cycle.end_date || p.header.reading_date;
      $('edit-units').value = p.cycle.units_actual ?? '';
      $('edit-bill').value = p.cycle.bill_amount_actual ?? '';
      $('edit-paid').value = p.cycle.payment_amount ?? '';
      $('edit-fpa').value = p.cycle.fpa_per_unit_actual ?? '';
      $('edit-notes').value = p.cycle.notes ?? '';
    });
  }

  function closeEditModal() {
    $('edit-modal').classList.add('hidden');
  }

  async function submitEdit(ev) {
    ev.preventDefault();
    const label = $('edit-label').value;
    const reading = $('edit-reading-date').value;
    // We need start_date too; pull it from the existing cycle to preserve.
    const existing = await fetchJSON(`/fesco/bill?cycle=${encodeURIComponent(label)}`);
    const body = {
      cycle_label: label,
      start_date: existing.cycle.start_date,
      end_date: reading,
      status: 'closed',
      units_actual: parseInt($('edit-units').value, 10),
      bill_amount_actual: parseFloat($('edit-bill').value),
      payment_amount: $('edit-paid').value ? parseFloat($('edit-paid').value) : null,
      fpa_per_unit_actual: $('edit-fpa').value ? parseFloat($('edit-fpa').value) : null,
      notes: $('edit-notes').value || null,
    };
    await fetchJSON('/fesco/cycle', { method: 'POST', body: JSON.stringify(body) });
    closeEditModal();
    location.reload();
  }

  // -------------------------- Init --------------------------

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const requestedLabel = params.get('cycle');

    let cyclesResp, billResp;
    try {
      cyclesResp = await fetchJSON('/fesco/cycles');
    } catch (e) {
      console.error(e);
      return;
    }

    if (cyclesResp.cycles.length === 0) {
      $('bootstrap-pane').classList.remove('hidden');
      $('bill-pane').classList.add('hidden');
      buildBootstrapRows();
      $('bootstrap-form').addEventListener('submit', submitBootstrap);
      return;
    }

    $('bootstrap-pane').classList.add('hidden');
    $('bill-pane').classList.remove('hidden');

    const url = requestedLabel ? `/fesco/bill?cycle=${encodeURIComponent(requestedLabel)}` : '/fesco/bill';
    billResp = await fetchJSON(url);

    $('bill-title').textContent = `FESCO Bill — ${billResp.cycle.cycle_label}`;
    $('bill-subtitle').textContent = `${fmtDate(billResp.cycle.start_date)} → ${fmtDate(billResp.cycle.end_date)}`;
    populateCyclePicker(cyclesResp.cycles, billResp.cycle.cycle_label);
    renderHeader(billResp);
    renderStatusBanner(billResp);
    renderCharges(billResp);
    renderSlab(billResp);
    renderPayable(billResp);
    renderHistory(billResp);
    renderRecordActualBtn(billResp);

    $('edit-close').addEventListener('click', closeEditModal);
    $('edit-form').addEventListener('submit', submitEdit);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
```

- [ ] **Step 2: Manual sanity check (visual)**

Start the app dev server (in a way the user knows; if there's a `flask run` script, use it) and open `/fesco-bill` in the browser. Expectations:
- With no cycles: bootstrap pane shows 12 input rows pre-filled with month labels.
- After bootstrapping: the bill pane shows the open cycle, charges grid, slab breakdown, history table, and "Enter actual bill" button.
- Cycle picker switches the URL and re-renders.
- Edit pencil opens the modal pre-filled with existing values.

Document the expected behavior in the commit message; no automated DOM tests required (per spec §13).

- [ ] **Step 3: Commit**

```bash
git add static/js/fesco_bill.js
git commit -m "feat(fesco): bill page JS — picker, edit modal, bootstrap form"
```

---

## Task 14: Add nav link to existing pages

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `templates/solar_flow.html`
- Modify: `templates/savings.html`
- Modify: `templates/history.html`

For each of the four templates, find the nav `<div class="flex items-center gap-1">` block (the row with Live / Reports / Savings links) and add an `<a href="/fesco-bill">` link in the same style.

- [ ] **Step 1: Add link to dashboard.html**

Open `templates/dashboard.html`. Find the nav block (search for `href="/savings"`) and add immediately after the Savings `<a>`:

```html
<a href="/fesco-bill" class="px-4 py-1.5 rounded-lg text-sm font-medium text-white/80 hover:bg-white/10 transition-colors">FESCO Bill</a>
```

- [ ] **Step 2: Add link to solar_flow.html**

Same edit as Step 1 in `templates/solar_flow.html`.

- [ ] **Step 3: Add link to savings.html**

Same edit as Step 1 in `templates/savings.html`.

- [ ] **Step 4: Add link to history.html**

Same edit as Step 1 in `templates/history.html`. (If `history.html` uses a different nav structure, place the link consistently with whatever nav it has.)

- [ ] **Step 5: Manual smoke check**

Open each page in the browser; click the "FESCO Bill" link from each. Verify nav highlights `bg-blue-600` only on the FESCO Bill page itself.

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html templates/solar_flow.html templates/savings.html templates/history.html
git commit -m "feat(nav): add FESCO Bill link to all top-level pages"
```

---

## Task 15: "Record bill" banner on Live screen

**Files:**
- Modify: `templates/dashboard.html` (or `solar_flow.html` — whichever is `/`)
- Modify: `static/js/` — add a small banner script

- [ ] **Step 1: Confirm which template is `/`**

Run: `grep -n "^@app.route('/')" /home/bilal/dfields/inverter-monitor/app.py`
Look at the next few lines to see which template is rendered.

(For the rest of this task, assume the Live page is `solar_flow.html` based on the file naming. Adjust if it's `dashboard.html`.)

- [ ] **Step 2: Add banner placeholder to the Live template**

In `templates/solar_flow.html`, immediately after the closing `</nav>` tag, add:

```html
<div id="fesco-record-banner" class="hidden bg-amber-500/15 border-b border-amber-500/40 px-4 py-2.5">
    <div class="max-w-6xl mx-auto flex items-center justify-between">
        <div class="text-amber-200 text-sm flex items-center gap-2">
            <i class="fas fa-file-invoice"></i>
            <span>FESCO <strong id="fesco-banner-label"></strong> bill is out — record it to keep history accurate.</span>
        </div>
        <div class="flex items-center gap-2">
            <a href="/fesco-bill" class="px-3 py-1 rounded-md bg-amber-500/30 hover:bg-amber-500/50 text-white text-xs font-semibold">Record now</a>
            <button id="fesco-banner-dismiss" class="text-amber-200/60 hover:text-amber-200 text-xs">Dismiss</button>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Add the banner logic**

Append a `<script>` block at the bottom of `templates/solar_flow.html` (just before `</body>`):

```html
<script>
(async function () {
  const today = new Date().toISOString().slice(0, 10);
  const dismissedKey = `fesco-banner-dismissed-${today}`;
  if (localStorage.getItem(dismissedKey)) return;

  let cycles;
  try {
    const r = await fetch('/fesco/cycles', { credentials: 'same-origin' });
    if (!r.ok) return;
    cycles = (await r.json()).cycles;
  } catch (_) { return; }

  // Trigger condition: a closed cycle whose end_date is in the past AND has no
  // bill_amount_actual. (Most-recent closed cycle by ordering.)
  const stale = cycles.find((c) =>
    c.status === 'closed' && c.end_date < today && c.bill_amount_actual == null
  );
  if (!stale) return;

  document.getElementById('fesco-banner-label').textContent = stale.cycle_label;
  const banner = document.getElementById('fesco-record-banner');
  banner.classList.remove('hidden');
  document.getElementById('fesco-banner-dismiss').addEventListener('click', () => {
    localStorage.setItem(dismissedKey, '1');
    banner.classList.add('hidden');
  });
})();
</script>
```

- [ ] **Step 4: Manual smoke check**

1. With a closed cycle missing `bill_amount_actual`, open `/`. Expect the banner to appear.
2. Click "Dismiss". Expect the banner to disappear and not return on reload (today only).
3. Tomorrow (or change system date / clear localStorage), the banner should reappear.

- [ ] **Step 5: Commit**

```bash
git add templates/solar_flow.html
git commit -m "feat(fesco): live-screen banner prompting user to record actual bill"
```

---

## Final Verification

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: All tests pass. If any fail, fix before claiming done.

- [ ] **Step 2: Smoke check the running app**

1. Set required env vars (`INVERTER_ADMIN_PASSWORD`, `INVERTER_SECRET_KEY`).
2. Start the app per project conventions.
3. Log in, click through Live → Reports → Savings → FESCO Bill in nav. All pages load.
4. On a fresh DB, `/fesco-bill` shows the bootstrap form.
5. Enter the user's real 12-month series (Mar25=115, Apr25=171, …, Feb26=133) and submit.
6. Page rerenders showing the open Mar26 cycle, status banner says "ESTIMATED · cycle in progress", protected status says "UNPROTECTED · 306 in Sep25 violates", flip prediction says "flips protected at Apr26 (if Apr26 ≤ 200 units)".
7. Click "Enter actual bill for Mar26", fill in 162 units / 7597 PKR / 7597 paid, save.
8. Reload — Mar26 now shows ACTUAL, history grid includes it, an open Apr26 cycle now exists.
9. Visit Savings page — "this cycle" matches the FESCO Bill page's cycle.

- [ ] **Step 3: Confirm with user**

```bash
echo "Implementation complete. Checklist:"
echo "  1. All 6 tests files pass: pytest"
echo "  2. /fesco-bill page renders bill mirroring the actual FESCO format"
echo "  3. Bootstrap → enter 12 historical bills"
echo "  4. Live banner appears when an open cycle's end_date passes"
echo "  5. Savings page now shows 'this cycle' with FESCO date range"
git log --oneline -20
```

---

## Self-Review Notes

This plan was self-reviewed against [the spec](../specs/2026-04-27-fesco-bill-cycle-design.md) on 2026-04-27. Coverage map:

- Spec §5 (Data model) → Tasks 1, 3, 9
- Spec §6 (Pure-function API) → Tasks 4, 5, 6, 7, 8
- Spec §7 (Tariff fix charges) → Task 2
- Spec §8 (Savings integration) → Task 10
- Spec §9 (CRUD module) → Task 9
- Spec §10 (HTTP API) → Task 11
- Spec §11 (Page UI) → Tasks 12, 13
- Spec §11.5 (Live banner) → Task 15
- Nav links across pages → Task 14
- Spec §12 (Edge cases) → covered in tests across Tasks 4, 7, 9
- Spec §13 (Testing) → every task includes its tests

**Known intentional deviations from spec:**
- Task 10 leaves `compute_slab_projection` calendar-month-based (it's still consumed by the existing Savings page UI which we don't reskin in this plan). The FESCO Bill page implements its own slab display from `bill_breakdown.slab_info`, so the user gets the cycle-accurate cliff there. If the Savings page needs the same correction later, that's a follow-up task.
- Task 9 stores `notes='bootstrap'` on bootstrap-inserted rows; spec §12 mentions a `partial=true` flag for app-installed-mid-cycle, which we represent via the same `notes` field rather than a dedicated column to avoid a schema change after first install.

Both deviations are flagged inline; they don't block any spec requirement.
