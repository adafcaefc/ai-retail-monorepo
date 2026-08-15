"""Demand Forecasting's Store scope from SQL rows through the HTTP contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from main import app
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting import dashboard


AGENT_URL = "/api/html/dashboard/retail.demand_forecasting"


def _build_or_skip(scope: DashboardScope | None = None) -> dict:
    try:
        return dashboard.build(scope)
    except Exception as error:  # noqa: BLE001 - an unseeded DB is an environment skip
        pytest.skip(f"no seeded retail database: {error}")


def _forecast(payload: dict) -> float:
    return sum(float(row["forecast_7d"]) for row in payload["items"])


def test_store_scope_uses_store_grain_rows_for_all_downstream_inputs() -> None:
    all_stores = _build_or_skip()
    s001 = _build_or_skip(DashboardScope.from_query(store_id="S001"))
    s002 = _build_or_skip(DashboardScope.from_query(store_id="S002"))

    # All Stores retains the existing chain-net source and its 800 item rows.
    assert len(all_stores["items"]) == 800
    assert len(all_stores["stores"]) == 160
    assert _forecast(all_stores) == pytest.approx(1_656_178.21602674)
    assert all("store_id" not in row for row in all_stores["items"])

    # A selected Store uses ENGINE_STORE's 100 store x SKU rows. Every item,
    # inventory input, inbound input, risk calculation, and ranking input is
    # therefore from the selected Store before the frontend aggregates it.
    assert len(s001["items"]) == 100
    assert len(s002["items"]) == 100
    assert {row["store_id"] for row in s001["items"]} == {"S001"}
    assert {row["store_id"] for row in s002["items"]} == {"S002"}
    assert {row["store_id"] for row in s001["stores"]} == {"S001"}
    assert {row["store_id"] for row in s002["stores"]} == {"S002"}
    assert _forecast(s001) == pytest.approx(25_948.941032500927)
    assert _forecast(s002) == pytest.approx(30_756.578276753902)
    assert _forecast(s001) != pytest.approx(_forecast(s002))
    assert s001["scope"] == {"store_id": "S001"}
    assert s002["scope"] == {"store_id": "S002"}
    assert s001["scope_limitations"]


def test_store_scope_is_not_reported_as_ignored_by_the_descriptor() -> None:
    payload = _build_or_skip(DashboardScope.from_query(store_id="S001"))

    descriptor = dashboard.SUPPORTED_FILTERS
    assert "store_id" in descriptor
    assert DashboardScope(store_id="S001").ignored_by(descriptor) == ()
    assert payload["scope"]["store_id"] == "S001"


def test_store_id_reaches_the_executed_store_grain_sql() -> None:
    """The query listener proves this is a bound SQL predicate, not response filtering."""
    from src.llm.agents.retail.common.warehouse import get_engine

    try:
        engine = get_engine()
    except Exception as error:  # noqa: BLE001 - missing DB config is an environment skip
        pytest.skip(f"no configured retail database: {error}")
    statements: list[tuple[str, object]] = []

    def capture(_connection, _cursor, statement, parameters, _context, _executemany):
        if "fact_inventory_daily" in statement:
            statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        _build_or_skip(DashboardScope.from_query(store_id="S001"))
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    # Match on the predicate in the SQL and the value in the parameters, not on
    # the parameter's name: pyodbc binds positionally, so `parameters` arrives
    # as a tuple like ('2026-07-01', 'S001') and never carries "store_id" the
    # way psycopg's named-parameter dict used to.
    matching = [
        (statement, parameters)
        for statement, parameters in statements
        if "s.store_id" in statement and "S001" in str(parameters)
    ]
    assert matching, "the Store-grain query did not bind store_id=S001"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _get_or_skip(client: TestClient, **params: str) -> dict:
    response = client.get(AGENT_URL, params=params)
    if response.status_code == 503:
        pytest.skip("no seeded retail database")
    assert response.status_code == 200
    return response.json()


def test_api_all_s001_and_s002_return_distinct_scoped_results(
    client: TestClient,
) -> None:
    # Avoid opening a TestClient request when the configured database is not
    # reachable.  The builder check is the same dependency, but fails quickly
    # and lets this integration test remain useful in seeded environments.
    _build_or_skip()
    all_stores = _get_or_skip(client)
    s001 = _get_or_skip(client, store_id="S001")
    s002 = _get_or_skip(client, store_id="S002")

    assert all_stores["scope"] == {}
    assert "ignored_filters" not in all_stores
    assert len(all_stores["items"]) == 800
    assert len(all_stores["stores"]) == 160
    assert _forecast(all_stores) == pytest.approx(1_656_178.21602674)

    for payload, store_id, expected in (
        (s001, "S001", 25_948.941032500927),
        (s002, "S002", 30_756.578276753902),
    ):
        assert payload["scope"] == {"store_id": store_id}
        assert "ignored_filters" not in payload
        assert len(payload["items"]) == 100
        assert {row["store_id"] for row in payload["items"]} == {store_id}
        assert {row["store_id"] for row in payload["stores"]} == {store_id}
        assert _forecast(payload) == pytest.approx(expected)

    assert _forecast(s001) != pytest.approx(_forecast(s002))
