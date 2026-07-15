from __future__ import annotations

from typing import Any

from src.db.db import run_query


class CashFlowDataError(RuntimeError):
    pass


def _get_single_row(
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    rows, error = run_query(sql, params)

    if error:
        raise CashFlowDataError(error)

    if not rows:
        raise CashFlowDataError(
            "Required Cash Flow data was not found."
        )

    return rows[0]


def get_latest_import_batch() -> dict[str, Any]:
    return _get_single_row(
        """
        SELECT
            id,
            workbook_name,
            workbook_version,
            imported_at,
            completed_at
        FROM audit.import_batches
        WHERE agent_name = 'cashflow_agent'
          AND import_status = 'COMPLETED'
        ORDER BY imported_at DESC
        LIMIT 1
        """
    )


def get_weekly_positions(
    import_batch_id: int,
) -> list[dict[str, Any]]:
    rows, error = run_query(
        """
        SELECT
            week_number,
            opening_cash_idr_mn,
            closing_cash_idr_mn,
            minimum_buffer_idr_mn,
            headroom_idr_mn,
            status
        FROM cashflow.weekly_forecast
        WHERE import_batch_id = %s
          AND week_number IN (5, 6, 7)
        ORDER BY week_number
        """,
        (import_batch_id,),
    )

    if error:
        raise CashFlowDataError(error)

    if len(rows) != 3:
        raise CashFlowDataError(
            "Week 5, Week 6, and Week 7 data must be available."
        )

    return rows


def get_numeric_assumption(
    import_batch_id: int,
    assumption_name: str,
) -> float:
    row = _get_single_row(
        """
        SELECT
            numeric_value
        FROM cashflow.assumptions
        WHERE import_batch_id = %s
          AND assumption_name = %s
        LIMIT 1
        """,
        (
            import_batch_id,
            assumption_name,
        ),
    )

    value = row.get("numeric_value")

    if value is None:
        raise CashFlowDataError(
            f"Numeric assumption is missing: {assumption_name}"
        )

    return float(value)


def get_net_usd_exposure(
    import_batch_id: int,
) -> float:
    payable_row = _get_single_row(
        """
        SELECT
            COALESCE(
                SUM(COALESCE(usd_amount, 0)),
                0
            ) AS usd_payables
        FROM cashflow.ap_payables
        WHERE import_batch_id = %s
        """,
        (import_batch_id,),
    )

    receivable_row = _get_single_row(
        """
        SELECT
            COALESCE(
                SUM(COALESCE(usd_amount, 0)),
                0
            ) AS usd_receivables
        FROM cashflow.ar_collections
        WHERE import_batch_id = %s
        """,
        (import_batch_id,),
    )

    return (
        float(payable_row["usd_payables"])
        - float(receivable_row["usd_receivables"])
    )


def get_customer_delay_driver(
    import_batch_id: int,
) -> dict[str, Any]:
    return _get_single_row(
        """
        SELECT
            invoice_number AS reference_number,
            customer_name AS counterparty_name,
            idr_value_mn AS amount_idr_mn,
            original_week,
            expected_week,
            notes AS description
        FROM cashflow.ar_collections
        WHERE import_batch_id = %s
          AND invoice_number = 'AR-012'
        LIMIT 1
        """,
        (import_batch_id,),
    )


def get_deferrable_payment_driver(
    import_batch_id: int,
) -> dict[str, Any]:
    return _get_single_row(
        """
        SELECT
            bill_number AS reference_number,
            vendor_name AS counterparty_name,
            amount_idr_mn,
            payment_week,
            is_deferrable,
            notes AS description
        FROM cashflow.ap_payables
        WHERE import_batch_id = %s
          AND bill_number = 'AP-015'
        LIMIT 1
        """,
        (import_batch_id,),
    )
