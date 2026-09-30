"""PowerStats: WAL mode, restart average seeding, and the solar-share definition."""
from __future__ import annotations

import sqlite3

import pytest
from freezegun import freeze_time

import power_stats


def _seed_day(db, **cols):
    keys = ', '.join(cols)
    marks = ', '.join('?' for _ in cols)
    with sqlite3.connect(db) as conn:
        conn.execute(f'INSERT OR REPLACE INTO daily_stats ({keys}) VALUES ({marks})', tuple(cols.values()))
        conn.commit()


def test_journal_mode_is_wal(tmp_path):
    db = str(tmp_path / 'ps.db')
    ps = power_stats.PowerStats(db, flush_interval=0.2)
    try:
        with sqlite3.connect(db) as conn:
            assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    finally:
        ps.cleanup()


def test_summary_solar_share_excludes_battery_absorption(tmp_path):
    # 2026-09-30 live numbers: 4.149 kWh solar, of which 1.286 kWh went into the battery
    # and none came back; solar served 2.863 kWh of the 7.35 kWh load (39%), not 56%.
    db = str(tmp_path / 'ps.db')
    ps = power_stats.PowerStats(db, flush_interval=0.2)
    try:
        _seed_day(db, date='2026-09-30', solar_energy=4149, grid_energy=4376, load_energy=7350,
                  battery_charge_energy=1286, battery_discharge_energy=0,
                  solar_max=1640, grid_max=5422, load_max=5533, battery_max=615)
        s = ps.get_summary('2026-09-30')
        assert s['solar_kwh'] == 4.149
        assert s['solar_to_load_kwh'] == pytest.approx(2.863, abs=1e-3)
        assert s['solar_fraction'] == pytest.approx(0.39, abs=0.005)
        assert s['self_sufficiency'] == pytest.approx(0.405, abs=0.005)
    finally:
        ps.cleanup()


def test_restart_seed_weight_is_elapsed_day_not_one_hour(tmp_path):
    # 20 Sep 2026: service restarted 17:05 with a stored 380 W solar average. Seeding one
    # hour of weight let the evening's zeros drag it to 59 W; the seed must carry ~17 h.
    db = str(tmp_path / 'ps.db')
    power_stats.PowerStats(db, flush_interval=0.2).cleanup()
    _seed_day(db, date='2026-09-20', solar_energy=6452, grid_energy=7319, load_energy=12739,
              solar_avg=380.0, grid_avg=383.0, load_avg=515.0,
              battery_charge_energy=0, battery_discharge_energy=0)
    with freeze_time('2026-09-20 17:05:00'):
        ps = power_stats.PowerStats(db, flush_interval=0.2)
    try:
        elapsed = 17 * 3600 + 5 * 60
        assert ps.current_day['solar']['tsum'] == pytest.approx(elapsed)
        assert ps.current_day['solar']['wsum'] / ps.current_day['solar']['tsum'] == pytest.approx(380.0)
        # Seven more hours of zero solar must only pull the average to ~269 W, not 59 W.
        ps.current_day['solar']['tsum'] += 7 * 3600
        assert ps.current_day['solar']['wsum'] / ps.current_day['solar']['tsum'] == pytest.approx(268.8, abs=1.0)
    finally:
        ps.cleanup()
