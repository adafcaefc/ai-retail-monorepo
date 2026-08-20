"""Live SQL coverage for the Demand Forecasting Seasonality Index KPI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from main import app
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.common.warehouse import get_engine
from src.llm.agents.retail.demand_forecasting.dashboard import (
    ENGINE_STORE_SEASONALITY_SOURCE,
    engine_store_seasonality_index,
)


SCOPES = (
    ("All retail", DashboardScope(), 1.03125, 103.125, 16000),
    ("GRC", DashboardScope(legal_entity_id="GRC"), 1.14, 114.0, 2000),
    ("S001", DashboardScope(store_id="S001"), 1.14, 114.0, 100),
    ("GRC-C01", DashboardScope(category_group="GRC-C01"), 1.14, 114.0, 100),
    ("GRC-001", DashboardScope(sku="GRC-001"), 1.14, 114.0, 20),
    (
        "S001 + GRC-C01",
        DashboardScope(store_id="S001", category_group="GRC-C01"),
        1.14,
        114.0,
        5,
    ),
    (
        "S001 + GRC-001",
        DashboardScope(store_id="S001", sku="GRC-001"),
        1.14,
        114.0,
        1,
    ),
)


def _engine_or_skip():
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return engine
    except Exception as error:  # noqa: BLE001 - an unseeded DB is an environment skip
        pytest.skip(f"no seeded Azure SQL database: {error}")


def test_engine_store_seas_uses_average_after_scope_filtering() -> None:
    engine = _engine_or_skip()

    with engine.connect() as connection:
        for label, scope, expected_average, expected_value, expected_rows in SCOPES:
            result = engine_store_seasonality_index(connection, scope)

            assert result["source"] == ENGINE_STORE_SEASONALITY_SOURCE
            assert result["grain"] == "sku_store", label
            assert result["aggregation"] == "AVG(Seas) * 100", label
            assert result["row_count"] == expected_rows, label
            assert result["average_seas"] == pytest.approx(expected_average), label
            assert result["value"] == pytest.approx(expected_value), label


def test_seasonality_kpi_query_does_not_read_legacy_reference_table() -> None:
    engine = _engine_or_skip()
    statements: list[str] = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with engine.connect() as connection:
            result = engine_store_seasonality_index(
                connection,
                DashboardScope(legal_entity_id="GRC", store_id="S001", sku="GRC-001"),
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert result["value"] == pytest.approx(114.0)
    seasonality_sql = [
        statement for statement in statements if "temp_engine_store" in statement
    ]
    assert seasonality_sql, "the KPI did not execute against temp_engine_store"
    assert any("[Seas]" in statement for statement in seasonality_sql)
    assert not any("agent_kpi_reference" in statement for statement in statements)


def test_dashboard_api_returns_the_calculated_seasonality_payload() -> None:
    _engine_or_skip()
    client = TestClient(app)
    for params, expected_average, expected_value in (
        ({}, 1.03125, 103.125),
        ({"legal_entity_id": "GRC"}, 1.14, 114.0),
        ({"store_id": "S001"}, 1.14, 114.0),
    ):
        response = client.get(
            "/api/html/dashboard/retail.demand_forecasting",
            params=params,
        )
        if response.status_code == 503:
            pytest.skip("the dashboard API cannot reach the seeded database")
        assert response.status_code == 200
        payload = response.json()
        assert payload["derivation"]["seasonality_index"] == (
            "calculated-from-engine-store-seas"
        )
        index = payload["seasonality_index"]
        assert index["value"] == pytest.approx(expected_value)
        assert index["average_seas"] == pytest.approx(expected_average)
        assert index["row_count"] > 0
        assert index["source"] == "retail.temp_engine_store.[Seas]"
        assert index["grain"] == "sku_store"
        assert index["aggregation"] == "AVG(Seas) * 100"
