from __future__ import annotations

from pydantic import BaseModel, Field


class LegalEntity(BaseModel):
    legal_entity_id: str
    legal_entity_name: str
    country: str


class WeeklyCashPosition(BaseModel):
    week_number: int
    opening_cash_idr_mn: float
    closing_cash_idr_mn: float
    minimum_buffer_idr_mn: float
    headroom_idr_mn: float
    status: str


class CashFlowDriver(BaseModel):
    reference_number: str
    counterparty_name: str
    amount_idr_mn: float

    original_week: int | None = None
    expected_week: int | None = None
    payment_week: int | None = None

    is_deferrable: bool | None = None
    description: str | None = None


class CashFlowBaselineResponse(BaseModel):
    import_batch_id: int
    workbook_name: str
    workbook_version: str | None = None

    weekly_positions: list[WeeklyCashPosition]

    minimum_buffer_idr_mn: float
    net_usd_exposure: float
    recommended_hedge_usd: float

    spot_rate_idr_per_usd: float
    forward_rate_idr_per_usd: float
    adverse_rate_idr_per_usd: float

    customer_delay_driver: CashFlowDriver
    deferrable_payment_driver: CashFlowDriver

    legal_entity_id: str | None = None
    legal_entities: list[LegalEntity] = Field(default_factory=list)
    # Which parts of this payload actually narrowed to `legal_entity_id`.
    # "weekly_positions" and the FX figures stay whole-ledger even when an
    # entity is requested — see get_baseline()'s docstring for why. A filtered
    # UI reading this can then say so, instead of implying every number moved.
    entity_scope: dict[str, str] = Field(
        default_factory=lambda: {
            "weekly_positions": "all_entities",
            "fx": "all_entities",
            "simulator_caps": "requested_entity",
        }
    )


class CashFlowSimulationRequest(BaseModel):
    accelerate_collection_idr_mn: float = Field(
        default=0, ge=0,
        description="Customer collection moved into Week 5, in IDR million.",
    )
    defer_payment_idr_mn: float = Field(
        default=0, ge=0,
        description="Eligible vendor payment deferred, in IDR million.",
    )
    credit_line_draw_idr_mn: float = Field(
        default=0, ge=0,
        description="Credit line draw added to Week 5 liquidity, in IDR million.",
    )
    hedge_usd: float = Field(
        default=0, ge=0,
        description="USD exposure covered using a forward contract.",
    )


class CashFlowSimulationResponse(BaseModel):
    import_batch_id: int

    accelerate_collection_idr_mn: float
    defer_payment_idr_mn: float
    credit_line_draw_idr_mn: float
    hedge_usd: float

    week5_cash_idr_mn: float
    week6_cash_idr_mn: float
    week7_cash_idr_mn: float

    week5_headroom_idr_mn: float
    week6_headroom_idr_mn: float
    week7_headroom_idr_mn: float

    minimum_buffer_idr_mn: float
    lowest_headroom_idr_mn: float
    weeks_below_buffer: int

    net_usd_exposure: float
    residual_usd_exposure: float
    hedge_coverage_pct: float
    fx_downside_avoided_idr_mn: float
    forward_premium_idr_mn: float

    status: str
    recommendation: str

    assumptions: list[str]
    warnings: list[str]