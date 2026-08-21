"""Focused tests for the persisted forecast-basket handoff workflow."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from src.agent_handoffs import service
from src.llm.agents.common.dashboard_scope import DashboardScope


def _row(store_id: str, sku_id: str, suggestion: float = 4) -> dict:
    return {
        "store_id": store_id,
        "store_name": f"Store {store_id}",
        "sku_id": sku_id,
        "item_name": f"Item {sku_id}",
        "category_id": "GRC-C01",
        "category": "Grocery",
        "target": {"value": 10.0, "unit": "units/day", "basis": "ads"},
        "forecast_7d": 70.5,
        "rop": 20.0,
        "max": 30.0,
        "position": 10.0,
        "suggestion": suggestion,
        "signal": ["below_rop"],
        "route": "direct",
        "lead_time_days": 2.0,
        "eta": None,
        "eta_status": "unavailable",
        "perishable": True,
        "vendor": "Vendor A",
    }


def _basket(rows: list[dict] | None = None, **overrides) -> dict:
    rows = rows or [_row("S001", "SKU-001"), _row("S002", "SKU-002", 0)]
    payload = {
        "schema_version": 1,
        "agent": "retail.demand_forecasting",
        "as_of": "2026-07-01",
        "scope": {
            "legal_entity_id": None,
            "category_group": None,
            "store_id": None,
            "sku": None,
        },
        "grain": "sku_store",
        "source": "retail.fact_inventory_daily.forecast_7d",
        "source_import_batch_id": 23,
        "row_count": len(rows),
        "action_row_count": sum(row["suggestion"] > 0 for row in rows),
        "dashboard_forecast_7d": sum(row["forecast_7d"] for row in rows),
        "basket_forecast_7d": sum(row["forecast_7d"] for row in rows),
        "reconciles": True,
        "suggestion_units": sum(row["suggestion"] for row in rows),
        "rows": rows,
    }
    payload.update(overrides)
    return payload


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}
        self.next_id = 1
        self.create_calls = 0

    def create_handoff(self, _session, **values):
        handoff_id = f"handoff-{self.next_id}"
        self.next_id += 1
        self.create_calls += 1
        record = {
            "handoff_id": handoff_id,
            **values,
            "scope": json.loads(values["scope_json"]),
            "payload": json.loads(values["payload_json"]),
            "created_at": "2026-07-01T00:00:00",
            "updated_at": "2026-07-01T00:00:00",
            "events": [{"from_status": None, "to_status": values["status"]}],
        }
        self.records[handoff_id] = record
        return self._view(record)

    def find_sent_by_hash(self, _session, **values):
        for record in self.records.values():
            if (
                record["status"] == "sent"
                and record["source_agent"] == values["source_agent"]
                and record["target_agent"] == values["target_agent"]
                and record["handoff_type"] == values["handoff_type"]
                and record["basket_hash"] == values["basket_hash"]
            ):
                return self._view(record)
        return None

    def get_handoff(self, _session, handoff_id, *, include_payload=False):
        record = self.records.get(handoff_id)
        if record is None:
            return None
        return self._view(record, include_payload=include_payload)

    def transition_handoff(self, _session, *, handoff_id, from_status, to_status):
        record = self.records.get(handoff_id)
        if record is None or record["status"] != from_status:
            return None
        record["status"] = to_status
        record["updated_at"] = "2026-07-01T00:01:00"
        record["events"].append(
            {"from_status": from_status, "to_status": to_status}
        )
        return self._view(record)

    def list_inbox(self, _session, *, target_agent):
        return [
            self._view(record)
            for record in self.records.values()
            if record["target_agent"] == target_agent and record["status"] == "sent"
        ]

    @staticmethod
    def _view(record, *, include_payload=False):
        result = {
            key: value
            for key, value in record.items()
            if key not in {"scope_json", "payload_json", "payload", "events"}
        }
        result["scope"] = deepcopy(record["scope"])
        result["events"] = deepcopy(record["events"])
        if include_payload:
            result["payload"] = deepcopy(record["payload"])
        return result


@pytest.fixture
def fake_workflow(monkeypatch):
    repository = FakeRepository()
    current = [_basket()]
    monkeypatch.setattr(service, "build_forecast_basket", lambda _scope: deepcopy(current[0]))
    for name in (
        "create_handoff",
        "find_sent_by_hash",
        "get_handoff",
        "list_inbox",
        "transition_handoff",
    ):
        monkeypatch.setattr(
            service.repository,
            name,
            getattr(repository, name),
        )
    return repository, current


def _expected(payload: dict) -> dict:
    return {
        "as_of": payload["as_of"],
        "source_import_batch_id": payload["source_import_batch_id"],
        "row_count": payload["row_count"],
        "basket_forecast_7d": payload["basket_forecast_7d"],
        "dashboard_forecast_7d": payload["dashboard_forecast_7d"],
    }


def _scope() -> DashboardScope:
    return DashboardScope()


def test_snapshot_hash_is_reproducible_and_rows_are_canonical(fake_workflow):
    _repository, current = fake_workflow
    first, first_json, first_hash = service.build_snapshot(_scope())
    current[0]["rows"] = list(reversed(current[0]["rows"]))
    second, second_json, second_hash = service.build_snapshot(_scope())

    assert first_hash == second_hash
    assert first_json == second_json
    assert [row["store_id"] for row in first["rows"]] == ["S001", "S002"]


@pytest.mark.parametrize("status", ["approved", "rejected", "cancelled"])
def test_main_decisions_create_persisted_snapshot(fake_workflow, status):
    repository, current = fake_workflow
    result = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.REPLENISHMENT_AGENT,
        handoff_type="forecast_basket",
        status=status,
        scope=_scope(),
        expected=_expected(current[0]),
    )

    handoff = result["handoff"]
    assert result["created"] is True
    assert handoff["status"] == status
    assert handoff["source_import_batch_id"] == 23
    assert handoff["basket_hash"]
    assert repository.create_calls == 1
    assert handoff["events"][0]["to_status"] == status


def test_status_machine_allows_reopen_and_send_but_rejects_invalid_moves(fake_workflow):
    repository, current = fake_workflow
    created = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.REPLENISHMENT_AGENT,
        handoff_type="forecast_basket",
        status="rejected",
        scope=_scope(),
        expected=_expected(current[0]),
    )["handoff"]

    reopened = service.transition_handoff(
        object(), handoff_id=created["handoff_id"], to_status="reopened"
    )
    approved = service.transition_handoff(
        object(), handoff_id=created["handoff_id"], to_status="approved"
    )
    sent = service.transition_handoff(
        object(), handoff_id=created["handoff_id"], to_status="sent"
    )

    assert reopened["status"] == "reopened"
    assert approved["status"] == "approved"
    assert sent["status"] == "sent"
    with pytest.raises(service.HandoffTransitionError, match="sent -> reopened"):
        service.transition_handoff(
            object(), handoff_id=created["handoff_id"], to_status="reopened"
        )
    assert len(repository.records[created["handoff_id"]]["events"]) == 4


def test_snapshot_metadata_drift_requires_regeneration(fake_workflow):
    _repository, current = fake_workflow
    expected = _expected(current[0])
    expected["basket_forecast_7d"] += 1

    with pytest.raises(service.HandoffSnapshotDriftError, match="basket_forecast_7d"):
        service.create_handoff(
            object(),
            source_agent=service.DEMAND_AGENT,
            target_agent=service.REPLENISHMENT_AGENT,
            handoff_type="forecast_basket",
            status="approved",
            scope=_scope(),
            expected=expected,
        )


def test_risk_flag_is_sent_and_idempotent_for_the_same_frozen_basket(fake_workflow):
    repository, current = fake_workflow
    first = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.INVENTORY_RISK_AGENT,
        handoff_type="risk_flag",
        status="sent",
        scope=_scope(),
        expected=_expected(current[0]),
    )
    second = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.INVENTORY_RISK_AGENT,
        handoff_type="risk_flag",
        status="sent",
        scope=_scope(),
        expected=_expected(current[0]),
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["idempotent"] is True
    assert second["handoff"]["handoff_id"] == first["handoff"]["handoff_id"]
    assert repository.create_calls == 1


def test_snapshot_is_immutable_when_live_source_changes_after_creation(fake_workflow):
    repository, current = fake_workflow
    created = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.REPLENISHMENT_AGENT,
        handoff_type="forecast_basket",
        status="approved",
        scope=_scope(),
        expected=_expected(current[0]),
    )["handoff"]
    original_hash = created["basket_hash"]
    current[0]["rows"][0]["suggestion"] = 999
    current[0]["suggestion_units"] = 999

    sent = service.transition_handoff(
        object(), handoff_id=created["handoff_id"], to_status="sent"
    )
    detail = service.get_handoff(object(), created["handoff_id"])

    assert sent["basket_hash"] == original_hash
    assert detail["payload"]["suggestion_units"] == 4
    assert detail["payload"]["rows"][0]["suggestion"] == 4


def test_inbox_is_targeted_and_only_sent_items_are_delivered(fake_workflow):
    repository, current = fake_workflow
    service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.REPLENISHMENT_AGENT,
        handoff_type="forecast_basket",
        status="approved",
        scope=_scope(),
        expected=_expected(current[0]),
    )
    delivered = service.create_handoff(
        object(),
        source_agent=service.DEMAND_AGENT,
        target_agent=service.INVENTORY_RISK_AGENT,
        handoff_type="risk_flag",
        status="sent",
        scope=_scope(),
        expected=_expected(current[0]),
    )

    replenishment = service.list_inbox(
        object(), target_agent=service.REPLENISHMENT_AGENT
    )
    risk = service.list_inbox(object(), target_agent=service.INVENTORY_RISK_AGENT)

    assert replenishment == []
    assert len(risk) == 1
    assert risk[0]["handoff_id"] == delivered["handoff"]["handoff_id"]
    with pytest.raises(service.HandoffValidationError):
        service.list_inbox(object(), target_agent=service.DEMAND_AGENT)
