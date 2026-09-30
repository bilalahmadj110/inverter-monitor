"""Smoke tests for the /fesco/* routes. Uses Flask test_client; no real
inverter, no real Socket.IO, no auth (we monkeypatch login_required to a no-op)."""
from __future__ import annotations

import os
import sys
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The app reads INVERTER_ADMIN_PASSWORD + INVERTER_SECRET_KEY from env via auth.init_auth.
    monkeypatch.setenv("INVERTER_ADMIN_PASSWORD", "test-pass")
    monkeypatch.setenv("INVERTER_SECRET_KEY", "test-secret-key-32chars-padding-more")
    monkeypatch.setenv("WTF_CSRF_ENABLED", "False")  # disable CSRF for these tests

    # Point power_stats at a temp DB so we don't touch real data.
    fake_db = str(tmp_path / "test.db")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Force module-level singletons to use temp DB before app.py imports them.
    import power_stats
    power_stats._instance = power_stats.PowerStats(fake_db)
    import cost_config
    cost_config._instance = cost_config.CostConfig(fake_db)
    import fesco_cycles
    fesco_cycles._instance = fesco_cycles.CycleStore(fake_db)

    # Avoid touching the inverter at startup — patch ContinuousReader.
    with patch("continuous_reader.ContinuousReader") as MockReader:
        mock_inst = MagicMock()
        mock_inst.get_latest_data.return_value = None
        mock_inst.get_config.return_value = {}
        mock_inst.get_statistics.return_value = {}
        MockReader.return_value = mock_inst
        import importlib
        import app as app_module
        importlib.reload(app_module)
        flask_app = app_module.app
        flask_app.config["WTF_CSRF_ENABLED"] = False

        # Mark session as logged in for all requests.
        with flask_app.test_client() as c:
            with c.session_transaction() as sess:
                sess["uid"] = "test-uid"
                sess["user"] = "admin"
            yield c


def test_get_cycles_empty(client):
    resp = client.get("/fesco/cycles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cycles"] == []


def test_bootstrap_then_list(client):
    payload = {"rows": [
        {"cycle_label": "Jan26", "units_actual": 124, "bill_amount_actual": 4645,
         "payment_amount": 4645},
        {"cycle_label": "Feb26", "units_actual": 133, "bill_amount_actual": 5691,
         "payment_amount": 5691},
    ]}
    resp = client.post(
        "/fesco/bootstrap",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.get_json()["inserted"] == 2

    listing = client.get("/fesco/cycles").get_json()
    labels = [c["cycle_label"] for c in listing["cycles"]]
    assert "Jan26" in labels and "Feb26" in labels


def test_bill_returns_open_cycle_payload(client):
    resp = client.get("/fesco/bill")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "cycle" in data
    assert "header" in data
    assert "history" in data
    assert "status" in data
    assert data["cycle"]["status"] == "open"


def test_upsert_actual_then_status_updates(client):
    # Bootstrap 6 closed cycles all <= 200 -> status should be 'protected'.
    rows = [
        {"cycle_label": "Aug25", "units_actual": 150},
        {"cycle_label": "Sep25", "units_actual": 150},
        {"cycle_label": "Oct25", "units_actual": 150},
        {"cycle_label": "Nov25", "units_actual": 150},
        {"cycle_label": "Dec25", "units_actual": 150},
        {"cycle_label": "Jan26", "units_actual": 150},
    ]
    client.post("/fesco/bootstrap", data=json.dumps({"rows": rows}),
                content_type="application/json")
    status = client.get("/fesco/status").get_json()
    assert status["status"] == "protected"


def test_record_meter_reading_and_calibration(client):
    import fesco_cycles
    store = fesco_cycles._instance
    store.upsert_cycle({
        "cycle_label": "Aug26", "start_date": "2026-07-28", "end_date": "2026-08-26",
        "status": "closed", "units_estimated": 353.1, "bill_amount_estimated": 19697.0,
        "notes": "auto",
    })
    store.upsert_cycle({
        "cycle_label": "Zzz99", "start_date": "2026-08-27", "end_date": "2099-01-01",
        "status": "open",
    })

    resp = client.post("/fesco/cycle/Aug26/actual",
                       data=json.dumps({"units_actual": 370, "bill_amount_actual": 20500}),
                       content_type="application/json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["cycle"]["units_actual"] == 370
    assert body["cycle"]["units_estimated"] == 353.1     # estimate preserved alongside
    assert body["cycle"]["notes"] == "meter"
    assert abs(body["calibration"]["factor"] - 370 / 353.1) < 1e-3

    # Open cycles and unknown labels are refused.
    assert client.post("/fesco/cycle/Zzz99/actual", data=json.dumps({"units_actual": 1}),
                       content_type="application/json").status_code == 400
    assert client.post("/fesco/cycle/Nope00/actual", data=json.dumps({"units_actual": 1}),
                       content_type="application/json").status_code == 404

    # Clearing restores the estimate-only state.
    resp = client.post("/fesco/cycle/Aug26/actual", data=json.dumps({"units_actual": None}),
                       content_type="application/json")
    assert resp.status_code == 200
    assert resp.get_json()["cycle"]["units_actual"] is None
    assert resp.get_json()["calibration"]["factor"] is None


def test_savings_data_smoke(client):
    """/savings/data must maintain cycles first and return the cycle-based payload."""
    from datetime import date as _date
    resp = client.get("/savings/data")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("today", "cycle", "month", "lifetime", "payback", "projection", "tariff_check", "config"):
        assert key in data
    assert "avoided_grid_kwh" in data["today"]
    start = _date.fromisoformat(data["cycle"]["start"])
    end = _date.fromisoformat(data["cycle"]["end"])
    assert 26 <= (end - start).days + 1 <= 35          # one reading-day cycle, never a multi-month span
    assert start <= _date.today() <= end
    assert data["config"]["fix_charges_min_units"] == 300
    # The route opened the current cycle as a side effect.
    cycles = client.get("/fesco/cycles").get_json()["cycles"]
    assert [c["status"] for c in cycles].count("open") == 1


def test_delete_cycle(client):
    client.post("/fesco/bootstrap",
                data=json.dumps({"rows": [{"cycle_label": "Jan26", "units_actual": 124}]}),
                content_type="application/json")
    resp = client.delete("/fesco/cycle/Jan26")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    listing = client.get("/fesco/cycles").get_json()
    assert all(c["cycle_label"] != "Jan26" for c in listing["cycles"])
