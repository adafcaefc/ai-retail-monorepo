from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

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
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
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


def get_alert_action_plan(
    agent: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Return recent stored alerts with the routed actions planned for each."""

    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50.")
    agent_filter = agent.strip()

    with _read_connection() as connection:
        alerts = _rows(
            connection,
            """
            SELECT id, name, subagent, agent, issue, date_created
            FROM chat.alerts
            WHERE :agent = ''
               OR lower(agent) LIKE '%' || lower(:agent) || '%'
               OR lower(subagent) LIKE '%' || lower(:agent) || '%'
            ORDER BY date_created DESC
            LIMIT :limit
            """,
            {"agent": agent_filter, "limit": limit},
        )
        alert_ids = [str(alert["id"]) for alert in alerts]
        actions = (
            _rows(
                connection,
                """
                SELECT id, alert_id, action, agent, routes, status,
                       spec, impact, simulation_summary, created_at
                FROM chat.actions
                WHERE alert_id::text = ANY(:alert_ids)
                ORDER BY created_at
                LIMIT 200
                """,
                {"alert_ids": alert_ids},
            )
            if alert_ids
            else []
        )
        unlinked_actions = _rows(
            connection,
            """
            SELECT id, action, agent, routes, status, spec, impact,
                   simulation_summary, created_at
            FROM chat.actions
            WHERE alert_id IS NULL
            ORDER BY created_at DESC
            LIMIT 20
            """,
            {},
        )

    actions_by_alert: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        alert_id = str(action.pop("alert_id"))
        actions_by_alert.setdefault(alert_id, []).append(action)

    return {
        "agent_filter": agent_filter,
        "alert_count": len(alerts),
        "alerts": [
            {
                **alert,
                "actions": actions_by_alert.get(str(alert["id"]), []),
            }
            for alert in alerts
        ],
        "unlinked_actions": unlinked_actions,
        "note": (
            "Each action carries its own status and routing owners. An "
            "action is only executed once its owner records approval."
        ),
    }


def _resolve_action(
    session: Any,
    *,
    action_id: str = "",
    action: str = "",
) -> dict[str, Any]:
    """Resolve a stored action by id, falling back to title match."""

    from src.actions import repository

    action_id = (action_id or "").strip()
    action_title = (action or "").strip()

    if action_id:
        found = repository.get_action(session, action_id)
        if found is None:
            raise LookupError(f"Action {action_id!r} was not found.")
        return found

    if not action_title:
        raise ValueError(
            "Provide action_id or action title so the action can be resolved."
        )

    candidates = repository.get_actions(session)
    exact = [
        item
        for item in candidates
        if str(item.get("action") or "").strip().lower()
        == action_title.lower()
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        ids = ", ".join(str(item["id"]) for item in exact[:5])
        raise ValueError(
            f"Multiple actions titled {action_title!r}. "
            f"Pass action_id. Candidates: {ids}"
        )

    partial = [
        item
        for item in candidates
        if action_title.lower() in str(item.get("action") or "").lower()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        ids = ", ".join(str(item["id"]) for item in partial[:5])
        raise ValueError(
            f"Multiple actions match {action_title!r}. "
            f"Pass action_id. Candidates: {ids}"
        )
    raise LookupError(f"No stored action matches {action_title!r}.")


async def simulate_action_impact(
    action_id: str = "",
    action: str = "",
    question: str = "",
) -> dict[str, Any]:
    """Run the impact simulation for an action before any approval.

    Call this whenever the user wants to understand what an action would
    do: its impact, effect, consequence, result, upside, downside, risk,
    or any what-if about applying it. Also call it as the first step when
    the user approves or asks to execute an action, so the simulation is
    shown before approval is confirmed. Do not wait for the user to say
    the word simulation.

    Args:
        action_id: Identifier of the action being simulated, when known.
        action: Title of the action being simulated.
        question: What the user wants to understand about the impact.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        resolved = _resolve_action(
            session,
            action_id=action_id,
            action=action,
        )
        result = await actions_service.simulate_action(
            session,
            str(resolved["id"]),
        )

    simulation = result.get("simulation") or {}
    updated = result.get("action") or {}
    return {
        "received": True,
        "action_id": str(updated.get("id") or resolved["id"]),
        "action": updated.get("action") or resolved.get("action"),
        "question": question,
        "status": "SIMULATED",
        "action_status": updated.get("status") or resolved.get("status"),
        "impact": updated.get("impact") or resolved.get("impact"),
        "simulation": simulation,
        "simulation_summary": updated.get("simulation_summary"),
        "note_to_agent": (
            "Present the simulation summary and metrics as the simulated "
            "impact for this action. Distinguish the owner's stored impact "
            "estimate from the freshly simulated figures. Ask the user to "
            "confirm before calling request_action_approval."
        ),
    }


def request_action_approval(
    action_id: str = "",
    action: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Mark a stored action as approved after the user confirms.

    Call this whenever the user confirms approval after a simulation was
    already presented for the same action. The action status is set to
    approved in the database. Nothing is executed; execution remains with
    the domain execution agent after approval.

    Args:
        action_id: Identifier of the approved action, when known.
        action: Title of the approved action.
        note: Any condition or instruction the user attached.
    """

    from src.actions import service as actions_service
    from src.db.db import session_scope

    with session_scope() as session:
        resolved = _resolve_action(
            session,
            action_id=action_id,
            action=action,
        )
        updated = actions_service.approve_action(
            session,
            str(resolved["id"]),
        )

    return {
        "received": True,
        "action_id": str(updated["id"]),
        "action": updated.get("action"),
        "note": note,
        "status": "APPROVED",
        "action_status": updated.get("status"),
        "routes": list(updated.get("routes") or []),
        "impact": updated.get("impact"),
        "simulation_summary": updated.get("simulation_summary"),
        "note_to_agent": (
            "The action status is now approved in storage. Do not imply "
            "the remediation was executed. Report the approved status and "
            "routing owners; execution still requires the execution agent."
        ),
    }


LOCAL_FINANCE_TOOLS = {
    "calculate_collection_scenario": calculate_collection_scenario,
    "get_alert_action_plan": get_alert_action_plan,
    "request_action_approval": request_action_approval,
    "simulate_action_impact": simulate_action_impact,
    "get_cashflow_baseline": get_cashflow_baseline,
    "get_collections_snapshot": get_collections_snapshot,
    "get_financial_performance_snapshot": get_financial_performance_snapshot,
    "get_payment_leakage_snapshot": get_payment_leakage_snapshot,
    "simulate_cashflow": simulate_cashflow,
}


__all__ = [
    "LOCAL_FINANCE_TOOLS",
    "calculate_collection_scenario",
    "get_alert_action_plan",
    "get_cashflow_baseline",
    "get_collections_snapshot",
    "get_financial_performance_snapshot",
    "get_payment_leakage_snapshot",
    "request_action_approval",
    "simulate_action_impact",
    "simulate_cashflow",
]