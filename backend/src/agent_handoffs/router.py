"""HTTP API for persisted Retail agent handoffs and inboxes."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.agent_handoffs import service
from src.db.db import get_db_session
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting.forecast_basket import ForecastBasketError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/retail", tags=["Retail Agent Handoffs"])

DatabaseSession = Annotated[Session, Depends(get_db_session)]


class HandoffScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity_id: str | None = None
    category_group: str | None = None
    store_id: str | None = None
    sku: str | None = None


class ExpectedSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source_import_batch_id: int | None = None
    row_count: int = Field(ge=0)
    basket_forecast_7d: float
    dashboard_forecast_7d: float


class CreateHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_agent: Literal["retail.demand_forecasting"]
    target_agent: Literal[
        "retail.inventory_risk",
        "retail.replenishment",
    ]
    handoff_type: Literal["forecast_basket", "risk_flag"]
    status: Literal["approved", "rejected", "cancelled", "sent"]
    scope: HandoffScope
    expected: ExpectedSnapshot


class StatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "approved",
        "rejected",
        "cancelled",
        "reopened",
        "sent",
    ]


def _scope(payload: HandoffScope) -> DashboardScope:
    return DashboardScope.from_query(**payload.model_dump())


def _validation_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@router.post("/agent-handoffs")
def create_agent_handoff(
    payload: CreateHandoffRequest,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        return service.create_handoff(
            session,
            source_agent=payload.source_agent,
            target_agent=payload.target_agent,
            handoff_type=payload.handoff_type,
            status=payload.status,
            scope=_scope(payload.scope),
            expected=payload.expected,
        )
    except service.HandoffSnapshotDriftError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except service.HandoffValidationError as error:
        raise _validation_error(error) from error
    except ForecastBasketError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Canonical forecast basket unavailable: {error}",
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Persisted agent handoff creation failed")
        raise HTTPException(
            status_code=503,
            detail="Agent handoff persistence is unavailable.",
        ) from error


@router.get("/agent-handoffs/{handoff_id}")
def get_agent_handoff(
    handoff_id: str,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        return {"handoff": service.get_handoff(session, handoff_id)}
    except service.HandoffNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SQLAlchemyError as error:
        logger.exception("Persisted agent handoff read failed")
        raise HTTPException(
            status_code=503,
            detail="Agent handoff persistence is unavailable.",
        ) from error


@router.get("/agent-inbox")
def get_agent_inbox(
    session: DatabaseSession,
    agent: str = Query(..., description="Canonical receiving Retail agent id."),
) -> dict[str, Any]:
    try:
        items = service.list_inbox(session, target_agent=agent)
    except service.HandoffValidationError as error:
        raise _validation_error(error) from error
    except SQLAlchemyError as error:
        logger.exception("Persisted agent inbox read failed")
        raise HTTPException(
            status_code=503,
            detail="Agent handoff persistence is unavailable.",
        ) from error
    return {"items": items, "count": len(items)}


@router.patch("/agent-handoffs/{handoff_id}/status")
def update_agent_handoff_status(
    handoff_id: str,
    payload: StatusUpdateRequest,
    session: DatabaseSession,
) -> dict[str, Any]:
    try:
        handoff = service.transition_handoff(
            session,
            handoff_id=handoff_id,
            to_status=payload.status,
        )
    except service.HandoffNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except service.HandoffTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SQLAlchemyError as error:
        logger.exception("Persisted agent handoff status update failed")
        raise HTTPException(
            status_code=503,
            detail="Agent handoff persistence is unavailable.",
        ) from error
    return {"handoff": handoff}


__all__ = ["router"]
