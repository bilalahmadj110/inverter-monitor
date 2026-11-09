"""The MCP server with the dashboard faked out: which tools are registered under each safety
flag, the shape of what the tools return, write tools posting the right body and confirming the
change, dashboard errors surfacing as tool errors, and the priority tables matching the app's.
Needs the `mcp` SDK (requirements-mcp.txt); skipped where it is not installed."""
from __future__ import annotations

import importlib
import json
import sys

import pytest

pytest.importorskip("mcp")
from mcp import Client  # noqa: E402

from lib.app_client import AppError  # noqa: E402

# Payloads captured from the live dashboard on 2026-11-09, trimmed.
STATUS = {
    "success": True,
    "metrics": {
        "battery": {"charging_current": 0, "current": -9, "direction": "discharging", "discharge_current": 9,
                    "percentage": 85, "power": -221.4, "voltage": 24.6},
        "grid": {"estimated": True, "frequency": 49.7, "in_use": False, "power": 0.0, "voltage": 231.9},
        "load": {"active_power": 180, "apparent_power": 229, "current": 1.0, "frequency": 49.7, "percentage": 6,
                 "power": 180, "power_factor": 0.786, "voltage": 229.7},
        "solar": {"current": 0.15, "power": 7, "pv_to_battery_current": 0.2, "voltage": 46.8},
    },
    "system": {"bus_voltage": 338, "charge_stage": "idle", "has_fault": False, "is_ac_charging_on": False,
               "is_charging_on": False, "is_charging_to_float": False, "is_load_on": True, "is_scc_charging_on": False,
               "is_switched_on": True, "mode": "B", "mode_label": "Battery Mode", "mode_source": "qmod",
               "temperature": 40, "warnings": []},
    "timing": {"duration_ms": 641.6, "end_time": 1794227801.6, "start_time": 1794227800.9},
}
CONFIG_INNER = {
    "ac_output_frequency": 50.0, "ac_output_voltage": 230.0, "battery_bulk_charge_voltage": 29.2,
    "battery_float_charge_voltage": 27.1, "battery_nominal_voltage": 24.0, "battery_recharge_voltage": 23.0,
    "battery_redischarge_voltage": 27.0, "battery_type": "User", "battery_under_voltage": 21.0,
    "max_ac_charging_current": 10, "max_charging_current": 20,
    "rows": [{"key": "ac_input_voltage", "label": "AC Input Voltage", "unit": "V", "value": 230.0},
             {"key": "max_parallel_units", "label": "Max Parallel Units", "unit": "", "value": 9}],
}
SUMMARY = {"battery_charge_kwh": 2.731, "battery_discharge_kwh": 0.617, "battery_peak_w": 1150.0, "date": "2026-11-09",
           "grid_kwh": 2.443, "grid_peak_w": 468.4, "load_kwh": 4.163, "load_peak_w": 1459.0, "pf_avg": 0.703,
           "self_sufficiency": 0.413, "solar_fraction": 0.309, "solar_kwh": 3.399, "solar_peak_w": 792.0,
           "solar_to_load_kwh": 1.285, "temperature_max": 47.0}
HISTORY = [
    {"battery_charge_energy": 1.81, "battery_discharge_energy": 0.3, "date": "2026-11-07", "grid_energy": 3.66,
     "load_energy": 6.06, "solar_energy": 3.38},
    {"battery_charge_energy": 1.34, "battery_discharge_energy": 1.43, "date": "2026-11-08", "grid_energy": 3.31,
     "load_energy": 5.92, "solar_energy": 2.29},
]
RECENT = {"bucket_seconds": 120, "minutes": 10, "now_ms": 1794227801927, "points": [
    {"battery_avg": -226.8, "battery_percentage": 85.6, "grid_avg": 0, "grid_voltage": 232.8, "load_avg": 179.4,
     "load_max": 201.0, "load_min": 152.0, "solar_avg": 8.8, "solar_max": 9.0, "solar_min": 8.0, "timestamp": 1794227160},
    {"battery_avg": -229.0, "battery_percentage": 85.5, "grid_avg": 0, "grid_voltage": 232.1, "load_avg": 179.7,
     "load_max": 202.0, "load_min": 147.0, "solar_avg": 8.7, "solar_max": 10.0, "solar_min": 8.0, "timestamp": 1794227280},
]}
OUTAGES = {"availability": 0.9663, "count": 2, "from": "2026-11-03", "to": "2026-11-10", "total_down_seconds": 5550,
           "outages": [{"duration_seconds": 3594, "end": 1793716190, "start": 1793712596},
                       {"duration_seconds": 1956, "end": 1793798455, "start": 1793796499}]}
SAVINGS = {
    "today": {"avoided_grid_kwh": 1.748, "date": "2026-11-09", "grid_kwh": 2.443, "load_kwh": 4.191,
              "marginal_rate_pkr_per_kwh": 35.76, "savings_pkr": 62.51, "solar_kwh": 3.4},
    "cycle": {"label": "Nov26", "start": "2026-10-27", "end": "2026-11-26", "savings_pkr": 2427.47,
              "energy": {"grid_kwh": 61.785, "load_kwh": 106.783, "solar_kwh": 59.943},
              "bill_with_solar": {"total": 2243.89, "slab_info": {"current_label": "1-100"}},
              "bill_without_solar": {"total": 4671.36, "slab_info": {"current_label": "101-200"}}},
    "lifetime": {"avg_daily_savings_pkr": 355.19, "days_elapsed": 205, "system_start_date": "2026-04-19",
                 "total_savings_pkr": 72814.08, "total_solar_kwh": 1352.432, "months": [{"month": "Apr26", "savings_pkr": 2431.35}]},
    "payback": {"install_cost_pkr": 500000.0, "payback_years": 3.85, "status": "ok"},
    "projection": {"cliff_alert": {"current_slab": "1-100", "expected_overshoot_kwh": 36.81, "kwh_until_cliff": 38.22,
                                   "next_slab": "101-200", "rate_jump_pkr_per_kwh": 6.47},
                   "days_remaining": 17, "grid_kwh_so_far": 61.78, "projected_bill_total_pkr": 5975.03,
                   "projected_month_end_grid_kwh": 136.81},
}
BILL = {
    "bill_breakdown": {"total": 5975.03, "units": 136.809, "effective_rate_per_unit": 43.674,
                       "slab_info": {"current_label": "101-200", "current_rate": 28.91, "units_to_next_slab": 63.191}},
    "calibration": {"factor": 1.2354, "cycles": []},
    "cycle": {"cycle_label": "Nov26", "start_date": "2026-10-27", "end_date": "2026-11-26", "status": "open"},
    "forecast": {"daily_avg_kwh": 4.413, "days_elapsed": 14, "days_remaining": 17, "projected_units": 136.809,
                 "same_month_last_year_label": "Nov25", "same_month_last_year_units": 153, "total_days": 31,
                 "units_so_far": 61.785},
    "header": {"discom_name": "FESCO", "due_date": "2026-12-09", "load_kw": 3.3, "reading_date": "2026-11-26",
               "tariff_code": "A-1a(01)"},
    "history": [{"label": "Oct26", "start_date": "2026-09-29", "end_date": "2026-10-26", "units": 216.384,
                 "bill_amount": 10504.4, "paid": None, "is_actual": False}],
    "lp_surcharge": {"phase_1_pkr": 597.5, "phase_2_pkr": 1195.01},
    "status": {"status": "unprotected", "reason": "Aug26 = 491 > 200", "window": ["May26", "Oct26"]},
}
STATS_PAYLOAD = {"reading_stats": {"avg_duration": 0.622, "error_count": 0, "error_rate": 0.0, "extras_mode": "B",
                                   "extras_warning_count": 0, "last_reading_time": 1794227801.6, "max_duration": 93.5,
                                   "mode_age_s": 19.8, "running": True, "total_readings": 578968}}


class FakeDashboardClient:
    """Stands in for lib.app_client.InverterAppClient: answers the paths the tools use and records calls."""

    def __init__(self):
        self.calls = []
        self.output_priority = "SBU"
        self.charger_priority = "SOL_ONLY"
        self.stale_after_write = False   # mimic the dashboard's debounced re-read handing back the old value
        self.fail_status = None          # AppError to raise on GET /status

    def _config(self):
        return {**CONFIG_INNER, "output_priority": self.output_priority, "charger_priority": self.charger_priority}

    def get(self, path, **params):
        self.calls.append(("GET", path, params))
        if path == "/status":
            if self.fail_status:
                raise self.fail_status
            return STATUS
        if path == "/config":
            return {"config": self._config(), "output_priority_options": [], "charger_priority_options": []}
        if path == "/inverter/selectable-currents":
            return {"max_charging_current": [10, 20, 30], "max_ac_charging_current": [2, 10, 20]}
        if path == "/warnings":
            return {"warnings": [], "has_fault": False, "mode": "B", "mode_label": "Battery Mode"}
        if path == "/summary":
            return SUMMARY
        if path == "/history":
            return HISTORY
        if path == "/recent-readings":
            return RECENT
        if path == "/outages":
            return OUTAGES
        if path == "/savings/data":
            return SAVINGS
        if path == "/fesco/bill":
            return BILL
        if path == "/healthz":
            return {"ok": True, "version": "abc1234"}
        if path == "/stats-payload":
            return STATS_PAYLOAD
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, body=None, **params):
        self.calls.append(("POST", path, body))
        if path == "/set-output-priority":
            prev, self.output_priority = self.output_priority, body["mode"]
            reported = prev if self.stale_after_write else self.output_priority
            return {"success": True, "previous": prev, "applied": {"mode": body["mode"], "label": "x", "command": "POP0x",
                                                                   "response": "ACK"},
                    "config": {**self._config(), "output_priority": reported}}
        if path == "/set-charger-priority":
            prev, self.charger_priority = self.charger_priority, body["mode"]
            return {"success": True, "previous": prev, "applied": {"mode": body["mode"], "label": "x", "command": "PCP0x",
                                                                   "response": "ACK"},
                    "config": self._config()}
        if path == "/refresh-extras":
            return {"mode": "B", "warnings": [], "config": self._config(), "cached": False}
        if path == "/inverter/set-param":
            return {"success": True, "applied": {"param": body["param"], "value": body["value"], "command": "PBFT27.1",
                                                 "label": "Float charge voltage", "response": "ACK"},
                    "config": self._config()}
        raise AssertionError(f"unexpected POST {path}")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def load_server(monkeypatch, **env):
    monkeypatch.setenv("INVERTER_MCP_ENV_FILE", "/nonexistent/inverter-mcp.env")
    monkeypatch.setenv("INVERTER_PASSWORD", "test-pass")
    for key in ("INVERTER_MCP_READ_ONLY", "INVERTER_MCP_ALLOW_PARAM_WRITES"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("mcp_server", None)
    mod = importlib.import_module("mcp_server")
    fake = FakeDashboardClient()
    mod._client = fake
    monkeypatch.setattr(mod, "CONFIRM_RETRY_DELAY_S", 0.0)
    return mod, fake


@pytest.fixture
def server(monkeypatch):
    return load_server(monkeypatch)


async def tool_names(mod):
    async with Client(mod.mcp, raise_exceptions=True) as c:
        return {t.name for t in (await c.list_tools()).tools}


READ_TOOLS = {"get_live_status", "get_inverter_settings", "get_warnings", "get_energy_summary", "get_daily_history",
              "get_recent_trend", "get_grid_outages", "get_savings", "get_bill_forecast", "get_system_health"}


@pytest.mark.anyio
async def test_default_registers_priority_writes_but_not_parameter_writes(server):
    mod, _ = server
    names = await tool_names(mod)
    assert READ_TOOLS <= names
    assert {"set_output_priority", "set_charger_priority"} <= names
    assert "set_inverter_parameter" not in names


@pytest.mark.anyio
async def test_read_only_hides_every_write(monkeypatch):
    mod, _ = load_server(monkeypatch, INVERTER_MCP_READ_ONLY="1", INVERTER_MCP_ALLOW_PARAM_WRITES="1")
    names = await tool_names(mod)
    assert names == READ_TOOLS


@pytest.mark.anyio
async def test_parameter_writes_need_the_flag(monkeypatch):
    mod, fake = load_server(monkeypatch, INVERTER_MCP_ALLOW_PARAM_WRITES="1")
    assert "set_inverter_parameter" in await tool_names(mod)
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("set_inverter_parameter", {"param": "float_voltage", "value": 27.1})
    assert res.is_error is False
    assert ("POST", "/inverter/set-param", {"param": "float_voltage", "value": 27.1}) in fake.calls
    assert res.structured_content["applied"]["command"] == "PBFT27.1"


@pytest.mark.anyio
async def test_live_status_shape_and_summary(server):
    mod, _ = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("get_live_status")
    assert res.is_error is False
    data = res.structured_content
    assert data["mode"] == {"code": "B", "label": "Battery Mode", "source": "qmod"}
    assert data["battery"]["direction"] == "discharging" and data["battery"]["state_of_charge_percent"] == 85
    assert data["grid"]["present"] is True and data["grid"]["power_w_estimated"] == 0.0
    assert data["output_priority"]["key"] == "SBU" and data["charger_priority"]["label"] == "Only solar"
    summary = data["summary"]
    for piece in ("Battery Mode (QMOD)", "load 180 W", "solar 7 W", "discharging at 221 W", "output priority SBU",
                  "charger Only solar", "no warnings"):
        assert piece in summary
    assert res.content[0].text.startswith("{")   # the model gets the JSON text


@pytest.mark.anyio
async def test_settings_cached_and_refreshed(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        cached = (await c.call_tool("get_inverter_settings")).structured_content
        assert not any(call[1] == "/refresh-extras" for call in fake.calls)
        fresh = (await c.call_tool("get_inverter_settings", {"refresh": True})).structured_content
    assert ("POST", "/refresh-extras", None) in fake.calls
    for data in (cached, fresh):
        assert data["output_priority"]["key"] == "SBU"
        assert data["battery"]["float_charge_voltage_v"] == 27.1
        assert [o["key"] for o in data["options"]["output_priority"]] == ["UTI", "SOL", "SBU"]
        assert len(data["options"]["charger_priority"]) == 4
        assert data["charging"]["selectable_max_charge_current_a"] == [10, 20, 30]
        assert {"label": "Max Parallel Units", "value": 9, "unit": ""} in data["all_settings"]


@pytest.mark.anyio
async def test_read_tools_summaries(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        energy = (await c.call_tool("get_energy_summary")).structured_content
        history = (await c.call_tool("get_daily_history", {"days": 2})).structured_content
        trend = (await c.call_tool("get_recent_trend", {"minutes": 10})).structured_content
        outages = (await c.call_tool("get_grid_outages")).structured_content
        savings = (await c.call_tool("get_savings")).structured_content
        bill = (await c.call_tool("get_bill_forecast")).structured_content
        health = (await c.call_tool("get_system_health")).structured_content
        warnings = (await c.call_tool("get_warnings")).structured_content
    assert "load 4.163 kWh" in energy["summary"] and energy["self_sufficiency"] == 0.413
    assert history["totals"]["load_kwh"] == 11.98 and history["rows"][0]["solar_kwh"] == 3.38
    assert len(trend["points"]) == 2 and trend["points"][0]["battery_percent"] == 85.6 and "85.6% → 85.5%" in trend["summary"]
    assert ("GET", "/recent-readings", {"minutes": 10, "bucket": 60}) in fake.calls   # 30-point default, 60 s floor
    assert outages["count"] == 2 and outages["outages"][0]["duration_minutes"] == 59.9 and "97%" in outages["summary"]
    assert "Rs 62.51" in savings["summary"] and savings["cycle"]["bill_with_solar_pkr"] == 2243.89
    assert "Slab alert" in savings["summary"]
    assert "Cycle Nov26" in bill["summary"] and "136.809" in bill["summary"] and bill["calibration"]["factor"] == 1.2354
    assert bill["recent_cycles"][0]["cycle"] == "Oct26"
    assert health["reader"]["total_readings"] == 578968 and health["dashboard"]["version"] == "abc1234"
    assert health["ok"] is False and any(i.startswith("last reading") for i in health["issues"])   # fixture reading is old
    assert warnings["summary"] == "No active warnings or faults."


@pytest.mark.anyio
async def test_bad_date_is_a_tool_error(server):
    mod, _ = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("get_energy_summary", {"date": "9 Nov"})
    assert res.is_error is True
    assert "YYYY-MM-DD" in res.content[0].text


@pytest.mark.anyio
async def test_set_output_priority_posts_and_confirms(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("set_output_priority", {"priority": "SOL"})
    assert res.is_error is False
    data = res.structured_content
    assert ("POST", "/set-output-priority", {"mode": "SOL"}) in fake.calls
    assert fake.output_priority == "SOL"
    assert (data["previous"], data["now"], data["confirmed"]) == ("SBU", "SOL", True)
    assert "changed from SBU (SBU) to Solar first (SOL)" in data["summary"]
    assert not any(call[1] == "/refresh-extras" for call in fake.calls)


@pytest.mark.anyio
async def test_set_output_priority_same_value_is_reported_as_unchanged(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        data = (await c.call_tool("set_output_priority", {"priority": "SBU"})).structured_content
    assert data["confirmed"] is True and "was already SBU" in data["summary"]


@pytest.mark.anyio
async def test_set_priority_re_reads_when_the_dashboard_answer_is_stale(server):
    mod, fake = server
    fake.stale_after_write = True
    async with Client(mod.mcp, raise_exceptions=True) as c:
        data = (await c.call_tool("set_output_priority", {"priority": "UTI"})).structured_content
    assert ("POST", "/refresh-extras", None) in fake.calls
    assert data["confirmed"] is True and data["now"] == "UTI"


@pytest.mark.anyio
async def test_set_charger_priority(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        data = (await c.call_tool("set_charger_priority", {"priority": "SOL_FIRST"})).structured_content
    assert ("POST", "/set-charger-priority", {"mode": "SOL_FIRST"}) in fake.calls
    assert data["confirmed"] is True and data["previous_label"] == "Only solar"


@pytest.mark.anyio
async def test_invalid_priority_is_rejected_before_any_request(server):
    mod, fake = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("set_output_priority", {"priority": "XYZ"})
    assert res.is_error is True
    assert not any(call[0] == "POST" for call in fake.calls)


@pytest.mark.anyio
async def test_dashboard_error_reaches_the_model(server):
    mod, fake = server
    fake.fail_status = AppError(503, "No reading available yet")
    async with Client(mod.mcp, raise_exceptions=True) as c:
        res = await c.call_tool("get_live_status")
    assert res.is_error is True
    assert "503" in res.content[0].text and "No reading available yet" in res.content[0].text


@pytest.mark.anyio
async def test_resources_and_prompts(server):
    mod, _ = server
    async with Client(mod.mcp, raise_exceptions=True) as c:
        uris = {str(r.uri) for r in (await c.list_resources()).resources}
        status = await c.read_resource("inverter://status")
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        briefing = await c.get_prompt("inverter_briefing")
        advice = await c.get_prompt("priority_advice", {"goal": "battery full for load-shedding"})
    assert uris == {"inverter://status", "inverter://settings"}
    assert json.loads(status.contents[0].text)["mode"]["label"] == "Battery Mode"
    assert prompts == {"inverter_briefing", "priority_advice"}
    assert "get_bill_forecast" in briefing.messages[0].content.text
    assert "battery full for load-shedding" in advice.messages[0].content.text


def test_priority_tables_match_the_dashboard(monkeypatch):
    inverter_status = pytest.importorskip("inverter_status")
    mod, _ = load_server(monkeypatch)
    for key, (label, command, _desc) in mod.OUTPUT_PRIORITIES.items():
        app_cmd, app_label, _ = inverter_status.OUTPUT_PRIORITY_COMMANDS[key]
        assert (label, command) == (app_label, app_cmd)
    for key, (label, command, _desc) in mod.CHARGER_PRIORITIES.items():
        app_cmd, app_label, _ = inverter_status.CHARGER_PRIORITY_COMMANDS[key]
        assert (label, command) == (app_label, app_cmd)
    assert set(mod.CONFIG_PARAMS) == set(inverter_status.CONFIG_PARAM_SETTERS)


def test_env_file_loading(monkeypatch, tmp_path):
    env_file = tmp_path / "inverter-mcp.env"
    env_file.write_text('# comment\nINVERTER_URL="http://pi.local:5000"\nexport INVERTER_USERNAME=bilal\n'
                        'INVERTER_PASSWORD=from-file\nINVERTER_MCP_READ_ONLY=yes\n')
    for key in ("INVERTER_URL", "INVERTER_USERNAME", "INVERTER_PASSWORD", "INVERTER_MCP_READ_ONLY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("INVERTER_MCP_ENV_FILE", str(env_file))
    monkeypatch.setenv("INVERTER_USERNAME", "env-wins")
    sys.modules.pop("mcp_server", None)
    mod = importlib.import_module("mcp_server")
    assert (mod.BASE_URL, mod.USERNAME, mod.PASSWORD, mod.READ_ONLY) == ("http://pi.local:5000", "env-wins", "from-file", True)
    assert mod.ENV_FILE_LOADED is True


class _Recorder:
    """Captures what an ASGI app would have sent."""

    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


async def _echo_app(scope, receive, send):
    body = json.dumps({"path": scope["path"], "type": scope["type"]}).encode()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


async def _run(app, path, headers=()):
    rec = _Recorder()
    scope = {"type": "http", "path": path, "raw_path": path.encode(), "headers": list(headers), "client": ("1.2.3.4", 1)}
    await app(scope, None, rec)
    status = rec.messages[0]["status"]
    body = json.loads(rec.messages[1]["body"] or b"null") if rec.messages[1]["body"] else None
    return status, body


@pytest.mark.anyio
async def test_http_wrapper_accepts_header_or_path_token(server):
    mod, _ = server
    app = mod._bearer_app(_echo_app, "s3cret")
    assert await _run(app, "/healthz") == (200, {"ok": True, "service": "inverter-mcp"})
    assert (await _run(app, "/mcp"))[0] == 401
    assert (await _run(app, "/mcp", [(b"authorization", b"Bearer wrong")]))[0] == 401
    assert (await _run(app, "/wrong/mcp"))[0] == 401
    assert await _run(app, "/mcp", [(b"authorization", b"Bearer s3cret")]) == (200, {"path": "/mcp", "type": "http"})
    assert await _run(app, "/s3cret/mcp") == (200, {"path": "/mcp", "type": "http"})
    # Non-HTTP scopes (lifespan) pass straight through.
    rec = _Recorder()
    await app({"type": "lifespan", "path": ""}, None, rec)
    assert rec.messages[0]["status"] == 200


def test_run_http_passes_relay_flags_and_wraps_with_the_token_check(server, monkeypatch):
    mod, _ = server
    captured = {}
    monkeypatch.setattr(mod.mcp, "streamable_http_app", lambda **kw: captured.update(kw) or "SDK-APP")
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: captured.update(run=kw, app=app))
    mod.run_http("0.0.0.0", 8765, "tok", [], json_response=True, stateless=True)
    assert captured["json_response"] is True and captured["stateless_http"] is True
    assert captured["transport_security"] is None and captured["host"] == "0.0.0.0"
    assert captured["run"]["proxy_headers"] is True and captured["run"]["port"] == 8765
    assert callable(captured["app"]) and captured["app"] != "SDK-APP"   # wrapped by _bearer_app
    with pytest.raises(SystemExit):
        mod.run_http("0.0.0.0", 8765, "", [])                            # no token on a LAN address is refused
