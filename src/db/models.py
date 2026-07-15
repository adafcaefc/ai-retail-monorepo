from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


BIGINT_PRIMARY_KEY = BigInteger().with_variant(
    Integer(),
    "sqlite",
)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "import_status IN ('STARTED', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="import_batches_status_check",
        ),
        Index("idx_import_batches_agent_name", "agent_name"),
        Index("idx_import_batches_status", "import_status"),
        {"schema": "audit"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    workbook_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workbook_version: Mapped[str | None] = mapped_column(String(100))
    workbook_path: Mapped[str | None] = mapped_column(String(500))
    import_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="STARTED",
        server_default=text("'STARTED'"),
    )
    imported_by: Mapped[str | None] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    total_sheets: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    assumptions: Mapped[list[Assumption]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ar_collections: Mapped[list[ArCollection]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    ap_payables: Mapped[list[ApPayable]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    other_outflows: Mapped[list[OtherOutflow]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    weekly_forecasts: Mapped[list[WeeklyForecast]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    fx_scenarios: Mapped[list[FxScenario]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


Index(
    "idx_import_batches_imported_at",
    ImportBatch.imported_at.desc(),
)


class Assumption(Base):
    __tablename__ = "assumptions"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "assumption_group",
            "assumption_name",
            name="uq_assumptions_batch_name",
        ),
        Index("idx_assumptions_import_batch", "import_batch_id"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_assumptions_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    assumption_group: Mapped[str] = mapped_column(String(100), nullable=False)
    assumption_name: Mapped[str] = mapped_column(String(255), nullable=False)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    date_value: Mapped[date | None] = mapped_column(Date)
    unit: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="02 Assumptions",
        server_default=text("'02 Assumptions'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(back_populates="assumptions")


class ArCollection(Base):
    __tablename__ = "ar_collections"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "invoice_number",
            name="uq_ar_collections_batch_invoice",
        ),
        CheckConstraint(
            "original_week IS NULL OR original_week BETWEEN 1 AND 13",
            name="chk_ar_original_week",
        ),
        CheckConstraint(
            "expected_week IS NULL OR expected_week BETWEEN 1 AND 13",
            name="chk_ar_expected_week",
        ),
        Index("idx_ar_collections_import_batch", "import_batch_id"),
        Index("idx_ar_collections_expected_week", "expected_week"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_ar_collections_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_segment: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    original_week: Mapped[int | None] = mapped_column(Integer)
    expected_week: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    amount_idr_mn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    usd_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    idr_value_mn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    delay_flag: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="03 AR Collections",
        server_default=text("'03 AR Collections'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(
        back_populates="ar_collections"
    )


class ApPayable(Base):
    __tablename__ = "ap_payables"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "bill_number",
            name="uq_ap_payables_batch_bill",
        ),
        CheckConstraint(
            "payment_week IS NULL OR payment_week BETWEEN 1 AND 13",
            name="chk_ap_payment_week",
        ),
        Index("idx_ap_payables_import_batch", "import_batch_id"),
        Index("idx_ap_payables_payment_week", "payment_week"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_ap_payables_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    bill_number: Mapped[str] = mapped_column(String(50), nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255))
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    payment_week: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    amount_idr_mn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    usd_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    idr_value_mn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    is_deferrable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="04 AP USD Payables",
        server_default=text("'04 AP USD Payables'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(back_populates="ap_payables")


class OtherOutflow(Base):
    __tablename__ = "other_outflows"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "category",
            "week_number",
            name="uq_other_outflows_batch_category_week",
        ),
        CheckConstraint(
            "week_number BETWEEN 1 AND 13",
            name="chk_other_outflows_week",
        ),
        Index("idx_other_outflows_import_batch", "import_batch_id"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_other_outflows_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="05 Other Outflows",
        server_default=text("'05 Other Outflows'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(
        back_populates="other_outflows"
    )


class WeeklyForecast(Base):
    __tablename__ = "weekly_forecast"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "week_number",
            name="uq_weekly_forecast_batch_week",
        ),
        CheckConstraint(
            "week_number BETWEEN 1 AND 13",
            name="chk_weekly_forecast_week",
        ),
        CheckConstraint(
            "status IN ('OK', 'SHORTAGE', 'RISK')",
            name="chk_weekly_forecast_status",
        ),
        Index("idx_weekly_forecast_import_batch", "import_batch_id"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_weekly_forecast_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start: Mapped[date | None] = mapped_column(Date)
    week_end: Mapped[date | None] = mapped_column(Date)
    customer_collections_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    total_inflows_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    vendor_payments_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    vendor_payments_usd_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    payroll_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    rent_utilities_opex_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    taxes_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    loan_repayment_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    total_outflows_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    net_cash_flow_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    opening_cash_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    closing_cash_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    minimum_buffer_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    headroom_idr_mn: Mapped[Decimal] = mapped_column(
        Numeric(20, 2), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="06 Cash Forecast 13W",
        server_default=text("'06 Cash Forecast 13W'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(
        back_populates="weekly_forecasts"
    )


class FxScenario(Base):
    __tablename__ = "fx_scenarios"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "scenario_name",
            name="uq_fx_scenarios_batch_name",
        ),
        Index("idx_fx_scenarios_import_batch", "import_batch_id"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_fx_scenarios_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    scenario_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_description: Mapped[str | None] = mapped_column(Text)
    usd_exposure: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    fx_rate_idr_per_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    movement_vs_spot: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    fx_cash_impact_idr_mn: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2)
    )
    downside_avoided_idr_mn: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2)
    )
    premium_idr_mn: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    liquidity_effect: Mapped[str | None] = mapped_column(Text)
    confidence_label: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    is_recommended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="07 FX Scenarios",
        server_default=text("'07 FX Scenarios'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(back_populates="fx_scenarios")


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation_type IN ('LIQUIDITY', 'FX', 'GOVERNANCE')",
            name="chk_recommendation_type",
        ),
        Index("idx_recommendations_import_batch", "import_batch_id"),
        {"schema": "cashflow"},
    )

    id: Mapped[int] = mapped_column(
        BIGINT_PRIMARY_KEY,
        primary_key=True,
    )
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "audit.import_batches.id",
            name="fk_recommendations_import_batch",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    recommendation_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    action_title: Mapped[str] = mapped_column(String(255), nullable=False)
    action_description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    risks: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    approval_route: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="08 Recommendation",
        server_default=text("'08 Recommendation'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    import_batch: Mapped[ImportBatch] = relationship(
        back_populates="recommendations"
    )