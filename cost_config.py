"""Persistence for cost-savings configuration.

Single-row JSON-blob table in the same SQLite DB as power_stats. Keeping it
dead simple: one config object stored as TEXT, loaded once and rewritten on
every save. The schema rarely changes (it's freeform user-editable settings),
so a typed-column table would just be friction every time the user wants to
tweak a slab.
"""

from __future__ import annotations

import json
import sqlite3
import logging
import threading
from typing import Any

import lesco_tariff


logger = logging.getLogger(__name__)


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


class CostConfig:
    """Thread-safe single-row config store. Reads are cached in memory; writes
    go through the lock and refresh the cache."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS cost_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    config_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            ''')
            conn.commit()

    def _build_default(self) -> dict[str, Any]:
        cfg = lesco_tariff.default_config()
        cfg.update(DEFAULT_NON_TARIFF)
        return cfg

    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return dict(self._cache)
            try:
                with sqlite3.connect(self.db_path) as conn:
                    row = conn.execute(
                        'SELECT config_json FROM cost_config WHERE id = 1'
                    ).fetchone()
                if row and row[0]:
                    stored = json.loads(row[0])
                    merged = self._build_default()
                    merged.update(stored)
                    self._cache = merged
                else:
                    self._cache = self._build_default()
            except Exception as e:
                logger.error(f"cost_config load failed: {e}")
                self._cache = self._build_default()
            return dict(self._cache)

    def save(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge `patch` into the current config and persist. Returns the new
        full config so the UI can render the updated state in a single round-trip."""
        if not isinstance(patch, dict):
            raise ValueError("config patch must be an object")
        with self._lock:
            current = self._cache if self._cache is not None else self.load()
            merged = dict(current)
            for k, v in patch.items():
                merged[k] = v
            blob = json.dumps(merged)
            import time as _time
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO cost_config (id, config_json, updated_at) VALUES (1, ?, ?)',
                    (blob, int(_time.time())),
                )
                conn.commit()
            self._cache = merged
            return dict(merged)

    def reset(self) -> dict[str, Any]:
        with self._lock:
            fresh = self._build_default()
            blob = json.dumps(fresh)
            import time as _time
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO cost_config (id, config_json, updated_at) VALUES (1, ?, ?)',
                    (blob, int(_time.time())),
                )
                conn.commit()
            self._cache = fresh
            return dict(fresh)


_instance: CostConfig | None = None


def get_instance(db_path: str | None = None) -> CostConfig:
    global _instance
    if _instance is None:
        if db_path is None:
            import os
            db_path = os.path.join(os.path.dirname(__file__), 'data', 'power_stats.db')
        _instance = CostConfig(db_path)
    return _instance
