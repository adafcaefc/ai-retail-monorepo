"""HTTP API for alerts and planned/approved actions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.actions import service
from src.db.db import get_db_session

router = APIRouter(
    prefix="/api",
    tags=["Alerts & Actions"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db_session),
]


class ApproveActionResponse(BaseModel):
    id: str
    action: str
    agent: str
    routes: list[str] = Field(default_factory=list)
    alert_id: str | None = None
    status: str
    spec: str | None = None
    impact: str | None = None
    simulation_summary: Any | None = None
    created_at: str | None = None


@router.get("/alerts")
def get_alerts(
    session: DatabaseSession,
    agent: str | None = Query(
        default=None,
        description="Optional domain filter: finance, cashflow, collection, leakage",
    ),
) -> dict[str, Any]:
    try:
        items = service.list_alerts(session, agent=agent)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"items": items, "count": len(items)}


@router.delete("/alerts")
def clear_alerts(
    session: DatabaseSession,
    agent: str | None = Query(
        default=None,
        description=(
            "Optional domain filter: finance, cashflow, collection, leakage. "
            "Omit to clear alerts/actions for every domain."
        ),
    ),
) -> dict[str, Any]:
    """Delete all alerts and related actions (optionally for one domain)."""
    try:
        return service.clear_alerts(session, agent=agent)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/monitoring-agents")
def get_monitoring_agents(
    agent: str | None = Query(
        default=None,
        description=(
            "Optional domain filter: finance, cashflow, collection, leakage. "
            "Omit to list specialized monitors for every domain."
        ),
    ),
) -> dict[str, Any]:
    """List specialized monitoring subagents per domain agent (ordered)."""
    try:
        return service.list_monitoring_agents(agent=agent)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/alerts/populate")
async def populate_alerts(
    session: DatabaseSession,
    agent: str = Query(
        ...,
        description=(
            "Domain agent whose specialized monitoring passes should run: "
            "finance, cashflow, collection, leakage"
        ),
    ),
) -> dict[str, Any]:
    """
    Sequentially run all specialized monitoring agents for a domain.

    Each monitor receives previous_alerts (existing DB alerts plus alerts
    created earlier in this run) to avoid duplicates.
    """
    try:
        return await service.populate_alerts(session, agent)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Alert population failed: {error}",
        ) from error


@router.get("/actions")
def get_actions(
    session: DatabaseSession,
    agent: str | None = Query(
        default=None,
        description="Optional domain filter: finance, cashflow, collection, leakage",
    ),
    status: str | None = Query(
        default=None,
        description="Optional status filter: planned, approved (pending maps to planned)",
    ),
) -> dict[str, Any]:
    """List all stored actions (history) with their current status."""
    try:
        items = service.list_actions(session, agent=agent, status=status)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"items": items, "count": len(items)}


@router.get("/alerts/{alert_id}/actions")
def get_actions_for_alert(
    alert_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        items = service.list_actions_for_alert(session, alert_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "alert_id": alert_id,
        "items": items,
        "count": len(items),
    }


@router.post(
    "/actions/{action_id}/approve",
    response_model=ApproveActionResponse,
)
def approve_action(
    action_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        updated = service.approve_action(session, action_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "id": str(updated["id"]),
        "action": updated["action"],
        "agent": updated["agent"],
        "routes": list(updated.get("routes") or []),
        "alert_id": (
            str(updated["alert_id"])
            if updated.get("alert_id") is not None
            else None
        ),
        "status": updated["status"],
        "spec": updated.get("spec"),
        "impact": updated.get("impact"),
        "simulation_summary": updated.get("simulation_summary"),
        "created_at": updated.get("created_at"),
    }


@router.post("/actions/{action_id}/simulate")
async def simulate_action(
    action_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        return await service.simulate_action(session, action_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Simulation failed: {error}",
        ) from error
