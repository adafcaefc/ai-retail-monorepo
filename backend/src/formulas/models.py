"""Request/response models for the Formula Manager API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParameterType = Literal["number", "text", "boolean"]


class Parameter(BaseModel):
    key: str = Field(
        min_length=1,
        max_length=64,
        description="Name used inside the expression, e.g. on_hand",
    )
    label: str = Field(min_length=1, max_length=120)
    type: ParameterType = "number"
    default: Any | None = None


class FormulaBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    logic: str = Field(
        default="",
        max_length=500,
        description="Plain-language description of what the formula does",
    )
    sheet: str = Field(default="", max_length=64)
    result_type: Literal["number", "text"] = "number"
    expression: str = Field(
        min_length=1,
        max_length=2000,
        description="Excel-free arithmetic over the declared parameters",
    )
    parameters: list[Parameter] = Field(default_factory=list)


class FormulaCreate(FormulaBase):
    id: str | None = Field(
        default=None,
        description="Optional slug; derived from the name when omitted",
    )
    number: int | None = Field(default=None, ge=1)


class FormulaUpdate(FormulaBase):
    number: int | None = Field(default=None, ge=1)


class Formula(FormulaBase):
    id: str
    number: int


class ValidateRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=2000)
    parameters: list[Parameter] = Field(default_factory=list)


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    referenced: list[str] = Field(default_factory=list)
    undeclared: list[str] = Field(
        default_factory=list,
        description="Names the expression reads that no parameter declares",
    )
    unused: list[str] = Field(
        default_factory=list,
        description="Declared parameters the expression never reads",
    )


class EvaluateRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    id: str
    result: Any
    result_type: str
    values: dict[str, Any] = Field(default_factory=dict)
