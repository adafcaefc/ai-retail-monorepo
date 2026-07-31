"""Finance (performance) agent data tools."""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.tools.db import (
    _latest_batch_id,
    _read_connection,
    _rows,
)
from src.llm.agents.common.tools.period import finance_period


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
            "period": finance_period(connection, import_batch_id),
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


TOOLS = {
    "get_financial_performance_snapshot": get_financial_performance_snapshot,
}


__all__ = ["TOOLS", "get_financial_performance_snapshot"]
