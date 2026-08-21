"""Server-authoritative persisted forecast-basket handoff workflow."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from math import isclose
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.agent_handoffs import repository
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting.forecast_basket import (
    AGENT_ID as DEMAND_AGENT,
    BASKET_GRAIN,
    BASKET_SOURCE,
    ForecastBasketError,
    RECONCILIATION_ABS_TOL,
    RECONCILIATION_REL_TOL,
    build_forecast_basket,
)


INVENTORY_RISK_AGENT = "retail.inventory_risk"
REPLENISHMENT_AGENT = "retail.replenishment"

CANONICAL_AGENTS = frozenset(
    {DEMAND_AGENT, INVENTORY_RISK_AGENT, REPLENISHMENT_AGENT}
)
HANDOFF_TYPES = frozenset({"forecast_basket", "risk_flag"})

MAIN_HANDOFF = (DEMAND_AGENT, REPLENISHMENT_AGENT, "forecast_basket")
RISK_HANDOFF = (DEMAND_AGENT, INVENTORY_RISK_AGENT, "risk_flag")

INITIAL_STATUSES = frozenset({"approved", "rejected", "cancelled"})
ALL_STATUSES = frozenset(
    {*INITIAL_STATUSES, "reopened", "sent"}
)
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "approved": frozenset({"sent"}),
    "rejected": frozenset({"reopened"}),
    "cancelled": frozenset({"reopened"}),
    "reopened": INITIAL_STATUSES,
}


class HandoffValidationError(ValueError):
    """The requested agent/type/status combination is not supported."""


class HandoffSnapshotDriftError(ValueError):
    """The live canonical basket no longer matches the generated snapshot."""


class HandoffTransitionError(ValueError):
    """The requested status transition is not allowed."""


class HandoffNotFound(LookupError):
    """No persisted handoff exists for the requested id."""


def validate_target_agent(agent: str) -> str:
    if agent not in {INVENTORY_RISK_AGENT, REPLENISHMENT_AGENT}:
        raise HandoffValidationError(
            f"Unsupported inbox agent {agent!r}."
        )
    return agent


def _validate_route(
    source_agent: str,
    target_agent: str,
    handoff_type: str,
) -> None:
    if source_agent not in CANONICAL_AGENTS:
        raise HandoffValidationError(f"Unsupported source agent {source_agent!r}.")
    if target_agent not in CANONICAL_AGENTS:
        raise HandoffValidationError(f"Unsupported target agent {target_agent!r}.")
    if handoff_type not in HANDOFF_TYPES:
        raise HandoffValidationError(f"Unsupported handoff type {handoff_type!r}.")
    if (source_agent, target_agent, handoff_type) not in {
        MAIN_HANDOFF,
        RISK_HANDOFF,
    }:
        raise HandoffValidationError(
            "Unsupported handoff route. Demand Forecasting may send "
            "forecast_basket to Replenishment or risk_flag to Inventory Risk."
        )


def _canonical_snapshot(basket: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """Return a stable payload, its canonical JSON, and its SHA-256 hash."""

    if basket.get("agent") != DEMAND_AGENT:
        raise HandoffSnapshotDriftError("Canonical basket has an unexpected source agent.")
    if basket.get("grain") != BASKET_GRAIN:
        raise HandoffSnapshotDriftError("Canonical basket is not at sku_store grain.")
    if basket.get("source") != BASKET_SOURCE:
        raise HandoffSnapshotDriftError("Canonical basket has an unexpected source.")
    if basket.get("reconciles") is not True:
        raise HandoffSnapshotDriftError(
            "Canonical basket does not reconcile to the Demand Forecasting KPI; regenerate it."
        )

    rows = basket.get("rows")
    if not isinstance(rows, list) or basket.get("row_count") != len(rows):
        raise HandoffSnapshotDriftError("Canonical basket row count is invalid; regenerate it.")

    snapshot = deepcopy(basket)
    snapshot["rows"] = sorted(
        snapshot["rows"],
        key=lambda row: (str(row.get("store_id")), str(row.get("sku_id"))),
    )
    try:
        canonical = json.dumps(
            snapshot,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise HandoffSnapshotDriftError(
            f"Canonical basket cannot be serialized safely: {error}"
        ) from error
    return snapshot, canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _expected_values(expected: Any | None) -> dict[str, Any] | None:
    if expected is None:
        return None
    if hasattr(expected, "model_dump"):
        return expected.model_dump()
    if isinstance(expected, dict):
        return expected
    raise HandoffValidationError("Expected basket metadata must be an object.")


def _check_expected(basket: dict[str, Any], expected: Any | None) -> None:
    values = _expected_values(expected)
    if values is None:
        return

    if str(values.get("as_of"))[:10] != str(basket.get("as_of"))[:10]:
        raise HandoffSnapshotDriftError(
            "The basket snapshot date changed. Regenerate the forecast basket before deciding."
        )
    if values.get("source_import_batch_id") != basket.get("source_import_batch_id"):
        raise HandoffSnapshotDriftError(
            "The basket import batch changed. Regenerate the forecast basket before deciding."
        )
    if int(values.get("row_count")) != int(basket.get("row_count")):
        raise HandoffSnapshotDriftError(
            "The basket row count changed. Regenerate the forecast basket before deciding."
        )

    for field in ("basket_forecast_7d", "dashboard_forecast_7d"):
        try:
            matches = isclose(
                float(values.get(field)),
                float(basket.get(field)),
                rel_tol=RECONCILIATION_REL_TOL,
                abs_tol=RECONCILIATION_ABS_TOL,
            )
        except (TypeError, ValueError):
            matches = False
        if not matches:
            raise HandoffSnapshotDriftError(
                f"The basket {field} changed. Regenerate the forecast basket before deciding."
            )


def build_snapshot(
    scope: DashboardScope,
    *,
    expected: Any | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Rebuild and validate the live basket; browser rows never enter here."""

    try:
        basket = build_forecast_basket(scope)
    except ForecastBasketError:
        raise
    _check_expected(basket, expected)
    return _canonical_snapshot(basket)


def _snapshot_date(snapshot: dict[str, Any]) -> date:
    try:
        return date.fromisoformat(str(snapshot["as_of"])[:10])
    except (KeyError, TypeError, ValueError) as error:
        raise HandoffSnapshotDriftError(
            "Canonical basket has no valid snapshot date."
        ) from error


def create_handoff(
    session: Session,
    *,
    source_agent: str,
    target_agent: str,
    handoff_type: str,
    status: str,
    scope: DashboardScope,
    expected: Any | None = None,
) -> dict[str, Any]:
    """Create one immutable handoff, or return an existing risk flag."""

    _validate_route(source_agent, target_agent, handoff_type)
    if handoff_type == "risk_flag":
        if status != "sent":
            raise HandoffValidationError("A risk_flag must be created as sent.")
    elif status not in INITIAL_STATUSES:
        raise HandoffValidationError(
            "A forecast_basket decision must start as approved, rejected, or cancelled."
        )

    snapshot, payload_json, basket_hash = build_snapshot(scope, expected=expected)

    if handoff_type == "risk_flag":
        existing = repository.find_sent_by_hash(
            session,
            source_agent=source_agent,
            target_agent=target_agent,
            handoff_type=handoff_type,
            basket_hash=basket_hash,
        )
        if existing is not None:
            return {
                "handoff": existing,
                "created": False,
                "idempotent": True,
            }

    try:
        record = repository.create_handoff(
            session,
            source_agent=source_agent,
            target_agent=target_agent,
            handoff_type=handoff_type,
            status=status,
            scope_json=json.dumps(
                snapshot["scope"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            source_snapshot_date=_snapshot_date(snapshot),
            source_import_batch_id=snapshot.get("source_import_batch_id"),
            basket_hash=basket_hash,
            payload_json=payload_json,
        )
    except IntegrityError:
        # The filtered unique index protects against two simultaneous risk
        # clicks. Re-read its winner and preserve the same idempotent API
        # contract instead of surfacing a duplicate-delivery success.
        if handoff_type != "risk_flag":
            raise
        session.rollback()
        existing = repository.find_sent_by_hash(
            session,
            source_agent=source_agent,
            target_agent=target_agent,
            handoff_type=handoff_type,
            basket_hash=basket_hash,
        )
        if existing is None:
            raise
        return {
            "handoff": existing,
            "created": False,
            "idempotent": True,
        }
    return {"handoff": record, "created": True, "idempotent": False}


def get_handoff(
    session: Session,
    handoff_id: str,
    *,
    include_payload: bool = True,
) -> dict[str, Any]:
    record = repository.get_handoff(
        session,
        handoff_id,
        include_payload=include_payload,
    )
    if record is None:
        raise HandoffNotFound(f"Agent handoff {handoff_id} was not found.")
    return record


def transition_handoff(
    session: Session,
    *,
    handoff_id: str,
    to_status: str,
) -> dict[str, Any]:
    if to_status not in ALL_STATUSES:
        raise HandoffTransitionError(f"Unsupported status {to_status!r}.")

    current = get_handoff(session, handoff_id, include_payload=False)
    from_status = current["status"]
    allowed = VALID_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise HandoffTransitionError(
            f"Invalid handoff transition {from_status} -> {to_status}."
        )

    updated = repository.transition_handoff(
        session,
        handoff_id=handoff_id,
        from_status=from_status,
        to_status=to_status,
    )
    if updated is None:
        raise HandoffTransitionError(
            "The handoff changed before this transition was saved; refresh and retry."
        )
    return updated


def list_inbox(session: Session, *, target_agent: str) -> list[dict[str, Any]]:
    validate_target_agent(target_agent)
    return repository.list_inbox(session, target_agent=target_agent)


__all__ = [
    "ALL_STATUSES",
    "CANONICAL_AGENTS",
    "DEMAND_AGENT",
    "HandoffNotFound",
    "HandoffSnapshotDriftError",
    "HandoffTransitionError",
    "HandoffValidationError",
    "HANDOFF_TYPES",
    "INVENTORY_RISK_AGENT",
    "REPLENISHMENT_AGENT",
    "build_snapshot",
    "create_handoff",
    "get_handoff",
    "list_inbox",
    "transition_handoff",
    "validate_target_agent",
]
