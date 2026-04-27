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
