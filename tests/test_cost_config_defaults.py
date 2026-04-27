"""DEFAULT_NON_TARIFF must include FESCO billing-cycle and meter-metadata keys."""
from __future__ import annotations

import cost_config


def test_default_includes_reading_day():
    cfg = cost_config.DEFAULT_NON_TARIFF
    assert cfg["reading_day_of_month"] == 26
    assert cfg["weekend_rolls_to_monday"] is True


def test_default_includes_meter_metadata():
    cfg = cost_config.DEFAULT_NON_TARIFF
    assert "consumer_id" in cfg
    assert "tariff_code" in cfg
    assert "connection_date" in cfg
    assert "meter_no" in cfg
    assert cfg["discom_name"] == "FESCO"


def test_load_returns_new_keys(tmp_db):
    cc = cost_config.CostConfig(tmp_db)
    cfg = cc.load()
    assert cfg["reading_day_of_month"] == 26
    assert cfg["discom_name"] == "FESCO"
