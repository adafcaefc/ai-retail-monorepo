import pytest

from src.llm.tools.freeform_query import (
    FINANCE_ALLOWED_TABLES,
    _extract_table_names,
    _parse_single_statement,
    _validate_query,
)


def _finance_tables() -> set[str]:
    return {table.lower() for table in FINANCE_ALLOWED_TABLES}


def test_validate_allows_select_on_allowed_table() -> None:
    validated = _validate_query(
        "SELECT metric_name FROM financial_performance.kpis "
        "WHERE import_batch_id = 1 LIMIT 10",
        allowed_types={"SELECT"},
        allowed_tables=_finance_tables(),
    )
    assert "financial_performance.kpis" in validated.lower()


def test_validate_allows_cte_and_ignores_cte_alias() -> None:
    validated = _validate_query(
        """
        WITH latest AS (
            SELECT id
            FROM audit.import_batches
            WHERE agent_name = 'financial_performance_agent'
              AND import_status = 'COMPLETED'
            ORDER BY imported_at DESC
            LIMIT 1
        )
        SELECT k.metric_name
        FROM financial_performance.kpis AS k
        JOIN latest ON k.import_batch_id = latest.id
        """,
        allowed_types={"SELECT"},
        allowed_tables=_finance_tables(),
    )
    assert "financial_performance.kpis" in validated.lower()


def test_extract_tables_from_join_and_subquery() -> None:
    expression = _parse_single_statement(
        """
        SELECT k.metric_name, p.product_name
        FROM financial_performance.kpis AS k
        JOIN financial_performance.product_margins AS p
          ON k.import_batch_id = p.import_batch_id
        WHERE k.import_batch_id IN (
            SELECT id FROM audit.import_batches WHERE import_status = 'COMPLETED'
        )
        """
    )
    tables = _extract_table_names(expression)
    assert tables == {
        "financial_performance.kpis",
        "financial_performance.product_margins",
        "audit.import_batches",
    }


def test_validate_rejects_disallowed_table() -> None:
    with pytest.raises(ValueError, match="outside the allow-list"):
        _validate_query(
            "SELECT * FROM cashflow.weekly_forecast",
            allowed_types={"SELECT"},
            allowed_tables=_finance_tables(),
        )


def test_validate_rejects_insert_when_select_only() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        _validate_query(
            "INSERT INTO financial_performance.kpis (metric_name) VALUES ('x')",
            allowed_types={"SELECT"},
            allowed_tables=_finance_tables(),
        )


def test_validate_rejects_drop() -> None:
    with pytest.raises(ValueError, match="Unsupported SQL statement type"):
        _validate_query(
            "DROP TABLE financial_performance.kpis",
            allowed_types={"SELECT"},
            allowed_tables=_finance_tables(),
        )


def test_validate_rejects_multi_statement() -> None:
    with pytest.raises(ValueError, match="Only one SQL statement"):
        _validate_query(
            "SELECT 1 FROM financial_performance.kpis; "
            "DROP TABLE financial_performance.kpis",
            allowed_types={"SELECT"},
            allowed_tables=_finance_tables(),
        )


def test_validate_rejects_invalid_sql() -> None:
    with pytest.raises(ValueError, match="Failed to parse SQL"):
        _validate_query(
            "SELEC metric_name FORM financial_performance.kpis",
            allowed_types={"SELECT"},
            allowed_tables=_finance_tables(),
        )
