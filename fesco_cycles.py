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
