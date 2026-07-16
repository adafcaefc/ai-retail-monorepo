from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.cashflow import cards, repository, service
from src.cashflow.models import (
    CashFlowAdaptiveCardResponse,
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


@router.get(
    "/adaptive-card",
    response_model=CashFlowAdaptiveCardResponse,
)
def get_cashflow_adaptive_card(
    session: DatabaseSession,
) -> CashFlowAdaptiveCardResponse:
    try:
        baseline = service.get_baseline(session)
        return CashFlowAdaptiveCardResponse(
            adaptiveCard=cards.build_cashflow_baseline_card(baseline),
            data=baseline,
        )
    except repository.CashFlowDataError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post(
    "/adaptive-card/simulate",
    response_model=CashFlowAdaptiveCardResponse,
)
def simulate_cashflow_adaptive_card(
    payload: CashFlowSimulationRequest,
    session: DatabaseSession,
) -> CashFlowAdaptiveCardResponse:
    try:
        baseline = service.get_baseline(session)
        result = service.simulate(payload, session)
        return CashFlowAdaptiveCardResponse(
            adaptiveCard=cards.build_cashflow_simulation_card(
                baseline,
                payload,
                result,
            ),
            data=result,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except repository.CashFlowDataError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
