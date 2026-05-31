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


def _cycle_cfg():
    """Unprotected tariff with a FESCO 26th reading day and the weekend roll
    disabled, so cycle boundaries land exactly on the 26th for deterministic
    assertions."""
    cfg = _cfg()
    cfg["reading_day_of_month"] = 26
    cfg["weekend_rolls_to_monday"] = False
    return cfg


def test_slab_projection_runs_on_billing_cycle(tmp_db, seed_daily):
    # today = 10 Mar 2026 → cycle = 27 Feb .. 26 Mar 2026 (28 days, 12 elapsed).
    seed_daily("2026-02-05", grid_wh=50_000)   # calendar Feb, BEFORE cycle → excluded
    seed_daily("2026-02-27", grid_wh=10_000)   # in cycle
    seed_daily("2026-03-05", grid_wh=20_000)   # in cycle, on/before today
    seed_daily("2026-03-20", grid_wh=100_000)  # in cycle but AFTER today → excluded from base

    proj = cost_savings.compute_slab_projection(
        tmp_db, _cycle_cfg(), today=date(2026, 3, 10)
    )

    assert proj["month"] == "Mar26"
    assert proj["cycle_start"] == "2026-02-27"
    assert proj["cycle_end"] == "2026-03-26"
    assert proj["days_elapsed"] == 12
    assert proj["days_remaining"] == 16
    # 10 + 20 kWh — NOT the 50 kWh from calendar Feb, NOT the future 100 kWh.
    assert proj["grid_kwh_so_far"] == 30.0
    assert proj["daily_grid_rate_kwh"] == 2.5            # 30 / 12
    assert proj["projected_month_end_grid_kwh"] == 70.0  # 30 * 28 / 12


def test_compute_today_marginal_rate_keys_off_cycle(tmp_db, seed_daily):
    # today = 10 Mar 2026 → cycle = 27 Feb .. 26 Mar 2026.
    # Seed so cycle-to-date and the (old) calendar-March total land in DIFFERENT
    # slabs — otherwise the test would silently pass even if the code reverted
    # to calendar-month logic. The discriminator is the post-`today` March row:
    # the cycle code excludes it (min(today, end)); a calendar-month sum wouldn't.
    seed_daily("2026-02-05", grid_wh=100_000)  # pre-cycle → excluded either way
    seed_daily("2026-02-27", grid_wh=30_000)   # in cycle, NOT in calendar March
    seed_daily("2026-03-05", grid_wh=40_000)   # in cycle and in March, on/before today
    seed_daily("2026-03-20", grid_wh=200_000)  # after today → cycle excludes it,
                                               # calendar-March (old code) would not

    class _FakeStats:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_summary(self, day=None):
            return {"solar_kwh": 5.0, "grid_kwh": 2.0, "load_kwh": 7.0}

    cfg = _cycle_cfg()
    result = cost_savings.compute_today(
        _FakeStats(tmp_db), cfg, today=date(2026, 3, 10)
    )

    # Cycle-to-date = 30 + 40 = 70 kWh → unprotected slab 1-100 (Rs 22.44/kWh).
    expected_rate = lesco_tariff.marginal_rate(70.0, cfg)
    # Old calendar-March path totals 40 + 200 = 240 kWh → slab 201-300
    # (Rs 33.10/kWh): a different slab, so the two rates must differ.
    calendar_rate = lesco_tariff.marginal_rate(240.0, cfg)
    assert expected_rate != calendar_rate
    assert result["marginal_rate_pkr_per_kwh"] == expected_rate
    assert result["solar_kwh"] == 5.0
    assert result["savings_pkr"] == round(5.0 * expected_rate, 2)
