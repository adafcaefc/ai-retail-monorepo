"""Request/response models for the Formula Manager API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ParameterType = Literal["number", "text", "boolean"]

# What one row of a formula's inputs counts. It decides which table the rule
# may be fed from, and getting it wrong yields a plausible wrong number rather
# than an error: `f04-position` (store_sku) and `f20-days-of-supply`
# (chain_sku) both take a parameter named `position` and mean different things
# by it.
#
# Required, with no default. A formula whose grain nobody stated is one an
# agent cannot safely use, and defaulting would pick the majority answer
# (store_sku, 16 of 22) silently -- wrong for exactly the chain-net rules where
# it matters most.
#
# `vertical` was added alongside `fc01-seasonal-index` (a rule with no
# per-store or per-SKU row at all, only a per-vertical monthly figure) and is
# the grain the v8.5 per-vertical formulas (Accuracy %, Fill rate, Service
# level) also need -- see `docs/v8.5-new-agent-formulas.md`'s open design
# question.
Grain = Literal["store_sku", "chain_sku", "store_roster", "vertical"]

# The label the Formula Manager shows for each grain, and the table a rule at
# that grain reads from. Kept beside the type so the UI, the API docs and the
# agent tools all describe a grain the same way.
GRAIN_LABELS: dict[str, str] = {
    "store_sku": "Per store x SKU - one store's stock of one item",
    "chain_sku": "Chain-wide per SKU - netted across all stores",
    "store_roster": "Per store roster - one store's workforce",
    "vertical": "Per vertical - one legal entity's own figure",
}

GRAIN_TABLES: dict[str, str] = {
    "store_sku": "retail.fact_inventory_daily",
    "chain_sku": "retail.fact_inventory_chain_daily",
    "store_roster": "",
    "vertical": "retail.agent_kpi_reference",
}


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
    grain: Grain = Field(
        description=(
            "What one row of this formula's inputs counts. store_sku = one "
            "store x one SKU; chain_sku = one SKU netted across all stores; "
            "store_roster = one store's workforce roster."
        ),
    )
    sheet: str = Field(
        default="",
        max_length=64,
        description=(
            "Optional note of which workbook sheet the rule came from. "
            "Provenance only - `grain` is what decides how the rule is used."
        ),
    )
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
    # Echoed so a caller reading a number knows which grain of input produced
    # it, without a second lookup.
    grain: Grain
    values: dict[str, Any] = Field(default_factory=dict)
