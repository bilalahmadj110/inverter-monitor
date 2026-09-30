"""Tests for the mode-gated grid-power estimate in inverter_status._derive_grid_power.

Grid power is not measured by PI30; it is the energy-balance residual, gated on the
inverter's operating mode. In Battery mode the grid feeds nothing, so the residual is
noise and must read 0. In Line mode (this unit runs Line mode with PV assist almost
always) the residual is real grid draw and must be reported, with the PV->load
conversion loss accounted for.
"""
import pytest

from inverter_status import (
    GRID_MIN_REPORT_W,
    INVERTER_EFFICIENCY,
    _derive_grid_power,
    _derive_mode_from_flags,
)


def _metrics(load=0.0, solar=0.0, charge_a=0.0, discharge_a=0.0, batt_v=27.0,
             grid_v=223.0, grid_f=49.7, out_v=None, out_f=None, ac_charging=False,
             mode='L', switched_on=True):
    return {
        'load': {'active_power': load,
                 'voltage': grid_v if out_v is None else out_v,
                 'frequency': grid_f if out_f is None else out_f},
        'solar': {'power': solar},
        'battery': {'charging_current': charge_a, 'discharge_current': discharge_a,
                    'voltage': batt_v},
        'grid': {'voltage': grid_v, 'frequency': grid_f},
        'system': {'is_ac_charging_on': ac_charging, 'mode': mode,
                   'is_switched_on': switched_on},
    }


def test_line_mode_pv_assist_reports_real_shortfall():
    # Live sample 2026-09-30: load 528 W, PV 431 W, battery idle, QMOD=L. The old 100 W
    # deadband reported 0 here while the meter was drawing ~130 W.
    est = _derive_grid_power({}, _metrics(load=528, solar=431, mode='L'))
    assert est == pytest.approx(528 - 431 * INVERTER_EFFICIENCY, abs=0.1)


def test_battery_mode_reports_zero_regardless_of_residual():
    assert _derive_grid_power({}, _metrics(load=680, solar=600, mode='B')) == 0.0
    assert _derive_grid_power({}, _metrics(load=636, solar=0, discharge_a=20, mode='B')) == 0.0


def test_grid_absent_returns_zero():
    assert _derive_grid_power({}, _metrics(load=636, solar=0, grid_v=0, mode='L')) == 0.0


def test_night_line_mode_passes_full_load():
    assert _derive_grid_power({}, _metrics(load=636, solar=0, mode='L')) == 636.0


def test_pv_surplus_clamps_to_zero():
    assert _derive_grid_power({}, _metrics(load=500, solar=700, mode='L')) == 0.0


def test_tiny_residual_below_resolution_reads_zero():
    # 1 A of battery quantisation at 24 V is ~27 W; residuals inside that are noise.
    solar = (500 - GRID_MIN_REPORT_W + 5) / INVERTER_EFFICIENCY
    assert _derive_grid_power({}, _metrics(load=500, solar=solar, mode='L')) == 0.0


def test_pv_charging_battery_is_not_billed_to_grid():
    # Morning: PV 800 W, of which 500 W (DC) goes into the battery; the rest assists the load.
    est = _derive_grid_power({}, _metrics(load=600, solar=800, charge_a=500 / 27.0, mode='L'))
    solar_to_batt = 500 / 0.97
    expected = 600 - (800 - solar_to_batt) * INVERTER_EFFICIENCY
    assert est == pytest.approx(expected, abs=0.5)


def test_ac_charging_adds_charger_draw_and_bypasses_floor():
    m = _metrics(load=50, solar=0, charge_a=1.0, batt_v=27.0, ac_charging=True, mode='L')
    assert _derive_grid_power({}, m) == pytest.approx(50 + 27 / INVERTER_EFFICIENCY, abs=0.1)


def test_unknown_mode_falls_back_to_residual():
    assert _derive_grid_power({}, _metrics(load=400, solar=0, mode=None)) == 400.0


# --- derived-mode fallback (QMOD unavailable or stale) --------------------------------

def test_derived_mode_bypass_signature_is_line_mode():
    m = _metrics(load=528, solar=431, grid_v=222.9, grid_f=49.7, out_v=222.9, out_f=49.7, mode=None)
    assert _derive_mode_from_flags(m) == 'L'


def test_derived_mode_regulated_output_with_grid_present_is_battery_mode():
    m = _metrics(load=528, solar=431, grid_v=222.9, grid_f=49.7, out_v=230.0, out_f=50.0, mode=None)
    assert _derive_mode_from_flags(m) == 'B'


def test_derived_mode_grid_absent_with_load_is_battery_mode():
    m = _metrics(load=400, solar=0, grid_v=0, grid_f=0, out_v=230.0, out_f=50.0, mode=None)
    assert _derive_mode_from_flags(m) == 'B'


def test_derived_mode_idle_without_grid_is_standby():
    m = _metrics(load=0, solar=0, grid_v=0, grid_f=0, out_v=0, out_f=0, mode=None)
    assert _derive_mode_from_flags(m) == 'S'


def test_derived_mode_switched_off():
    assert _derive_mode_from_flags(_metrics(mode=None, switched_on=False)) == 'D'
