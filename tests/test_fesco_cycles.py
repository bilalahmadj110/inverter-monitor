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
