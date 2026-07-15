from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.cashflow import repository, service
from src.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
)
from src.db.db import get_db_session


router = APIRouter(
    prefix="/api/cashflow",
    tags=["Cash Flow"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db_session),
]


@router.get(
    "/baseline",
    response_model=CashFlowBaselineResponse,
)
def get_cashflow_baseline(
    session: DatabaseSession,
) -> CashFlowBaselineResponse:
    try:
        return service.get_baseline(session)

    except repository.CashFlowDataError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.post(
    "/simulate",
    response_model=CashFlowSimulationResponse,
)
def simulate_cashflow(
    payload: CashFlowSimulationRequest,
    session: DatabaseSession,
) -> CashFlowSimulationResponse:
    try:
        return service.simulate(payload, session)

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except repository.CashFlowDataError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error
