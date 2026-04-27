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
