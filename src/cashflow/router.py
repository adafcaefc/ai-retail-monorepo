from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.cashflow import repository, service
from src.cashflow.models import (
    CashFlowBaselineResponse,
    CashFlowSimulationRequest,
    CashFlowSimulationResponse,
)


router = APIRouter(
    prefix="/api/cashflow",
    tags=["Cash Flow"],
)


@router.get(
    "/baseline",
    response_model=CashFlowBaselineResponse,
)
async def get_cashflow_baseline() -> CashFlowBaselineResponse:
    try:
        return service.get_baseline()

    except repository.CashFlowDataError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.post(
    "/simulate",
    response_model=CashFlowSimulationResponse,
)
async def simulate_cashflow(
    payload: CashFlowSimulationRequest,
) -> CashFlowSimulationResponse:
    try:
        return service.simulate(payload)

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
