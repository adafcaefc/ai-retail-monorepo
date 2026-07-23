from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.cashflow import service as cashflow_service
from src.cashflow.models import CashFlowSimulationRequest
from src.db.db import get_engine


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _row(row: Any) -> dict[str, Any]:
    return {
        str(key): _json_value(value)
        for key, value in row.items()
    }


def _rows(
    connection: Connection,
    statement: str,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    result = connection.execute(
        text(statement),
        parameters,
    ).mappings()
    return [_row(row) for row in result]


def _latest_batch_id(
    connection: Connection,
    agent_name: str,
) -> int:
    import_batch_id = connection.execute(
        text(
            """
            SELECT id
            FROM audit.import_batches
            WHERE agent_name = :agent_name
              AND import_status = 'COMPLETED'
            ORDER BY imported_at DESC
            LIMIT 1
            """
        ),
        {"agent_name": agent_name},
    ).scalar_one_or_none()
    if import_batch_id is None:
        raise RuntimeError(
            f"No completed database import exists for {agent_name}."
        )
    return int(import_batch_id)


@contextmanager
def _read_connection() -> Iterator[Connection]:
    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        yield connection


def get_cashflow_baseline() -> dict[str, Any]:
    """Return the latest verified cash-flow forecast, assumptions, and drivers."""

    return cashflow_service.get_baseline().model_dump(mode="json")


def simulate_cashflow(
    accelerate_collection_idr_mn: float = 0,
    defer_payment_idr_mn: float = 0,
    credit_line_draw_idr_mn: float = 0,
    hedge_usd: float = 0,
) -> dict[str, Any]:
    """Recalculate Weeks 5-7 using validated liquidity and FX levers."""

    request = CashFlowSimulationRequest(
        accelerate_collection_idr_mn=accelerate_collection_idr_mn,
        defer_payment_idr_mn=defer_payment_idr_mn,
        credit_line_draw_idr_mn=credit_line_draw_idr_mn,
        hedge_usd=hedge_usd,
    )
    return cashflow_service.simulate(request).model_dump(mode="json")


def get_collections_snapshot() -> dict[str, Any]:
    """Return the latest exact collections, DSO, aging, risk, and worklist data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "collections_credit_agent",
        )
        parameters = {"import_batch_id": import_batch_id}
        summary = _rows(
            connection,
            """
            SELECT total_ar_idr_mn, current_ar_idr_mn, overdue_ar_idr_mn,
                   overdue_percentage, annual_credit_sales_idr_mn,
                   daily_credit_sales_idr_mn, current_dso_days,
                   target_dso_days, dso_gap_days,
                   cash_freed_at_target_idr_mn,
                   high_risk_provision_idr_mn
            FROM collections.dso_cash_impact
            WHERE import_batch_id = :import_batch_id
            """,
            parameters,
        )
        customers = _rows(
            connection,
            """
            SELECT customer_id, customer_name, customer_segment,
                   payment_terms, days_beyond_terms, payment_trend,
                   has_dispute, on_time_percentage, total_ar_idr_mn,
                   overdue_idr_mn, overdue_percentage,
                   current_idr_mn,
                   overdue_1_30_idr_mn, overdue_31_60_idr_mn,
                   overdue_61_90_idr_mn, overdue_90_plus_idr_mn,
                   credit_limit_idr_mn, credit_utilization
            FROM collections.customer_credit_aging
            WHERE import_batch_id = :import_batch_id
            ORDER BY overdue_idr_mn DESC, customer_name
            LIMIT 25
            """,
            parameters,
        )
        risk_tiers = _rows(
            connection,
            """
            SELECT risk_tier, customer_count, exposure_idr_mn,
                   percentage_of_ar, notes
            FROM collections.risk_tier_exposure
            WHERE import_batch_id = :import_batch_id
            ORDER BY exposure_idr_mn DESC
            """,
            parameters,
        )
        worklist = _rows(
            connection,
            """
            SELECT priority_rank, customer_name, overdue_idr_mn,
                   oldest_aging_bucket, risk_tier, risk_score,
                   recommended_action, recovery_percentage,
                   expected_recovery_idr_mn
            FROM collections.worklist
            WHERE import_batch_id = :import_batch_id
            ORDER BY priority_rank
            LIMIT 20
            """,
            parameters,
        )
        return {
            "import_batch_id": import_batch_id,
            "summary": summary[0] if summary else {},
            "customers": customers,
            "risk_tiers": risk_tiers,
            "worklist": worklist,
        }


def calculate_collection_scenario(
    customer_name: str,
    cash_to_collect_idr_mn: float,
    discount_pct: float = 0,
) -> dict[str, Any]:
    """Calculate exact cash, discount cost, customer overdue, and portfolio DSO."""

    if not customer_name.strip():
        raise ValueError("customer_name must not be empty.")
    amount = Decimal(str(cash_to_collect_idr_mn))
    discount = Decimal(str(discount_pct))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("cash_to_collect_idr_mn must be greater than zero.")
    if not discount.is_finite() or discount < 0 or discount > 100:
        raise ValueError("discount_pct must be between 0 and 100.")

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "collections_credit_agent",
        )
        customer = connection.execute(
            text(
                """
                SELECT customer_id, customer_name, total_ar_idr_mn,
                       overdue_idr_mn
                FROM collections.customer_credit_aging
                WHERE import_batch_id = :import_batch_id
                  AND lower(customer_name) LIKE '%' || lower(:customer_name) || '%'
                ORDER BY
                    CASE WHEN lower(customer_name) = lower(:customer_name)
                         THEN 0 ELSE 1 END,
                    overdue_idr_mn DESC
                LIMIT 1
                """
            ),
            {
                "import_batch_id": import_batch_id,
                "customer_name": customer_name.strip(),
            },
        ).mappings().one_or_none()
        if customer is None:
            raise ValueError(f"Customer was not found: {customer_name}")

        overdue_before = Decimal(customer["overdue_idr_mn"])
        if amount > overdue_before:
            raise ValueError(
                "Requested collection exceeds the customer's overdue balance "
                f"of IDR {overdue_before:,.2f} million."
            )

        portfolio = connection.execute(
            text(
                """
                SELECT total_ar_idr_mn, daily_credit_sales_idr_mn,
                       current_dso_days
                FROM collections.dso_cash_impact
                WHERE import_batch_id = :import_batch_id
                """
            ),
            {"import_batch_id": import_batch_id},
        ).mappings().one()

    total_ar_before = Decimal(portfolio["total_ar_idr_mn"])
    daily_credit_sales = Decimal(portfolio["daily_credit_sales_idr_mn"])
    total_ar_after = total_ar_before - amount
    dso_before = Decimal(portfolio["current_dso_days"])
    dso_after = total_ar_after / daily_credit_sales
    discount_cost = amount * discount / Decimal("100")

    return {
        "import_batch_id": import_batch_id,
        "customer_id": customer["customer_id"],
        "customer_name": customer["customer_name"],
        "cash_collected_idr_mn": round(float(amount), 2),
        "discount_pct": round(float(discount), 4),
        "discount_cost_idr_mn": round(float(discount_cost), 2),
        "customer_overdue_before_idr_mn": round(float(overdue_before), 2),
        "customer_overdue_after_idr_mn": round(float(overdue_before - amount), 2),
        "total_ar_before_idr_mn": round(float(total_ar_before), 2),
        "total_ar_after_idr_mn": round(float(total_ar_after), 2),
        "dso_before_days": round(float(dso_before), 2),
        "dso_after_days": round(float(dso_after), 2),
        "dso_change_days": round(float(dso_after - dso_before), 2),
        "assumption": (
            "The requested gross cash amount is received and total AR falls "
            "by the same amount. Customer acceptance requires verification."
        ),
    }


def get_financial_performance_snapshot() -> dict[str, Any]:
    """Return the latest bounded KPI, profit, variance, and simulator data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "financial_performance_agent",
        )
        parameters = {"import_batch_id": import_batch_id}
        return {
            "import_batch_id": import_batch_id,
            "kpis": _rows(
                connection,
                "SELECT * FROM financial_performance.kpis "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 30",
                parameters,
            ),
            "profit_summary": _rows(
                connection,
                "SELECT * FROM financial_performance.profit_summary "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 30",
                parameters,
            ),
            "variance_drivers": _rows(
                connection,
                "SELECT * FROM financial_performance.variance_drivers "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 30",
                parameters,
            ),
            "simulator_levers": _rows(
                connection,
                "SELECT * FROM financial_performance.simulator_levers "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 10",
                parameters,
            ),
        }


def get_payment_leakage_snapshot() -> dict[str, Any]:
    """Return the latest bounded leakage summary, anomalies, and action data."""

    with _read_connection() as connection:
        import_batch_id = _latest_batch_id(
            connection,
            "payment_leakage_fraud_agent",
        )
        parameters = {"import_batch_id": import_batch_id}
        return {
            "import_batch_id": import_batch_id,
            "summary": _rows(
                connection,
                "SELECT * FROM payment_leakage.summary "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 5",
                parameters,
            ),
            "category_breakdowns": _rows(
                connection,
                "SELECT * FROM payment_leakage.category_breakdowns "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 20",
                parameters,
            ),
            "anomalies": _rows(
                connection,
                "SELECT * FROM payment_leakage.anomaly_detections "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 30",
                parameters,
            ),
            "action_worklist": _rows(
                connection,
                "SELECT * FROM payment_leakage.action_worklist "
                "WHERE import_batch_id = :import_batch_id ORDER BY id LIMIT 20",
                parameters,
            ),
        }


LOCAL_FINANCE_TOOLS = {
    "calculate_collection_scenario": calculate_collection_scenario,
    "get_cashflow_baseline": get_cashflow_baseline,
    "get_collections_snapshot": get_collections_snapshot,
    "get_financial_performance_snapshot": get_financial_performance_snapshot,
    "get_payment_leakage_snapshot": get_payment_leakage_snapshot,
    "simulate_cashflow": simulate_cashflow,
}


__all__ = [
    "LOCAL_FINANCE_TOOLS",
    "calculate_collection_scenario",
    "get_cashflow_baseline",
    "get_collections_snapshot",
    "get_financial_performance_snapshot",
    "get_payment_leakage_snapshot",
    "simulate_cashflow",
]