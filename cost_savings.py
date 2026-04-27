"""Cost-savings service.

Joins energy stats from power_stats with the LESCO tariff to derive:
  - Today's savings (PKR), based on today's solar production at marginal rate
  - This month's savings, computed as bill_without_solar - bill_with_solar
    (this is the only honest way — monthly slabs make it non-additive)
  - Lifetime savings since system_start_date
  - Slab projector: where this month's grid usage is trending and what cliff
    the user is approaching
  - Payback estimator: months/years to recoup install cost

All numbers are in PKR. Everything reads tariff config from CostConfig so the
user can edit any rate from the UI and savings recalc on the next request.
"""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, date
from typing import Any

import lesco_tariff


logger = logging.getLogger(__name__)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _month_energy_kwh(db_path: str, month: str) -> dict[str, float]:
    """Sum daily energy rows for a calendar month YYYY-MM. Returns kWh values."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            '''
            SELECT
                COALESCE(SUM(solar_energy), 0) AS solar_wh,
                COALESCE(SUM(grid_energy),  0) AS grid_wh,
                COALESCE(SUM(load_energy),  0) AS load_wh
            FROM daily_stats
            WHERE substr(date, 1, 7) = ?
            ''',
            (month,),
        ).fetchone()
    return {
        "solar_kwh": (row["solar_wh"] or 0) / 1000.0,
        "grid_kwh":  (row["grid_wh"]  or 0) / 1000.0,
        "load_kwh":  (row["load_wh"]  or 0) / 1000.0,
    }


def _day_energy_kwh(stats_manager, day: str | None = None) -> dict[str, float]:
    summary = stats_manager.get_summary(day)
    if not summary:
        return {"solar_kwh": 0.0, "grid_kwh": 0.0, "load_kwh": 0.0}
    return {
        "solar_kwh": float(summary.get("solar_kwh") or 0),
        "grid_kwh":  float(summary.get("grid_kwh")  or 0),
        "load_kwh":  float(summary.get("load_kwh")  or 0),
    }


def compute_savings_for_month(db_path: str, month: str, config: dict[str, Any]) -> dict[str, Any]:
    """Solar savings for a calendar month: difference between the bill the
    house *would* have paid (all load from grid) and the bill it *did* pay
    (only grid_kwh from grid)."""
    energy = _month_energy_kwh(db_path, month)
    bill_without = lesco_tariff.compute_bill(energy["load_kwh"], config)
    bill_with    = lesco_tariff.compute_bill(energy["grid_kwh"], config)
    savings = bill_without["total"] - bill_with["total"]
    return {
        "month": month,
        "energy": {k: round(v, 3) for k, v in energy.items()},
        "bill_without_solar": bill_without,
        "bill_with_solar": bill_with,
        "savings_pkr": round(savings, 2),
    }


def _cycle_energy_kwh(db_path: str, start: date, end: date) -> dict[str, float]:
    """SUM daily_stats energy fields between start and end (inclusive)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            '''
            SELECT
                COALESCE(SUM(solar_energy), 0) AS solar_wh,
                COALESCE(SUM(grid_energy),  0) AS grid_wh,
                COALESCE(SUM(load_energy),  0) AS load_wh
            FROM daily_stats
            WHERE date BETWEEN ? AND ?
            ''',
            (start.isoformat(), end.isoformat()),
        ).fetchone()
    return {
        "solar_kwh": (row["solar_wh"] or 0) / 1000.0,
        "grid_kwh":  (row["grid_wh"]  or 0) / 1000.0,
        "load_kwh":  (row["load_wh"]  or 0) / 1000.0,
    }


def compute_savings_for_cycle(
    db_path: str, start: date, end: date, config: dict[str, Any]
) -> dict[str, Any]:
    """Solar savings for a billing cycle (date range). Same formula as
    compute_savings_for_month but with explicit start/end bounds."""
    energy = _cycle_energy_kwh(db_path, start, end)
    bill_without = lesco_tariff.compute_bill(energy["load_kwh"], config)
    bill_with    = lesco_tariff.compute_bill(energy["grid_kwh"], config)
    savings = bill_without["total"] - bill_with["total"]
    return {
        "start": start.isoformat(),
        "end":   end.isoformat(),
        "energy": {k: round(v, 3) for k, v in energy.items()},
        "bill_without_solar": bill_without,
        "bill_with_solar": bill_with,
        "savings_pkr": round(savings, 2),
    }


def compute_today(stats_manager, config: dict[str, Any]) -> dict[str, Any]:
    """Today's savings, valued at the *current marginal rate* — i.e. the rate
    of the next grid unit you'd consume given the month's grid usage so far.
    This correctly captures the slab cliff: if you're at 199 units, the next
    unit is worth Rs 28+ instead of Rs 22, so today's solar is worth more."""
    today = datetime.now().strftime('%Y-%m-%d')
    month = today[:7]
    day_energy = _day_energy_kwh(stats_manager, today)
    month_energy = _month_energy_kwh(stats_manager.db_path, month)

    rate_now = lesco_tariff.marginal_rate(month_energy["grid_kwh"], config)
    today_savings = day_energy["solar_kwh"] * rate_now

    return {
        "date": today,
        "solar_kwh": round(day_energy["solar_kwh"], 3),
        "grid_kwh":  round(day_energy["grid_kwh"], 3),
        "load_kwh":  round(day_energy["load_kwh"], 3),
        "marginal_rate_pkr_per_kwh": rate_now,
        "savings_pkr": round(today_savings, 2),
    }


def compute_lifetime(db_path: str, config: dict[str, Any], system_start_date: str | None) -> dict[str, Any]:
    """Sum monthly savings since system_start_date. If start date isn't set,
    fall back to the earliest date in daily_stats."""
    start = None
    if system_start_date:
        try:
            start = datetime.strptime(system_start_date, '%Y-%m-%d').date()
        except ValueError:
            start = None
    if start is None:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute('SELECT MIN(date) FROM daily_stats').fetchone()
            if row and row[0]:
                try:
                    start = datetime.strptime(row[0], '%Y-%m-%d').date()
                except ValueError:
                    start = None
    if start is None:
        return {
            "system_start_date": None,
            "days_elapsed": 0,
            "total_savings_pkr": 0,
            "total_solar_kwh": 0,
            "avg_daily_savings_pkr": 0,
            "months": [],
        }

    today = date.today()
    months_set: list[str] = []
    cur = date(start.year, start.month, 1)
    while cur <= today:
        months_set.append(cur.strftime('%Y-%m'))
        cur = (date(cur.year + (1 if cur.month == 12 else 0),
                    1 if cur.month == 12 else cur.month + 1, 1))

    months = []
    total_savings = 0.0
    total_solar = 0.0
    for m in months_set:
        result = compute_savings_for_month(db_path, m, config)
        months.append({
            "month": m,
            "solar_kwh": result["energy"]["solar_kwh"],
            "grid_kwh":  result["energy"]["grid_kwh"],
            "load_kwh":  result["energy"]["load_kwh"],
            "savings_pkr": result["savings_pkr"],
        })
        total_savings += result["savings_pkr"]
        total_solar += result["energy"]["solar_kwh"]

    days_elapsed = max(1, (today - start).days + 1)
    return {
        "system_start_date": start.isoformat(),
        "days_elapsed": days_elapsed,
        "total_savings_pkr": round(total_savings, 2),
        "total_solar_kwh": round(total_solar, 3),
        "avg_daily_savings_pkr": round(total_savings / days_elapsed, 2),
        "months": months,
    }


def compute_payback(install_cost_pkr: float, avg_daily_savings_pkr: float) -> dict[str, Any]:
    """Months and years to recoup install cost at current daily-savings pace."""
    install_cost = max(0.0, float(install_cost_pkr or 0))
    daily = max(0.0, float(avg_daily_savings_pkr or 0))
    if install_cost <= 0:
        return {
            "install_cost_pkr": 0,
            "avg_daily_savings_pkr": daily,
            "payback_days": None,
            "payback_months": None,
            "payback_years": None,
            "status": "set_install_cost",
        }
    if daily <= 0:
        return {
            "install_cost_pkr": install_cost,
            "avg_daily_savings_pkr": 0,
            "payback_days": None,
            "payback_months": None,
            "payback_years": None,
            "status": "no_savings_yet",
        }
    days = install_cost / daily
    return {
        "install_cost_pkr": round(install_cost, 2),
        "avg_daily_savings_pkr": round(daily, 2),
        "payback_days": round(days, 1),
        "payback_months": round(days / 30.4375, 2),
        "payback_years": round(days / 365.25, 2),
        "status": "ok",
    }


def compute_slab_projection(db_path: str, config: dict[str, Any]) -> dict[str, Any]:
    """For the *current* billing month, project month-end grid kWh assuming the
    same daily-average grid usage continues. Identify the slab the projection
    lands in and how many kWh stand between current usage and the next cliff.

    For unprotected consumers this is the single most actionable number on the
    dashboard: crossing 200 kWh roughly doubles your per-unit price.
    """
    today = date.today()
    month = today.strftime('%Y-%m')
    energy = _month_energy_kwh(db_path, month)
    days_in_month = _days_in_month(today.year, today.month)
    days_elapsed = today.day
    days_remaining = max(0, days_in_month - days_elapsed)

    grid_so_far = energy["grid_kwh"]
    daily_grid_rate = grid_so_far / days_elapsed if days_elapsed > 0 else 0
    projected_month_end = grid_so_far + daily_grid_rate * days_remaining

    bill_now = lesco_tariff.compute_bill(grid_so_far, config)
    bill_projected = lesco_tariff.compute_bill(projected_month_end, config)

    slab_now = bill_now.get("slab_info") or {}
    slab_proj = bill_projected.get("slab_info") or {}

    # If projection crosses into a new (worse) slab, surface a clear warning.
    cliff = None
    if slab_proj and slab_now and slab_proj.get("current_label") != slab_now.get("current_label"):
        # Find the immediately-next slab from current.
        cur_upper = slab_now.get("upper_edge")
        if cur_upper is not None:
            kwh_to_next = max(0.0, cur_upper - grid_so_far)
            # What's the rate jump going to be?
            jump_rate = (slab_proj.get("current_rate") or 0) - (slab_now.get("current_rate") or 0)
            cliff = {
                "current_slab": slab_now.get("current_label"),
                "next_slab": slab_proj.get("current_label"),
                "kwh_until_cliff": round(kwh_to_next, 2),
                "rate_jump_pkr_per_kwh": round(jump_rate, 2),
                "expected_overshoot_kwh": round(max(0.0, projected_month_end - cur_upper), 2),
            }

    return {
        "month": month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "grid_kwh_so_far": round(grid_so_far, 2),
        "daily_grid_rate_kwh": round(daily_grid_rate, 2),
        "projected_month_end_grid_kwh": round(projected_month_end, 2),
        "current_slab": slab_now,
        "projected_slab": slab_proj,
        "cliff_alert": cliff,
        "projected_bill_total_pkr": bill_projected["total"],
    }


def build_full_payload(stats_manager, cost_config) -> dict[str, Any]:
    """One-shot payload for the savings page: today + this cycle + lifetime
    + slab projection + payback. The frontend gets everything in a single GET.
    """
    import fesco_bill
    import fesco_cycles

    cfg = cost_config.load()
    today_block = compute_today(stats_manager, cfg)

    today = date.today()
    start, end = fesco_bill.compute_cycle_boundaries(today, cfg, stats_manager.db_path)
    cycle_block = compute_savings_for_cycle(stats_manager.db_path, start, end, cfg)
    cycle_block["label"] = fesco_bill.cycle_label_for(end)
    # Back-compat: front-end JS reads `m.month` for the cycle label.
    cycle_block["month"] = cycle_block["label"]

    lifetime = compute_lifetime_from_cycles(stats_manager.db_path, cfg)
    payback = compute_payback(cfg.get("install_cost_pkr") or 0, lifetime["avg_daily_savings_pkr"])
    projection = compute_slab_projection(stats_manager.db_path, cfg)

    return {
        "config": cfg,
        "today": today_block,
        "cycle": cycle_block,
        # Back-compat alias for front-end JS that still reads payload.month.
        # Both keys point to the same dict — safe because this payload is
        # serialized once and never mutated.
        "month": cycle_block,
        "lifetime": lifetime,
        "payback": payback,
        "projection": projection,
    }


def compute_lifetime_from_cycles(db_path: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Walk the billing_cycles table for closed cycles and sum savings.
    Falls back to the calendar-month version if no cycles exist."""
    import fesco_cycles
    store = fesco_cycles.CycleStore(db_path)
    cycles = [c for c in store.list_cycles(limit=240) if c["status"] == "closed"]
    if not cycles:
        return compute_lifetime(db_path, cfg, cfg.get("system_start_date"))

    cycles.sort(key=lambda c: c["end_date"])  # oldest first
    months = []
    total_savings = 0.0
    total_solar = 0.0

    for c in cycles:
        # Reuse compute_savings_for_cycle for consistency with the cycle block.
        try:
            s = date.fromisoformat(c["start_date"])
            e = date.fromisoformat(c["end_date"])
        except (ValueError, TypeError):
            continue
        result = compute_savings_for_cycle(db_path, s, e, cfg)
        months.append({
            "month": c["cycle_label"],
            "solar_kwh": result["energy"]["solar_kwh"],
            "grid_kwh":  result["energy"]["grid_kwh"],
            "load_kwh":  result["energy"]["load_kwh"],
            "savings_pkr": result["savings_pkr"],
        })
        total_savings += result["savings_pkr"]
        total_solar += result["energy"]["solar_kwh"]

    first = date.fromisoformat(cycles[0]["start_date"])
    today = date.today()
    days_elapsed = max(1, (today - first).days + 1)

    return {
        "system_start_date": first.isoformat(),
        "days_elapsed": days_elapsed,
        "total_savings_pkr": round(total_savings, 2),
        "total_solar_kwh": round(total_solar, 3),
        "avg_daily_savings_pkr": round(total_savings / days_elapsed, 2),
        "months": months,
    }
