"""Leakage (payment integrity) agent data tools."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)


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


TOOLS = {
    "get_payment_leakage_snapshot": get_payment_leakage_snapshot,
}


__all__ = ["TOOLS", "get_payment_leakage_snapshot"]
