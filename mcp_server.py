#!/usr/bin/env python3
"""MCP server for the inverter dashboard.

Lets an MCP host (Claude Code, Claude Desktop, claude.ai, or any chatbot that speaks MCP) read the
live inverter state, the energy history and the FESCO bill forecast, and change the output /
charger source priority. It never opens /dev/hidraw0: everything goes through the Flask app's HTTP
API as a logged-in client, so the half-duplex PI30 bus keeps exactly one owner.

Configuration comes from the environment, or from KEY=VALUE lines in ~/.config/inverter-mcp.env
(override the path with INVERTER_MCP_ENV_FILE; the environment wins over the file):

  INVERTER_URL                      dashboard base URL (default http://127.0.0.1:5000)
  INVERTER_USERNAME                 dashboard login (default admin)
  INVERTER_PASSWORD                 dashboard password (required)
  INVERTER_MCP_READ_ONLY=1          register no tool that changes anything
  INVERTER_MCP_ALLOW_PARAM_WRITES=1 also expose set_inverter_parameter (battery voltages, charge
                                    currents, battery type, output frequency); off by default
  INVERTER_MCP_TRANSPORT            stdio (default) | streamable-http
  INVERTER_MCP_HOST / _PORT         bind address for streamable-http (default 127.0.0.1:8765)
  INVERTER_MCP_TOKEN                token every HTTP request must carry, as "Authorization: Bearer"
                                    or as the URL prefix /<token>/mcp; required unless bound to loopback
  INVERTER_MCP_ALLOWED_HOSTS        comma-separated Host header values accepted over HTTP

Run:
  python mcp_server.py                                   # stdio, for Claude Code / Claude Desktop
  python mcp_server.py --transport streamable-http --host 0.0.0.0 --port 8765
  python mcp_server.py --check                           # log in, read once, print a summary
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Annotated, Any, Literal

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pydantic import Field  # noqa: E402

from mcp.server import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ResourceError, ToolError  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from lib.app_client import AppError, InverterAppClient  # noqa: E402

log = logging.getLogger("inverter-mcp")


# ---- configuration ------------------------------------------------------------------------------

def _load_env_file(path: str) -> bool:
    """KEY=VALUE lines (comments and `export` allowed). Never overrides a variable already set."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


ENV_FILE = os.environ.get("INVERTER_MCP_ENV_FILE") or os.path.expanduser("~/.config/inverter-mcp.env")
ENV_FILE_LOADED = _load_env_file(ENV_FILE)

BASE_URL = os.environ.get("INVERTER_URL", "http://127.0.0.1:5000").rstrip("/")
USERNAME = os.environ.get("INVERTER_USERNAME", "admin")
PASSWORD = os.environ.get("INVERTER_PASSWORD", "")
READ_ONLY = _flag("INVERTER_MCP_READ_ONLY")
ALLOW_PARAM_WRITES = _flag("INVERTER_MCP_ALLOW_PARAM_WRITES") and not READ_ONLY

GRID_PRESENT_MIN_VOLTAGE = 180  # mirrors inverter_status.GRID_PRESENT_MIN_VOLTAGE
# After a priority write the dashboard re-reads QPIRI, but that re-read is debounced (5 s) and can hand
# back the old value; wait this long and force a fresh read before reporting "unconfirmed".
CONFIRM_RETRY_DELAY_S = 4.0
# get_recent_trend picks its bucket so a window comes back as about this many points: enough to see a
# trend, small enough not to flood the model's context (the dashboard default of 120 was ~40 KB for 30 min).
TREND_TARGET_POINTS = 30

# PI30 POP / PCP command set. Labels match the dashboard (inverter_status.py); tests check that.
OUTPUT_PRIORITIES = {
    "UTI": ("Utility first", "POP00", "Grid powers the load; battery and solar stay as backup."),
    "SOL": ("Solar first", "POP01",
            "Solar feeds the load first, then the grid; the battery is the last resort (used when the grid is out)."),
    "SBU": ("SBU", "POP02",
            "Solar → Battery → Utility: run from solar, then from the battery, and fall back to the grid only when "
            "the battery reaches its back-to-grid voltage. Maximises self-consumption, cycles the battery daily."),
}
CHARGER_PRIORITIES = {
    "UTI_SOL": ("Utility + Solar", "PCP00", "Grid and solar can both charge the battery."),
    "SOL_FIRST": ("Solar first", "PCP01", "Solar charges first; grid tops up if needed."),
    "SOL_UTI": ("Solar + Utility", "PCP02", "Both charge simultaneously when available."),
    "SOL_ONLY": ("Only solar", "PCP03", "Only solar is allowed to charge; grid never does."),
}
CONFIG_PARAMS = (
    "battery_type", "output_frequency", "cutoff_voltage", "back_to_grid_voltage", "back_to_battery_voltage",
    "bulk_voltage", "float_voltage", "max_charge_current", "max_ac_charge_current",
)

INSTRUCTIONS = """Tools for one home solar installation: a Voltronic / MPP-Solar style PI30 hybrid inverter
(3.6 kVA, 24 V battery bank) in Pakistan, fed by rooftop PV and backed by the FESCO grid, monitored by a
Raspberry Pi dashboard that this server talks to.

Vocabulary: "Line mode" means the load runs on the grid (with PV assisting); "Battery mode" means the load
runs on solar + battery. The output source priority decides which: SBU (Solar → Battery → Utility) maximises
self-consumption and drains the battery before touching the grid; Solar first (SOL) uses solar then grid and
keeps the battery for outages; Utility first (UTI) runs on the grid. The charger source priority decides what
may charge the battery (grid and solar, solar first, both, or only solar). PI30 never measures grid power:
the dashboard estimates it from the energy balance, so grid kWh and savings are estimates (get_bill_forecast
carries a calibration factor against the real meter).

Start with get_live_status for "what is it doing now" and get_inverter_settings for "how is it configured".
Changing a priority acts on the hardware immediately: say what the current value is and what will change
before calling set_output_priority / set_charger_priority, unless the user asked for exactly that change.
Bills are in Pakistani rupees (PKR); a FESCO billing cycle runs from about the 26th of one month to the 26th
of the next, and crossing 200 units in a cycle raises the per-unit rate for every unit in it."""

mcp = MCPServer(
    "inverter",
    title="Inverter Monitor",
    instructions=INSTRUCTIONS,
    version="1.0.0",
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


# ---- dashboard access ---------------------------------------------------------------------------

_client: InverterAppClient | None = None


def client() -> InverterAppClient:
    global _client
    if _client is None:
        if not PASSWORD:
            raise ToolError(
                f"INVERTER_PASSWORD is not set (environment or {ENV_FILE}); the MCP server cannot log in to the dashboard")
        _client = InverterAppClient(BASE_URL, USERNAME, PASSWORD)
    return _client


def _get(path: str, **params):
    try:
        return client().get(path, **params)
    except AppError as e:
        raise ToolError(f"dashboard replied {e.status}: {e.message}") from None
    except OSError as e:
        raise ToolError(f"cannot reach the dashboard at {BASE_URL}: {getattr(e, 'reason', e)}") from None


def _post(path: str, body=None):
    try:
        return client().post(path, body)
    except AppError as e:
        raise ToolError(f"dashboard replied {e.status}: {e.message}") from None
    except OSError as e:
        raise ToolError(f"cannot reach the dashboard at {BASE_URL}: {getattr(e, 'reason', e)}") from None


# ---- formatting helpers -------------------------------------------------------------------------

def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts)).isoformat(timespec="seconds") if ts else None
    except (TypeError, ValueError, OSError):
        return None


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _priority(table: dict, key) -> dict | None:
    if not key:
        return None
    if key in table:
        label, cmd, desc = table[key]
        return {"key": key, "label": label, "description": desc, "command": cmd}
    return {"key": key, "label": str(key), "description": None, "command": None}


def _options(table: dict) -> list[dict]:
    return [{"key": k, "label": v[0], "description": v[2]} for k, v in table.items()]


def _check_date(value: str | None, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ToolError(f"{name} must be YYYY-MM-DD, got {value!r}")
    return value


def _live_status(status: dict, cfg: dict) -> dict[str, Any]:
    m = status.get("metrics") or {}
    s = status.get("system") or {}
    t = status.get("timing") or {}
    grid, solar, batt, load = (m.get(k) or {} for k in ("grid", "solar", "battery", "load"))
    end = t.get("end_time")
    age = round(time.time() - float(end), 1) if end else None
    warnings = s.get("warnings") or []
    out_p = _priority(OUTPUT_PRIORITIES, cfg.get("output_priority"))
    chg_p = _priority(CHARGER_PRIORITIES, cfg.get("charger_priority"))
    batt_w = _num(batt.get("power"))
    direction = batt.get("direction") or "idle"
    if direction == "charging":
        batt_text = f"charging at {abs(batt_w):.0f} W"
    elif direction == "discharging":
        batt_text = f"discharging at {abs(batt_w):.0f} W"
    else:
        batt_text = "idle"
    grid_present = _num(grid.get("voltage")) >= GRID_PRESENT_MIN_VOLTAGE
    parts = [
        f"{s.get('mode_label') or 'Unknown mode'} ({'QMOD' if s.get('mode_source') == 'qmod' else 'derived'})",
        f"load {_num(load.get('power')):.0f} W",
        f"solar {_num(solar.get('power')):.0f} W",
        f"grid {_num(grid.get('power')):.0f} W est." + ("" if grid_present else " (grid absent)"),
        f"battery {batt.get('voltage')} V {batt.get('percentage')}% {batt_text}",
    ]
    if out_p:
        parts.append(f"output priority {out_p['label']}")
    if chg_p:
        parts.append(f"charger {chg_p['label']}")
    parts.append(f"{len(warnings)} warning(s): " + ", ".join(w.get("label", "?") for w in warnings) if warnings else "no warnings")
    if age is not None:
        parts.append(f"reading {age:.0f} s old")
    result: dict[str, Any] = {
        "summary": "; ".join(parts),
        "ok": bool(status.get("success")),
        "reading_time": _iso(end),
        "reading_age_seconds": age,
        "mode": {"code": s.get("mode"), "label": s.get("mode_label"), "source": s.get("mode_source")},
        "solar": {"power_w": solar.get("power"), "voltage_v": solar.get("voltage"), "current_a": solar.get("current")},
        "load": {
            "power_w": load.get("power"), "apparent_power_va": load.get("apparent_power"),
            "percent_of_capacity": load.get("percentage"), "voltage_v": load.get("voltage"),
            "frequency_hz": load.get("frequency"), "power_factor": load.get("power_factor"),
        },
        "grid": {
            "present": grid_present, "voltage_v": grid.get("voltage"), "frequency_hz": grid.get("frequency"),
            "power_w_estimated": grid.get("power"), "in_use": grid.get("in_use"),
        },
        "battery": {
            "voltage_v": batt.get("voltage"), "state_of_charge_percent": batt.get("percentage"),
            "current_a": batt.get("current"), "power_w": batt_w, "direction": direction,
            "charge_stage": s.get("charge_stage"),
        },
        "flags": {k: s.get(k) for k in ("is_load_on", "is_charging_on", "is_scc_charging_on", "is_ac_charging_on",
                                        "is_charging_to_float", "is_switched_on")},
        "heat_sink_temperature_c": s.get("temperature"),
        "bus_voltage_v": s.get("bus_voltage"),
        "warnings": warnings,
        "has_fault": bool(s.get("has_fault", False)),
        "output_priority": out_p,
        "charger_priority": chg_p,
        "notes": "Grid power is derived from the energy balance (load + AC charging − solar-to-load − battery "
                 "discharge) and is 0 by definition in Battery mode; treat it as an estimate.",
    }
    if not status.get("success"):
        result["error"] = status.get("error")
    return result


def _settings(cfg: dict, selectable: dict) -> dict[str, Any]:
    out_p = _priority(OUTPUT_PRIORITIES, cfg.get("output_priority")) or {"key": None, "label": "unknown"}
    chg_p = _priority(CHARGER_PRIORITIES, cfg.get("charger_priority")) or {"key": None, "label": "unknown"}
    summary = (
        f"Output priority {out_p['label']} ({out_p['key']}); charger {chg_p['label']} ({chg_p['key']}); "
        f"battery {cfg.get('battery_type')} {cfg.get('battery_nominal_voltage')} V: bulk {cfg.get('battery_bulk_charge_voltage')} V, "
        f"float {cfg.get('battery_float_charge_voltage')} V, cut-off {cfg.get('battery_under_voltage')} V, "
        f"back-to-grid {cfg.get('battery_recharge_voltage')} V, back-to-battery {cfg.get('battery_redischarge_voltage')} V; "
        f"max charge {cfg.get('max_charging_current')} A, max AC charge {cfg.get('max_ac_charging_current')} A; "
        f"output {cfg.get('ac_output_voltage')} V {cfg.get('ac_output_frequency')} Hz."
    )
    return {
        "summary": summary,
        "output_priority": out_p,
        "charger_priority": chg_p,
        "battery": {
            "type": cfg.get("battery_type"),
            "nominal_voltage_v": cfg.get("battery_nominal_voltage"),
            "bulk_charge_voltage_v": cfg.get("battery_bulk_charge_voltage"),
            "float_charge_voltage_v": cfg.get("battery_float_charge_voltage"),
            "cutoff_voltage_v": cfg.get("battery_under_voltage"),
            "back_to_grid_voltage_v": cfg.get("battery_recharge_voltage"),
            "back_to_battery_voltage_v": cfg.get("battery_redischarge_voltage"),
        },
        "charging": {
            "max_charge_current_a": cfg.get("max_charging_current"),
            "max_ac_charge_current_a": cfg.get("max_ac_charging_current"),
            "selectable_max_charge_current_a": selectable.get("max_charging_current"),
            "selectable_max_ac_charge_current_a": selectable.get("max_ac_charging_current"),
        },
        "output": {"voltage_v": cfg.get("ac_output_voltage"), "frequency_hz": cfg.get("ac_output_frequency")},
        "all_settings": [{"label": r.get("label"), "value": r.get("value"), "unit": r.get("unit")}
                         for r in (cfg.get("rows") or [])],
        "options": {"output_priority": _options(OUTPUT_PRIORITIES), "charger_priority": _options(CHARGER_PRIORITIES)},
        "writes_enabled": not READ_ONLY,
        "parameter_writes_enabled": ALLOW_PARAM_WRITES,
    }


def _pct(v) -> str:
    return f"{_num(v) * 100:.0f}%"


# ---- read tools ---------------------------------------------------------------------------------

@mcp.tool(annotations=READ)
def get_live_status() -> dict[str, Any]:
    """Current inverter reading: operating mode (Line / Battery / ...), solar, load, grid and battery
    power, battery voltage and state of charge, heat-sink temperature, active warnings, and the
    configured output / charger priorities. The dashboard refreshes readings about every 0.6 s;
    `reading_age_seconds` says how old this one is. Grid power is an estimate, not a measurement."""
    status = _get("/status")
    cfg = (_get("/config") or {}).get("config") or {}
    return _live_status(status, cfg)


@mcp.tool(annotations=READ)
def get_inverter_settings(
    refresh: Annotated[bool, Field(description="True re-reads the settings from the inverter (QPIRI) instead of "
                                               "returning the dashboard's cached copy; costs about a second of bus time.")] = False,
) -> dict[str, Any]:
    """Configured inverter settings: output source priority (SBU / Solar first / Utility first), charger
    source priority, battery type and voltage set-points, charge-current limits, output voltage and
    frequency, the full settings table, and the keys accepted by set_output_priority /
    set_charger_priority."""
    if refresh:
        cfg = (_post("/refresh-extras") or {}).get("config") or {}
    else:
        cfg = (_get("/config") or {}).get("config") or {}
    if not cfg:
        raise ToolError("the dashboard has not read the inverter settings yet; try again with refresh=true")
    try:
        selectable = _get("/inverter/selectable-currents") or {}
    except ToolError:
        selectable = {}
    return _settings(cfg, selectable)


@mcp.tool(annotations=READ)
def get_warnings(
    refresh: Annotated[bool, Field(description="True re-reads the warning flags (QPIWS) from the inverter.")] = False,
) -> dict[str, Any]:
    """Active inverter warnings and faults (PV loss, overload, battery low, over-temperature, fan locked,
    ...) with severity, plus the current operating mode."""
    if refresh:
        extras = _post("/refresh-extras") or {}
        warnings = extras.get("warnings") or []
        mode = extras.get("mode")
        has_fault = any(w.get("severity") == "fault" for w in warnings)
        mode_label = None
    else:
        data = _get("/warnings") or {}
        warnings = data.get("warnings") or []
        mode, mode_label, has_fault = data.get("mode"), data.get("mode_label"), bool(data.get("has_fault"))
    if warnings:
        summary = f"{len(warnings)} active: " + ", ".join(f"{w.get('label')} ({w.get('severity')})" for w in warnings)
    else:
        summary = "No active warnings or faults."
    return {"summary": summary, "warnings": warnings, "has_fault": has_fault, "mode": mode, "mode_label": mode_label,
            "severity_meaning": "fault = the inverter has stopped or will stop supplying the load; warning = degraded "
                                "condition, still running."}


@mcp.tool(annotations=READ)
def get_energy_summary(
    date: Annotated[str | None, Field(description="Day as YYYY-MM-DD; omit for today.")] = None,
) -> dict[str, Any]:
    """Energy totals for one day: solar, grid (estimated), load, battery charged / discharged in kWh,
    peak powers, self-sufficiency and solar fraction, maximum heat-sink temperature."""
    date = _check_date(date, "date")
    s = _get("/summary", date=date) or {}
    summary = (
        f"{s.get('date')}: load {s.get('load_kwh')} kWh, solar {s.get('solar_kwh')} kWh "
        f"({s.get('solar_to_load_kwh')} kWh of it to the load), grid {s.get('grid_kwh')} kWh (est.), "
        f"battery charged {s.get('battery_charge_kwh')} / discharged {s.get('battery_discharge_kwh')} kWh; "
        f"self-sufficiency {_pct(s.get('self_sufficiency'))}, solar fraction {_pct(s.get('solar_fraction'))}; "
        f"peaks: load {s.get('load_peak_w')} W, solar {s.get('solar_peak_w')} W, grid {s.get('grid_peak_w')} W."
    )
    return {"summary": summary, **s,
            "units": "kWh for energy, W for peaks; self_sufficiency and solar_fraction are ratios 0–1."}


@mcp.tool(annotations=READ)
def get_daily_history(
    days: Annotated[int, Field(ge=1, le=365, description="Number of days back from today, inclusive.")] = 7,
) -> dict[str, Any]:
    """Per-day energy history (kWh) for the last N days: solar, grid (estimated), load, battery charged
    and discharged, plus totals and daily averages over the window."""
    rows = _get("/history", days=days) or []
    out_rows = [{
        "date": r.get("date"), "solar_kwh": r.get("solar_energy"), "grid_kwh": r.get("grid_energy"),
        "load_kwh": r.get("load_energy"), "battery_charge_kwh": r.get("battery_charge_energy"),
        "battery_discharge_kwh": r.get("battery_discharge_energy"),
    } for r in rows]
    totals = {k: round(sum(_num(r.get(k)) for r in out_rows), 2)
              for k in ("solar_kwh", "grid_kwh", "load_kwh", "battery_charge_kwh", "battery_discharge_kwh")}
    n = len(out_rows) or 1
    averages = {k: round(v / n, 2) for k, v in totals.items()}
    summary = (f"{len(out_rows)} day(s): total load {totals['load_kwh']} kWh, solar {totals['solar_kwh']} kWh, "
               f"grid {totals['grid_kwh']} kWh (est.); daily average load {averages['load_kwh']}, solar "
               f"{averages['solar_kwh']}, grid {averages['grid_kwh']} kWh.")
    return {"summary": summary, "days_requested": days, "rows": out_rows, "totals": totals, "daily_average": averages}


@mcp.tool(annotations=READ)
def get_recent_trend(
    minutes: Annotated[int, Field(ge=1, le=1440, description="Window length ending now.")] = 30,
    bucket_seconds: Annotated[int | None, Field(ge=10, le=3600, description="Averaging bucket; omit for about 30 "
                                                                              "points over the window (60 s minimum).")] = None,
) -> dict[str, Any]:
    """Recent power trend: time-bucketed average solar, load, grid (estimated) and battery power, the load
    peak per bucket, battery state of charge and grid voltage over the last N minutes. Use it for 'what
    happened in the last hour' or to see whether the battery is draining."""
    if bucket_seconds is None:
        bucket_seconds = min(3600, max(60, (minutes * 60) // TREND_TARGET_POINTS))
    data = _get("/recent-readings", minutes=minutes, bucket=bucket_seconds) or {}
    points = []
    for p in data.get("points") or []:
        points.append({
            "time": _iso(p.get("timestamp")),
            "solar_w": p.get("solar_avg"), "load_w": p.get("load_avg"), "load_w_peak": p.get("load_max"),
            "grid_w_estimated": p.get("grid_avg"), "battery_w": p.get("battery_avg"),
            "battery_percent": p.get("battery_percentage"), "grid_voltage_v": p.get("grid_voltage"),
        })
    if points:
        loads = [_num(p["load_w"]) for p in points]
        solars = [_num(p["solar_w"]) for p in points]
        first, last = points[0], points[-1]
        summary = (f"Last {minutes} min in {len(points)} buckets of {data.get('bucket_seconds')} s: load avg "
                   f"{sum(loads) / len(loads):.0f} W (min {min(loads):.0f}, max {max(loads):.0f}), solar avg "
                   f"{sum(solars) / len(solars):.0f} W (max {max(solars):.0f}); battery {first.get('battery_percent')}% → "
                   f"{last.get('battery_percent')}%.")
    else:
        summary = f"No readings in the last {minutes} minutes."
    return {"summary": summary, "minutes": minutes, "bucket_seconds": data.get("bucket_seconds"),
            "points": points, "sign_convention": "battery_w is negative while discharging, positive while charging."}


@mcp.tool(annotations=READ)
def get_grid_outages(
    from_date: Annotated[str | None, Field(description="Start day YYYY-MM-DD (default: about a week ago).")] = None,
    to_date: Annotated[str | None, Field(description="End day YYYY-MM-DD (default: today).")] = None,
) -> dict[str, Any]:
    """Grid outages (load-shedding) detected from the grid voltage: start, end and duration of each,
    total downtime and grid availability over the range."""
    f = _check_date(from_date, "from_date")
    t = _check_date(to_date, "to_date")
    params = {}
    if f:
        params["from"] = f
    if t:
        params["to"] = t
    data = _get("/outages", **params) or {}
    outages = [{
        "start": _iso(o.get("start")), "end": _iso(o.get("end")),
        "duration_minutes": round(_num(o.get("duration_seconds")) / 60, 1),
    } for o in data.get("outages") or []]
    total_min = round(_num(data.get("total_down_seconds")) / 60, 1)
    summary = (f"{data.get('count', len(outages))} outage(s) between {data.get('from')} and {data.get('to')}, "
               f"{total_min} minutes without grid in total, availability {_pct(data.get('availability'))}.")
    return {"summary": summary, "from": data.get("from"), "to": data.get("to"), "count": data.get("count", len(outages)),
            "total_down_minutes": total_min, "availability": data.get("availability"), "outages": outages}


@mcp.tool(annotations=READ)
def get_savings() -> dict[str, Any]:
    """Money saved by the solar system in PKR: today, the current FESCO billing cycle (bill with solar
    versus without), lifetime since installation, payback progress, and the projected cycle-end grid
    units with the slab-cliff alert (crossing 200 units raises the rate on every unit)."""
    d = _get("/savings/data") or {}
    today = d.get("today") or {}
    cycle = d.get("cycle") or {}
    lifetime = d.get("lifetime") or {}
    payback = d.get("payback") or {}
    proj = d.get("projection") or {}
    with_solar = (cycle.get("bill_with_solar") or {})
    without = (cycle.get("bill_without_solar") or {})
    cliff = proj.get("cliff_alert") or {}
    summary = (
        f"Today saved Rs {today.get('savings_pkr')} (avoided {today.get('avoided_grid_kwh')} kWh of grid at "
        f"Rs {today.get('marginal_rate_pkr_per_kwh')}/kWh). Cycle {cycle.get('label')} ({cycle.get('start')} → "
        f"{cycle.get('end')}): bill with solar Rs {with_solar.get('total')} vs Rs {without.get('total')} without, "
        f"saving Rs {cycle.get('savings_pkr')}. Lifetime Rs {lifetime.get('total_savings_pkr')} over "
        f"{lifetime.get('days_elapsed')} days (avg Rs {lifetime.get('avg_daily_savings_pkr')}/day); payback "
        f"{payback.get('payback_years')} years on Rs {payback.get('install_cost_pkr')}. Projected cycle-end grid "
        f"{proj.get('projected_month_end_grid_kwh')} kWh (so far {proj.get('grid_kwh_so_far')}, "
        f"{proj.get('days_remaining')} days left), projected bill Rs {proj.get('projected_bill_total_pkr')}."
    )
    if cliff:
        summary += (f" Slab alert: {cliff.get('kwh_until_cliff')} kWh until the {cliff.get('next_slab')} slab, "
                    f"expected overshoot {cliff.get('expected_overshoot_kwh')} kWh "
                    f"(+Rs {cliff.get('rate_jump_pkr_per_kwh')}/kWh on every unit).")
    return {
        "summary": summary,
        "today": today,
        "cycle": {
            "label": cycle.get("label"), "start": cycle.get("start"), "end": cycle.get("end"),
            "energy_kwh": cycle.get("energy"), "savings_pkr": cycle.get("savings_pkr"),
            "bill_with_solar_pkr": with_solar.get("total"), "bill_without_solar_pkr": without.get("total"),
            "slab_with_solar": with_solar.get("slab_info"), "slab_without_solar": without.get("slab_info"),
        },
        "lifetime": {k: lifetime.get(k) for k in ("total_savings_pkr", "avg_daily_savings_pkr", "days_elapsed",
                                                  "total_solar_kwh", "system_start_date")},
        "lifetime_by_cycle": lifetime.get("months"),
        "payback": payback,
        "projection": proj,
        "notes": "Grid kWh here is the inverter's energy-balance estimate; the meter has tended to read higher "
                 "(see calibration in get_bill_forecast).",
    }


@mcp.tool(annotations=READ)
def get_bill_forecast() -> dict[str, Any]:
    """FESCO electricity bill for the open billing cycle: units so far, daily average, projected units
    and projected bill in PKR, slab position, reading and due dates, protected / unprotected consumer
    status, the inverter-estimate-vs-meter calibration factor, and the last billed cycles."""
    d = _get("/fesco/bill") or {}
    if d.get("error"):
        raise ToolError(f"dashboard: {d['error']}")
    cycle = d.get("cycle") or {}
    fc = d.get("forecast") or {}
    bill = d.get("bill_breakdown") or {}
    hdr = d.get("header") or {}
    status = d.get("status") or {}
    cal = d.get("calibration") or {}
    slab = bill.get("slab_info") or {}
    history = [{
        "cycle": h.get("label"), "start": h.get("start_date"), "end": h.get("end_date"), "units": h.get("units"),
        "bill_pkr": h.get("bill_amount"), "paid_pkr": h.get("paid"), "from_meter": h.get("is_actual"),
    } for h in (d.get("history") or [])[:6]]
    to_next = slab.get("units_to_next_slab")
    next_slab_text = f", {round(_num(to_next), 1)} units below the next slab" if to_next is not None else ""
    summary = (
        f"Cycle {cycle.get('cycle_label')} ({cycle.get('start_date')} → {cycle.get('end_date')}, reading date "
        f"{hdr.get('reading_date')}, due {hdr.get('due_date')}): {fc.get('units_so_far')} units in {fc.get('days_elapsed')} "
        f"days ({fc.get('daily_avg_kwh')}/day), {fc.get('days_remaining')} days left; projected {fc.get('projected_units')} "
        f"units → about Rs {bill.get('total')} in the {slab.get('current_label')} slab at Rs {slab.get('current_rate')}/unit"
        f"{next_slab_text}. "
        f"Same cycle last year: {fc.get('same_month_last_year_units')} units. Consumer status: {status.get('status')} "
        f"({status.get('reason')}). Meter / estimate calibration factor {cal.get('factor')}."
    )
    return {
        "summary": summary,
        "cycle": {k: cycle.get(k) for k in ("cycle_label", "start_date", "end_date", "status")},
        "dates": {k: hdr.get(k) for k in ("reading_date", "due_date", "lp_phase_2_date")},
        "forecast": {k: fc.get(k) for k in ("units_so_far", "days_elapsed", "days_remaining", "total_days",
                                            "daily_avg_kwh", "projected_units", "same_month_last_year_label",
                                            "same_month_last_year_units")},
        "projected_bill": {
            "total_pkr": bill.get("total"), "units": bill.get("units"), "effective_rate_per_unit": bill.get("effective_rate_per_unit"),
            "slab": slab, "energy_charge": bill.get("energy_charge"), "fpa": bill.get("fpa"),
            "fc_surcharge": bill.get("fc_surcharge"), "gst": bill.get("gst"), "electricity_duty": bill.get("electricity_duty"),
            "tv_fee": bill.get("tv_fee"), "fix_charges": bill.get("fix_charges"),
        },
        "late_payment_surcharge": d.get("lp_surcharge"),
        "consumer_status": status,
        "calibration": cal,
        "recent_cycles": history,
        "account": {k: hdr.get(k) for k in ("discom_name", "tariff_code", "load_kw", "consumer_id", "meter_no")},
        "notes": "Units so far are the inverter's grid estimate; multiply by the calibration factor for a "
                 "meter-like figure. Projected bill uses the configured tariff and may run high.",
    }


@mcp.tool(annotations=READ)
def get_system_health() -> dict[str, Any]:
    """Health of the monitoring itself: dashboard version, whether the reader thread is running, total
    readings, error rate, when the last reading arrived and how fresh the operating-mode poll is. Use
    it when readings look stale or the dashboard seems unresponsive."""
    health = _get("/healthz") or {}
    payload = _get("/stats-payload") or {}
    rs = payload.get("reading_stats") or {}
    last = rs.get("last_reading_time")
    last_age = round(time.time() - float(last), 1) if last else None
    err_rate = _num(rs.get("error_rate"))
    issues = []
    if not rs.get("running"):
        issues.append("reader thread not running")
    if last_age is None or last_age > 30:
        issues.append(f"last reading {last_age} s ago" if last_age is not None else "no reading yet")
    if err_rate > 0.05:
        issues.append(f"error rate {err_rate * 100:.1f}%")
    summary = (f"Dashboard {health.get('version')} at {BASE_URL}: reader {'running' if rs.get('running') else 'STOPPED'}, "
               f"{rs.get('total_readings')} readings, error rate {err_rate * 100:.2f}%, last reading "
               f"{last_age} s ago, mode poll {rs.get('mode_age_s')} s old, avg read {_num(rs.get('avg_duration')) * 1000:.0f} ms. "
               + ("Issues: " + "; ".join(issues) + "." if issues else "No issues."))
    return {
        "summary": summary, "ok": not issues, "issues": issues,
        "dashboard": {"url": BASE_URL, "version": health.get("version"), "healthz": health.get("ok")},
        "reader": {
            "running": rs.get("running"), "total_readings": rs.get("total_readings"), "error_count": rs.get("error_count"),
            "error_rate": rs.get("error_rate"), "last_reading_time": _iso(last), "last_reading_age_seconds": last_age,
            "avg_read_ms": round(_num(rs.get("avg_duration")) * 1000, 1), "max_read_ms": round(_num(rs.get("max_duration")) * 1000, 1),
            "mode_poll_age_seconds": rs.get("mode_age_s"), "mode": rs.get("extras_mode"),
            "active_warning_count": rs.get("extras_warning_count"),
        },
        "mcp_server": {"read_only": READ_ONLY, "parameter_writes_enabled": ALLOW_PARAM_WRITES, "env_file": ENV_FILE,
                       "env_file_loaded": ENV_FILE_LOADED},
    }


# ---- write tools --------------------------------------------------------------------------------

def _set_priority(kind: str, priority: str) -> dict[str, Any]:
    if kind == "output":
        table, path, cfg_key, noun = OUTPUT_PRIORITIES, "/set-output-priority", "output_priority", "Output source priority"
    else:
        table, path, cfg_key, noun = CHARGER_PRIORITIES, "/set-charger-priority", "charger_priority", "Charger source priority"
    label, command, _ = table[priority]
    res = _post(path, {"mode": priority}) or {}
    applied = res.get("applied") or {}
    previous = res.get("previous")
    now = (res.get("config") or {}).get(cfg_key)
    if now != priority:
        # The dashboard's post-write re-read is debounced (5 s), so it can hand back the old value.
        # Wait it out and force a fresh QPIRI before reporting.
        time.sleep(CONFIRM_RETRY_DELAY_S)
        now = ((_post("/refresh-extras") or {}).get("config") or {}).get(cfg_key)
    confirmed = now == priority
    prev_label = table[previous][0] if previous in table else (previous or "unknown")
    if confirmed:
        if previous == priority:
            summary = f"{noun} was already {label} ({priority}); the inverter acknowledged {command} and still reports {label}."
        else:
            summary = f"{noun} changed from {prev_label} ({previous}) to {label} ({priority}); the inverter acknowledged {command} and now reports {label}."
    else:
        summary = (f"The inverter acknowledged {command} ({label}) but the re-read still reports {now!r}; "
                   f"check again in a few seconds with get_inverter_settings(refresh=true).")
    return {"summary": summary, "requested": priority, "requested_label": label, "previous": previous,
            "previous_label": prev_label, "now": now, "confirmed": confirmed, "command_sent": applied.get("command") or command,
            "inverter_response": applied.get("response")}


if not READ_ONLY:

    @mcp.tool(annotations=WRITE)
    def set_output_priority(
        priority: Annotated[Literal["SBU", "SOL", "UTI"], Field(
            description="SBU = Solar → Battery → Utility (run on solar, then battery, grid last). "
                        "SOL = Solar first (solar, then grid; battery kept for outages). "
                        "UTI = Utility first (grid powers the load; solar and battery are backup).")],
    ) -> dict[str, Any]:
        """Change the inverter's output source priority, i.e. which source runs the house load (PI30 POP
        command). Takes effect immediately and persists in the inverter. Returns the previous and the
        re-read value so the change is confirmed. Switching to SBU will discharge the battery into the
        load until the back-to-grid voltage; switching to SOL or UTI stops that."""
        return _set_priority("output", priority)

    @mcp.tool(annotations=WRITE)
    def set_charger_priority(
        priority: Annotated[Literal["UTI_SOL", "SOL_FIRST", "SOL_UTI", "SOL_ONLY"], Field(
            description="UTI_SOL = grid and solar may both charge. SOL_FIRST = solar charges first, grid tops up. "
                        "SOL_UTI = solar and grid charge at the same time. SOL_ONLY = only solar may charge, "
                        "the grid never does.")],
    ) -> dict[str, Any]:
        """Change the inverter's charger source priority, i.e. what is allowed to charge the battery (PI30 PCP
        command). Takes effect immediately and persists in the inverter. Returns the previous and the
        re-read value so the change is confirmed. Allowing the grid to charge raises the grid bill."""
        return _set_priority("charger", priority)


if ALLOW_PARAM_WRITES:

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
    def set_inverter_parameter(
        param: Annotated[Literal[CONFIG_PARAMS], Field(
            description="battery_type (0 AGM, 1 Flooded, 2 User), output_frequency (50 or 60), cutoff_voltage, "
                        "back_to_grid_voltage, back_to_battery_voltage (0 = full), bulk_voltage, float_voltage "
                        "(volts), max_charge_current, max_ac_charge_current (amps, from the selectable list).")],
        value: Annotated[float | str, Field(description="New value: a number of volts / amps, or the option code "
                                                        "for battery_type / output_frequency.")],
    ) -> dict[str, Any]:
        """Write one inverter configuration parameter (battery voltages, charge-current limits, battery type,
        output frequency). The dashboard validates the value against the battery system and the inverter's
        own selectable lists and the inverter can still refuse (NAK). Bulk / float / cut-off voltages are only
        writable while battery type is User. Wrong values can damage the battery bank: confirm with the user
        and read get_inverter_settings first."""
        res = _post("/inverter/set-param", {"param": param, "value": value}) or {}
        applied = res.get("applied") or {}
        cfg = res.get("config") or {}
        return {
            "summary": f"Sent {applied.get('command')} ({applied.get('label')} = {applied.get('value')}); inverter replied "
                       f"{applied.get('response')!r}. Settings re-read: battery {cfg.get('battery_type')}, bulk "
                       f"{cfg.get('battery_bulk_charge_voltage')} V, float {cfg.get('battery_float_charge_voltage')} V, cut-off "
                       f"{cfg.get('battery_under_voltage')} V, back-to-grid {cfg.get('battery_recharge_voltage')} V, back-to-battery "
                       f"{cfg.get('battery_redischarge_voltage')} V, max charge {cfg.get('max_charging_current')} A, max AC charge "
                       f"{cfg.get('max_ac_charging_current')} A.",
            "applied": applied,
            "settings_after": _settings(cfg, {}) if cfg else None,
        }


# ---- resources and prompts ----------------------------------------------------------------------

@mcp.resource("inverter://status", name="Live inverter status", mime_type="application/json",
              description="The same data as get_live_status, as JSON.")
def status_resource() -> str:
    try:
        return json.dumps(get_live_status(), indent=1, default=str)
    except ToolError as e:
        raise ResourceError(str(e)) from None


@mcp.resource("inverter://settings", name="Inverter settings", mime_type="application/json",
              description="The same data as get_inverter_settings (cached copy), as JSON.")
def settings_resource() -> str:
    try:
        return json.dumps(get_inverter_settings(), indent=1, default=str)
    except ToolError as e:
        raise ResourceError(str(e)) from None


@mcp.prompt(title="Solar system briefing")
def inverter_briefing() -> str:
    """A short status briefing: live state, today's energy, the bill forecast, anything that needs attention."""
    return (
        "Give me a briefing on my solar / inverter system. Call get_live_status, get_energy_summary, "
        "get_daily_history (7 days), get_bill_forecast and get_warnings, then answer in under 150 words: what the "
        "inverter is doing right now and on which source priority, how today compares with the last week, where the "
        "FESCO bill is heading and whether the 200-unit slab is at risk, and anything that needs attention. Lead with "
        "numbers; round kWh to one decimal and rupees to whole numbers."
    )


@mcp.prompt(title="Advise on source priority")
def priority_advice(
    goal: Annotated[str, Field(description="What the user wants, e.g. 'lowest bill', 'battery full for tonight's load-shedding'.")]
    = "lowest electricity bill without running the battery flat",
) -> str:
    """Recommend an output / charger priority for a stated goal, using the live state, recent trend and
    outage history, and offer to apply it."""
    return (
        f"My goal: {goal}. Look at get_live_status, get_inverter_settings, get_recent_trend (last 120 minutes), "
        "get_grid_outages (last 7 days) and get_bill_forecast. Then recommend an output source priority (SBU / SOL / UTI) "
        "and a charger source priority, explain the trade-off in three sentences or fewer (battery wear and outage "
        "reserve versus grid units), and ask before calling set_output_priority or set_charger_priority."
    )


# ---- HTTP transport with a bearer token ---------------------------------------------------------

def _bearer_app(app, token: str):
    """Wrap the SDK's ASGI app so every HTTP request must prove it knows the token, either as
    `Authorization: Bearer <token>` (Claude Code, Claude Desktop, SDK clients) or as the first path
    segment, `/<token>/mcp`, for hosts such as claude.ai custom connectors that cannot send a header.
    GET /healthz is open so systemd / monitoring can probe the port."""
    expected = token.encode()

    async def _send_json(send, status: int, body: bytes, extra_headers=()):
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra_headers]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def wrapper(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        if scope.get("path") == "/healthz":
            return await _send_json(send, 200, b'{"ok": true, "service": "inverter-mcp"}')
        auth = b""
        for key, value in scope.get("headers") or []:
            if key == b"authorization":
                auth = value
                break
        scheme, _, credential = auth.partition(b" ")
        if scheme.lower() == b"bearer" and hmac.compare_digest(credential.strip(), expected):
            return await app(scope, receive, send)
        segment, _, rest = (scope.get("path") or "").lstrip("/").partition("/")
        if segment and rest and hmac.compare_digest(segment.encode(), expected):
            # Secret-URL form: strip the token segment so the SDK sees its own /mcp path.
            rewritten = dict(scope)
            rewritten["path"] = "/" + rest
            rewritten["raw_path"] = rewritten["path"].encode()
            return await app(rewritten, receive, send)
        log.warning("rejected request without a valid token from %s", (scope.get("client") or ["?"])[0])
        return await _send_json(
            send, 401, b'{"error": "invalid_token", "error_description": "a valid bearer token is required"}',
            [(b"www-authenticate", b'Bearer error="invalid_token"')])

    return wrapper


def run_http(host: str, port: int, token: str, allowed_hosts: list[str]) -> None:
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not token:
        if not loopback:
            raise SystemExit("refusing to listen on a non-loopback address without INVERTER_MCP_TOKEN")
        log.warning("no INVERTER_MCP_TOKEN set; accepting unauthenticated requests on loopback only")
    security = TransportSecuritySettings(allowed_hosts=allowed_hosts, allowed_origins=[]) if allowed_hosts else None
    app = mcp.streamable_http_app(streamable_http_path="/mcp", transport_security=security, host=host)
    if token:
        app = _bearer_app(app, token)
    log.info("inverter MCP listening on http://%s:%d/mcp (%s); dashboard %s; writes %s",
             host, port, "bearer token required" if token else "no auth", BASE_URL,
             "disabled" if READ_ONLY else ("priorities + parameters" if ALLOW_PARAM_WRITES else "priorities only"))
    # Behind ngrok / a TLS proxy the request arrives as http; trusting X-Forwarded-* keeps any URL the
    # app builds on https. Auth is the token, so trusting those headers from any peer costs nothing.
    uvicorn.run(app, host=host, port=port, log_level="info", proxy_headers=True, forwarded_allow_ips="*")


# ---- entry point --------------------------------------------------------------------------------

def check() -> int:
    """Log in, fetch one reading and print a summary. Exit 0 when the dashboard answers."""
    try:
        health = client().get("/healthz")
        status = client().get("/status")
        cfg = (client().get("/config") or {}).get("config") or {}
    except AppError as e:
        print(f"FAIL {BASE_URL}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"FAIL cannot reach {BASE_URL}: {e}", file=sys.stderr)
        return 1
    live = _live_status(status, cfg)
    print(f"OK dashboard {health.get('version')} at {BASE_URL} (env file {'loaded' if ENV_FILE_LOADED else 'not found'}: {ENV_FILE})")
    print(live["summary"])
    print(f"writes: {'disabled (read-only)' if READ_ONLY else 'priorities' + (' + parameters' if ALLOW_PARAM_WRITES else '')}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MCP server for the inverter dashboard")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"],
                        default=os.environ.get("INVERTER_MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.environ.get("INVERTER_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("INVERTER_MCP_PORT", "8765")))
    parser.add_argument("--check", action="store_true", help="log in, read once, print a summary and exit")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        allowed = [h.strip() for h in os.environ.get("INVERTER_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
        run_http(args.host, args.port, os.environ.get("INVERTER_MCP_TOKEN", "").strip(), allowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
