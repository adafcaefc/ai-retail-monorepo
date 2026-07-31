"""Leakage (payment integrity) agent data tools."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)
from src.llm.agents.common.tools.period import leakage_period


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
            "period": leakage_period(connection, import_batch_id),
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
            # QC-054: the flagged amounts carry an invoice date once joined to
            # the transactions they came from, which is the only genuine time
            # series any of the four agents holds besides the cash forecast.
            "daily_at_risk": _rows(
                connection,
                """
                SELECT t.invoice_date AS on_date,
                       a.anomaly_type,
                       a.payment_status,
                       a.amount_at_risk_idr_mn AS amount
                FROM payment_leakage.anomaly_detections a
                JOIN payment_leakage.ap_transactions t
                  ON t.transaction_id = a.transaction_id
                 AND t.import_batch_id = a.import_batch_id
                WHERE a.import_batch_id = :import_batch_id
                  AND a.is_flagged
                  AND t.invoice_date IS NOT NULL
                ORDER BY t.invoice_date
                """,
                parameters,
            ),
        }


TOOLS = {
    "get_payment_leakage_snapshot": get_payment_leakage_snapshot,
}


__all__ = ["TOOLS", "get_payment_leakage_snapshot"]
