"""HTTP contract tests for the additive Retail handoff API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent_handoffs import router


def _request(status="approved"):
    return {
        "source_agent": "retail.demand_forecasting",
        "target_agent": "retail.replenishment",
        "handoff_type": "forecast_basket",
        "status": status,
        "scope": {
            "legal_entity_id": "GRC",
            "category_group": None,
            "store_id": "ALL",
            "sku": "rice",
        },
        "expected": {
            "as_of": "2026-07-01",
            "source_import_batch_id": 23,
            "row_count": 100,
            "basket_forecast_7d": 123.5,
            "dashboard_forecast_7d": 123.5,
        },
    }


def test_create_accepts_scope_and_metadata_but_not_browser_rows(monkeypatch):
    captured = {}

    def fake_create(_session, **values):
        captured.update(values)
        return {"handoff": {"handoff_id": "h1", "status": "approved"}, "created": True}

    monkeypatch.setattr(router.service, "create_handoff", fake_create)
    response = router.create_agent_handoff(
        router.CreateHandoffRequest(**_request()),
        object(),
    )

    assert captured["source_agent"] == "retail.demand_forecasting"
    assert captured["scope"].store_id is None
    assert captured["expected"].row_count == 100
    assert "rows" not in response


def test_create_rejects_arbitrary_target_before_service(monkeypatch):
    called = False

    def fake_create(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(router.service, "create_handoff", fake_create)
    body = _request()
    body["target_agent"] = "retail.erp"

    with pytest.raises(ValidationError):
        router.CreateHandoffRequest(**body)
    assert called is False


def test_status_endpoint_returns_server_record_and_maps_invalid_transition(monkeypatch):
    monkeypatch.setattr(
        router.service,
        "transition_handoff",
        lambda *_args, **_kwargs: {"handoff_id": "h1", "status": "sent"},
    )
    response = router.update_agent_handoff_status(
        "h1",
        router.StatusUpdateRequest(status="sent"),
        object(),
    )
    assert response["handoff"]["status"] == "sent"

    def invalid(*_args, **_kwargs):
        raise router.service.HandoffTransitionError("Invalid handoff transition")

    monkeypatch.setattr(router.service, "transition_handoff", invalid)
    with pytest.raises(router.HTTPException) as error:
        router.update_agent_handoff_status(
            "h1",
            router.StatusUpdateRequest(status="approved"),
            object(),
        )
    assert error.value.status_code == 409


def test_inbox_returns_service_items_for_requested_agent(monkeypatch):
    captured = {}

    def fake_inbox(_session, *, target_agent):
        captured["agent"] = target_agent
        return [{"handoff_id": "h1", "status": "sent"}]

    monkeypatch.setattr(router.service, "list_inbox", fake_inbox)
    response = router.get_agent_inbox(
        object(),
        agent="retail.inventory_risk",
    )

    assert captured["agent"] == "retail.inventory_risk"
    assert response == {
        "items": [{"handoff_id": "h1", "status": "sent"}],
        "count": 1,
    }
