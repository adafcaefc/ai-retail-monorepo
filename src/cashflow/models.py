from __future__ import annotations

from pydantic import BaseModel, Field


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


class CashFlowSimulationRequest(BaseModel):
    accelerate_collection_idr_mn: float = Field(
        default=0,
        ge=0,
        le=8000,
        description=(
            "Customer A collection moved from Week 7 "
            "into Week 5, in IDR million."
        ),
    )

    defer_payment_idr_mn: float = Field(
        default=0,
        ge=0,
        le=3000,
        description=(
            "Eligible vendor payment moved from Week 5 "
            "into Week 6, in IDR million."
        ),
    )

    credit_line_draw_idr_mn: float = Field(
        default=0,
        ge=0,
        le=5000,
        description=(
            "Credit line draw added to Week 5 liquidity, "
            "in IDR million."
        ),
    )

    hedge_usd: float = Field(
        default=0,
        ge=0,
        le=3300000,
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