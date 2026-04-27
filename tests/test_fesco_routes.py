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


def test_delete_cycle(client):
    client.post("/fesco/bootstrap",
                data=json.dumps({"rows": [{"cycle_label": "Jan26", "units_actual": 124}]}),
                content_type="application/json")
    resp = client.delete("/fesco/cycle/Jan26")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    listing = client.get("/fesco/cycles").get_json()
    assert all(c["cycle_label"] != "Jan26" for c in listing["cycles"])
