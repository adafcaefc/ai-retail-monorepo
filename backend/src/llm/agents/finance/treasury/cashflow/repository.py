from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.db.models import (
    ApPayable,
    ArCollection,
    Assumption,
    ImportBatch,
    WeeklyForecast,
)


class CashFlowDataError(RuntimeError):
    pass


def _raise_database_error(error: SQLAlchemyError) -> None:
    raise CashFlowDataError(
        f"Database read failed: {error}"
    ) from error


def get_latest_import_batch(
    session: Session,
) -> ImportBatch:
    statement = (
        select(ImportBatch)
        .where(
            ImportBatch.agent_name == "cashflow_agent",
            ImportBatch.import_status == "COMPLETED",
        )
        .order_by(ImportBatch.imported_at.desc())
        .limit(1)
    )

    try:
        import_batch = session.scalars(statement).first()
    except SQLAlchemyError as error:
        _raise_database_error(error)

    if import_batch is None:
        raise CashFlowDataError(
            "Required Cash Flow data was not found."
        )

    return import_batch


def get_weekly_positions(
    session: Session,
    import_batch_id: int,
) -> list[WeeklyForecast]:
    statement = (
        select(WeeklyForecast)
        .where(
            WeeklyForecast.import_batch_id
            == import_batch_id,
        )
        .order_by(WeeklyForecast.week_number)
    )

    try:
        rows = list(session.scalars(statement).all())
    except SQLAlchemyError as error:
        _raise_database_error(error)

    available_weeks = {
        int(row.week_number)
        for row in rows
    }
    if not {5, 6, 7}.issubset(available_weeks):
        raise CashFlowDataError(
            "Week 5, Week 6, and Week 7 data must be available."
        )

    return rows


def get_numeric_assumption(
    session: Session,
    import_batch_id: int,
    assumption_name: str,
) -> float:
    statement = (
        select(Assumption.numeric_value)
        .where(
            Assumption.import_batch_id == import_batch_id,
            Assumption.assumption_name == assumption_name,
        )
        .limit(1)
    )

    try:
        value = session.scalar(statement)
    except SQLAlchemyError as error:
        _raise_database_error(error)

    if value is None:
        raise CashFlowDataError(
            f"Numeric assumption is missing: {assumption_name}"
        )

    return float(value)


def get_net_usd_exposure(
    session: Session,
    import_batch_id: int,
) -> float:
    payables = (
        select(func.coalesce(func.sum(ApPayable.usd_amount), 0))
        .where(ApPayable.import_batch_id == import_batch_id)
        .scalar_subquery()
    )

    receivables = (
        select(func.coalesce(func.sum(ArCollection.usd_amount), 0))
        .where(ArCollection.import_batch_id == import_batch_id)
        .scalar_subquery()
    )

    try:
        exposure = session.scalar(
            select(payables - receivables)
        )
    except SQLAlchemyError as error:
        _raise_database_error(error)

    return float(exposure or 0)


def get_customer_delay_driver(
    session: Session,
    import_batch_id: int,
) -> ArCollection:
    statement = (
        select(ArCollection)
        .where(
            ArCollection.import_batch_id == import_batch_id,
            ArCollection.invoice_number == "AR-012",
        )
        .limit(1)
    )

    try:
        driver = session.scalars(statement).first()
    except SQLAlchemyError as error:
        _raise_database_error(error)

    if driver is None:
        raise CashFlowDataError(
            "Required Cash Flow data was not found."
        )

    return driver


def get_deferrable_payment_driver(
    session: Session,
    import_batch_id: int,
) -> ApPayable:
    statement = (
        select(ApPayable)
        .where(
            ApPayable.import_batch_id == import_batch_id,
            ApPayable.bill_number == "AP-015",
        )
        .limit(1)
    )

    try:
        driver = session.scalars(statement).first()
    except SQLAlchemyError as error:
        _raise_database_error(error)

    if driver is None:
        raise CashFlowDataError(
            "Required Cash Flow data was not found."
        )

    return driver
