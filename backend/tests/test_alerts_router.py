"""HTTP contract for /api/alerts and /api/actions -- `service` is monkeypatched.

No database: this proves status codes, error mapping, and which query params
reach which service call, not persistence. Builds a standalone app around
just `src.actions.router` so importing it does not also pull in
backend/main.py's chivon load / workbook warm.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.actions import service
from src.actions.router import router
from src.db.db import get_db_session


class DummySession:
    """Stands in for the DB session; every service call below is monkeypatched."""


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: DummySession()
    return TestClient(app)


def test_delete_alerts_still_works(monkeypatch, client):
    """The one deliberate destructive path: DELETE /api/alerts is unchanged."""
    captured: dict[str, Any] = {}

    def fake_clear_alerts(session, *, agent=None):
        captured["agent"] = agent
        return {"agent": agent, "alerts_deleted": 3, "actions_deleted": 5}

    monkeypatch.setattr(service, "clear_alerts", fake_clear_alerts)

    response = client.delete("/api/alerts?agent=retail.inventory_risk")

    assert response.status_code == 200
    assert response.json() == {
        "agent": "retail.inventory_risk",
        "alerts_deleted": 3,
        "actions_deleted": 5,
    }
    assert captured["agent"] == "retail.inventory_risk"


def test_populate_conflict_maps_to_409(monkeypatch, client):
    async def fake_populate(session, agent):
        raise service.PopulateAlreadyRunningError(
            f"A monitoring populate is already running for {agent!r}."
        )

    monkeypatch.setattr(service, "populate_alerts", fake_populate)

    response = client.post("/api/alerts/populate?agent=retail.inventory_risk")

    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


def test_populate_500_is_still_the_fallback_for_other_errors(monkeypatch, client):
    async def fake_populate(session, agent):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "populate_alerts", fake_populate)

    response = client.post("/api/alerts/populate?agent=retail.inventory_risk")

    assert response.status_code == 500


def test_populate_success_returns_service_payload(monkeypatch, client):
    async def fake_populate(session, agent):
        return {
            "agent": agent,
            "run_id": 42,
            "created_count": 2,
            "items": [],
            "passes": [],
        }

    monkeypatch.setattr(service, "populate_alerts", fake_populate)

    response = client.post("/api/alerts/populate?agent=retail.inventory_risk")

    assert response.status_code == 200
    assert response.json()["run_id"] == 42


def test_actions_history_calls_list_action_history(monkeypatch, client):
    captured: dict[str, Any] = {}

    def fake_history(session, *, agent=None):
        captured["agent"] = agent
        return [{"id": "a1", "action": "Reorder", "status": "planned"}]

    monkeypatch.setattr(service, "list_action_history", fake_history)
    # The live-view function must NOT be the one this endpoint calls.
    monkeypatch.setattr(
        service,
        "list_actions",
        lambda *a, **k: pytest.fail("GET /actions/history must not call list_actions"),
    )

    response = client.get("/api/actions/history?agent=retail.inventory_risk")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert captured["agent"] == "retail.inventory_risk"


def test_actions_status_filter_threads_through(monkeypatch, client):
    captured: dict[str, Any] = {}

    def fake_list_actions(session, *, agent=None, status=None):
        captured["agent"] = agent
        captured["status"] = status
        return []

    monkeypatch.setattr(service, "list_actions", fake_list_actions)

    response = client.get("/api/actions?agent=retail.inventory_risk&status=planned")

    assert response.status_code == 200
    assert captured == {"agent": "retail.inventory_risk", "status": "planned"}


def test_alert_actions_status_filter_threads_through(monkeypatch, client):
    captured: dict[str, Any] = {}

    def fake_list_actions_for_alert(session, alert_id, *, status=None):
        captured["alert_id"] = alert_id
        captured["status"] = status
        return []

    monkeypatch.setattr(service, "list_actions_for_alert", fake_list_actions_for_alert)

    response = client.get("/api/alerts/alert-1/actions?status=approved")

    assert response.status_code == 200
    assert captured == {"alert_id": "alert-1", "status": "approved"}


def test_alert_actions_status_defaults_to_none(monkeypatch, client):
    captured: dict[str, Any] = {}

    def fake_list_actions_for_alert(session, alert_id, *, status=None):
        captured["status"] = status
        return []

    monkeypatch.setattr(service, "list_actions_for_alert", fake_list_actions_for_alert)

    client.get("/api/alerts/alert-1/actions")

    assert captured["status"] is None
