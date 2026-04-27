"""Shared pytest fixtures for the inverter-monitor test suite."""
from __future__ import annotations

import os
import sqlite3
import sys

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
