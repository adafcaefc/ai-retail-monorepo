"""HTTP API for the Formula Manager."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.formulas import service
from src.formulas.models import (
    EvaluateRequest,
    EvaluateResponse,
    Formula,
    FormulaCreate,
    FormulaUpdate,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(
    prefix="/api",
    tags=["Formulas"],
)


@router.get("/formulas")
def get_formulas() -> dict[str, Any]:
    """Every stored formula, ordered by number."""
    try:
        items = service.list_formulas()
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {"items": items, "count": len(items)}


# Registered before /formulas/{formula_id} so "validate" is not read as an id.
@router.post("/formulas/validate", response_model=ValidateResponse)
def validate_formula(payload: ValidateRequest) -> dict[str, Any]:
    """Check a draft expression against its parameters without storing it."""
    return service.validate(payload.expression, payload.parameters)


@router.get("/formulas/{formula_id}", response_model=Formula)
def get_formula(formula_id: str) -> dict[str, Any]:
    try:
        return service.get_formula(formula_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/formulas", response_model=Formula, status_code=201)
def create_formula(payload: FormulaCreate) -> dict[str, Any]:
    try:
        return service.create_formula(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/formulas/{formula_id}", response_model=Formula)
def update_formula(formula_id: str, payload: FormulaUpdate) -> dict[str, Any]:
    try:
        return service.update_formula(formula_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/formulas/{formula_id}")
def delete_formula(formula_id: str) -> dict[str, Any]:
    try:
        return service.delete_formula(formula_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/formulas/{formula_id}/evaluate", response_model=EvaluateResponse)
def evaluate_formula(
    formula_id: str,
    payload: EvaluateRequest,
) -> dict[str, Any]:
    """Run a stored formula against supplied parameter values."""
    try:
        return service.evaluate_formula(formula_id, payload.values)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
