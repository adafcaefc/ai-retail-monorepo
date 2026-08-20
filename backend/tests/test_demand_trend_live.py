"""Focused tests for the live Demand Forecasting Trend aggregate."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting import dashboard
from src.llm.agents.retail.common.warehouse import get_engine


def test_demand_trend_formula_uses_aggregate_totals() -> None:
    rows = ((Decimal("4"), Decimal("8")), (Decimal("400"), Decimal("400")))
    actual_total = sum(row[0] for row in rows)
    forecast_total = sum(row[1] for row in rows)

    expected = (forecast_total / actual_total - Decimal("1")) * Decimal("100")
    row_percentage_average = sum(
        (forecast / actual - Decimal("1")) * Decimal("100")
        for actual, forecast in rows
    ) / len(rows)

    assert dashboard.calculate_demand_trend_pct(actual_total, forecast_total) == pytest.approx(
        float(expected)
    )
    assert float(row_percentage_average) == pytest.approx(50.0)
    assert float(expected) != pytest.approx(float(row_percentage_average))


@pytest.mark.parametrize(
    ("actual", "forecast"),
    [(0, 10), (None, 10), ("0.000000", "10.000000")],
)
def test_demand_trend_zero_denominator_is_unavailable(actual, forecast) -> None:
    assert dashboard.calculate_demand_trend_pct(actual, forecast) is None


def _connection_or_skip():
    try:
        return get_engine().connect()
    except Exception as error:  # noqa: BLE001 - live database is optional in CI
        pytest.skip(f"no configured retail database: {error}")


def test_live_sql_trend_scopes_and_source_contract() -> None:
    expected = {
        "GRC": ("GRC", None, None, 2000, 5.5954),
        "S001": (None, None, "S001", 100, 6.1440),
        "GRC-C01": (None, "GRC-C01", None, 100, 5.7945),
        "GRC-001": (None, None, None, 20, 6.0666),
        "S001 + GRC-C01": (None, "GRC-C01", "S001", 5, 6.4092),
        "S001 + GRC-001": (None, None, "S001", 1, 3.8397),
    }

    connection = _connection_or_skip()
    try:
        results = []
        for label, (entity, category, store, row_count, trend) in expected.items():
            scope = DashboardScope(
                legal_entity_id=entity,
                category_group=category,
                store_id=store,
                sku="GRC-001" if label in {"GRC-001", "S001 + GRC-001"} else None,
            )
            results.append((label, dashboard._demand_trend(connection, scope), row_count, trend))

        # The existing browser search matches SKU id or item name. Verify the
        # same name-search contract against the runtime item dimension without
        # hardcoding a display name.
        sku_name = connection.execute(
            text("SELECT name FROM retail.dim_item WHERE item_id = :sku"),
            {"sku": "GRC-001"},
        ).scalar_one()
        by_name = dashboard._demand_trend(
            connection,
            DashboardScope(sku=str(sku_name)),
        )
        by_id = dashboard._demand_trend(
            connection,
            DashboardScope(sku="GRC-001"),
        )
        single_row_result = dashboard._demand_trend(
            connection,
            DashboardScope(sku="GRC-001", store_id="S001"),
        )
        single_row = connection.execute(
            text(
                """
                SELECT
                    actual_w4, actual_w3, actual_w2, actual_w1,
                    forecast_w1, forecast_w2, forecast_w3, forecast_w4
                FROM synthetic.demand_store_sku_32w
                WHERE sku_id = :sku_id AND store_id = :store_id
                """
            ),
            {"sku_id": "GRC-001", "store_id": "S001"},
        ).mappings().one()
    except Exception as error:  # noqa: BLE001 - missing seed is an environment skip
        pytest.skip(f"no approved synthetic demand database: {error}")
    finally:
        connection.close()

    for label, result, row_count, trend in results:
        assert result["source"] == dashboard.SYNTHETIC_DEMAND_TABLE
        assert result["row_count"] == row_count, label
        assert result["horizon_independent"] is True
        assert result["trend_pct"] == pytest.approx(trend, abs=0.0001), label
        assert len(result["sparkline"]) == 8, label
        assert all(value >= 0 for value in result["sparkline"]), label
    assert by_name["row_count"] == by_id["row_count"] == 20
    assert by_name["trend_pct"] == pytest.approx(by_id["trend_pct"], abs=0.000001)
    assert by_name["sparkline"] == pytest.approx(by_id["sparkline"])
    assert single_row_result["row_count"] == 1
    assert single_row_result["sparkline"] == pytest.approx(
        [
            float(single_row[column])
            for column in (
                "actual_w4",
                "actual_w3",
                "actual_w2",
                "actual_w1",
                "forecast_w1",
                "forecast_w2",
                "forecast_w3",
                "forecast_w4",
            )
        ]
    )


def test_live_dashboard_payload_exposes_calculated_trend() -> None:
    try:
        payload = dashboard.build(DashboardScope(legal_entity_id="GRC"))
    except Exception as error:  # noqa: BLE001 - live database is optional in CI
        pytest.skip(f"no configured retail database: {error}")

    trend = payload["demand_trend"]
    assert trend["source"] == dashboard.SYNTHETIC_DEMAND_TABLE
    assert trend["row_count"] == 2000
    assert trend["trend_pct"] == pytest.approx(5.5954, abs=0.0001)
    assert trend["horizon_independent"] is True
    assert len(trend["sparkline"]) == 8
    assert all(value >= 0 for value in trend["sparkline"])
    assert payload["derivation"]["demand_trend"] == "calculated"


def test_live_api_returns_scoped_calculated_trend() -> None:
    client = TestClient(app)
    cases = (
        ({"legal_entity_id": "GRC"}, 5.5954),
        ({"store_id": "S001"}, 6.1440),
        ({"category_group": "GRC-C01"}, 5.7945),
        ({"sku": "GRC-001"}, 6.0666),
        ({"store_id": "S001", "category_group": "GRC-C01"}, 6.4092),
        ({"store_id": "S001", "sku": "GRC-001"}, 3.8397),
    )
    first = client.get(
        "/api/html/dashboard/retail.demand_forecasting",
        params=cases[0][0],
    )
    if first.status_code == 503:
        pytest.skip("no configured retail database")
    assert first.status_code == 200

    payloads = [first.json()]
    for params, _ in cases[1:]:
        response = client.get(
            "/api/html/dashboard/retail.demand_forecasting",
            params=params,
        )
        assert response.status_code == 200
        payloads.append(response.json())

    for payload, (_, expected) in zip(payloads, cases):
        trend = payload["demand_trend"]
        assert trend["source"] == dashboard.SYNTHETIC_DEMAND_TABLE
        assert trend["horizon_independent"] is True
        assert trend["trend_pct"] == pytest.approx(expected, abs=0.0001)
        assert len(trend["sparkline"]) == 8
        assert all(value >= 0 for value in trend["sparkline"])
