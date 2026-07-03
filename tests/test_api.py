import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed (API runs on the EMS VM)")

from fastapi.testclient import TestClient

from src.api.main import CommandRequest, app

client = TestClient(app)


def test_command_model_accepts_valid_input():
    cmd = CommandRequest(mode="CHARGE", p_set_kw=25.0)
    assert cmd.mode == "CHARGE"


def test_command_model_rejects_unknown_mode():
    with pytest.raises(Exception):
        CommandRequest(mode="TURBO", p_set_kw=10.0)


def test_command_model_rejects_out_of_range_power():
    with pytest.raises(Exception):
        CommandRequest(mode="CHARGE", p_set_kw=999.0)


def test_post_command_requires_api_key():
    resp = client.post("/api/commands", json={"mode": "IDLE", "p_set_kw": 0})
    assert resp.status_code in (401, 503)  # no key sent / server key unset


def test_exercise_endpoints_report_not_implemented():
    assert client.get("/api/health").status_code == 501
    assert client.get("/api/alarms").status_code == 501
    assert client.get("/api/batteries/5/history").status_code == 501


def test_battery_history_validates_battery_id():
    resp = client.get("/api/batteries/99/history")
    assert resp.status_code == 422  # path validation fires before the 501 stub
