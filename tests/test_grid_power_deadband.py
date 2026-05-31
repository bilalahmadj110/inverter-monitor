"""Tests for the derived grid-power deadband in inverter_status._derive_grid_power.

Grid power is not measured; it's an energy-balance residual clamped to >=0, which
rectifies measurement noise into a phantom positive draw. The deadband suppresses
that phantom while leaving genuine (large) grid draw untouched.
"""
from inverter_status import (
    GRID_NOISE_FLOOR_W,
    _derive_grid_power,
)


def _metrics(load=0.0, solar=0.0, charge_a=0.0, discharge_a=0.0,
             batt_v=50.0, grid_v=230.0, ac_charging=False):
    return {
        'load': {'active_power': load},
        'solar': {'power': solar},
        'battery': {'charging_current': charge_a, 'discharge_current': discharge_a,
                    'voltage': batt_v},
        'grid': {'voltage': grid_v},
        'system': {'is_ac_charging_on': ac_charging},
    }


def test_phantom_daytime_draw_suppressed():
    # Solar nearly balances load -> tiny residual (~80 W) is noise, not real draw.
    assert _derive_grid_power({}, _metrics(load=680, solar=600)) == 0.0


def test_real_night_draw_passes_through():
    # Night: no solar, battery idle, full load must be reported (well above floor).
    assert _derive_grid_power({}, _metrics(load=636, solar=0)) > 600


def test_deadband_scales_with_throughput():
    # At high throughput the floor isn't enough; a ~150 W residual on 4 kW of
    # combined load+solar is still within the proportional noise band.
    assert _derive_grid_power({}, _metrics(load=2150, solar=2000)) == 0.0
    # The same 150 W residual at low throughput is above the floor -> real.
    assert _derive_grid_power({}, _metrics(load=150, solar=0)) > GRID_NOISE_FLOOR_W


def test_ac_charging_bypasses_deadband():
    # When AC-charging the grid is definitely in use; small estimates count.
    m = _metrics(load=50, solar=0, charge_a=1.0, batt_v=50.0, ac_charging=True)
    assert _derive_grid_power({}, m) > 0.0


def test_grid_absent_returns_zero():
    assert _derive_grid_power({}, _metrics(load=636, solar=0, grid_v=0)) == 0.0
