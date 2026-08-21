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


class _CategoryRows:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class _CategoryConnection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.statement = ""

    def execute(self, statement, _parameters=None):
        self.statement = str(statement)
        return _CategoryRows(self.rows)


def test_store_scope_uses_store_grain_rows_for_all_downstream_inputs() -> None:
    all_stores = _build_or_skip()
    s001 = _build_or_skip(DashboardScope.from_query(store_id="S001"))
    s002 = _build_or_skip(DashboardScope.from_query(store_id="S002"))

    # All Stores retains the existing chain-net source and its 800 item rows.
    assert len(all_stores["items"]) == 800
    assert len(all_stores["stores"]) == 160
    # v8.5/batch-23's current Forecast 7d source total, also reconciled by
    # the approved synthetic table, is 1,809,147.2231469.
    assert _forecast(all_stores) == pytest.approx(1_809_147.2231469)
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
    assert _forecast(s001) == pytest.approx(28_024.77359938824)
    assert _forecast(s002) == pytest.approx(33_217.00649819611)
    assert _forecast(s001) != pytest.approx(_forecast(s002))
    assert s001["scope"] == {"store_id": "S001"}
    assert s002["scope"] == {"store_id": "S002"}
    assert s001["scope_limitations"]


def test_predicted_to_trend_is_not_the_whole_store_under_store_scope() -> None:
    """Regression: `is_trending` used to be a rank+quota allocation sized to
    the vertical-wide `Trending SKUs` reference count. Once scoped to a
    single Store (100 rows, far fewer than most verticals' count), the quota
    always exceeded the row count and every row in the Store was marked
    trending. `is_trending` is now a per-row formula (`viral OR growth>1.25`)
    that composes correctly under scope -- it should mark only some rows.
    """
    s001 = _build_or_skip(DashboardScope.from_query(store_id="S001"))

    trending = [row for row in s001["items"] if row["is_trending"]]
    assert 0 < len(trending) < len(s001["items"])

    # And membership must exactly match the stated formula -- not merely be
    # "fewer than all of them".
    expected = {
        row["sku_id"]
        for row in s001["items"]
        if "viral" in row["signals"] or float(row["growth"]) > 1.25
    }
    assert {row["sku_id"] for row in trending} == expected


def test_store_scope_is_not_reported_as_ignored_by_the_descriptor() -> None:
    payload = _build_or_skip(DashboardScope.from_query(store_id="S001"))

    descriptor = dashboard.SUPPORTED_FILTERS
    assert "store_id" in descriptor
    assert DashboardScope(store_id="S001").ignored_by(descriptor) == ()
    assert payload["scope"]["store_id"] == "S001"


def test_engine_store_category_ids_reads_the_store_category_relationship() -> None:
    connection = _CategoryConnection(
        [
            {"store_id": "S001", "category_id": "GRC-C01"},
            {"store_id": "S001", "category_id": "GRC-C02"},
            {"store_id": "S020", "category_id": "GRC-C01"},
            {"store_id": "S037", "category_id": "GMR-C01"},
        ]
    )

    result = dashboard.engine_store_category_ids(connection)

    assert result == {
        "S001": ["GRC-C01", "GRC-C02"],
        "S020": ["GRC-C01"],
        "S037": ["GMR-C01"],
    }
    assert "temp_engine_store" in connection.statement
    assert "t.[Store]" in connection.statement
    assert "t.[Cat]" in connection.statement


def test_store_filter_options_follow_engine_store_category_membership() -> None:
    grocery = _build_or_skip(
        DashboardScope.from_query(legal_entity_id="GRC")
    )
    grocery_fruit = _build_or_skip(
        DashboardScope.from_query(
            legal_entity_id="GRC",
            category_group="GRC-C01",
        )
    )

    expected_grocery_stores = {f"S{number:03d}" for number in range(1, 21)}
    grocery_ids = {row["value"] for row in grocery["filter_options"]["stores"]}
    fruit_ids = {
        row["value"] for row in grocery_fruit["filter_options"]["stores"]
    }

    # All categories keeps the legal entity's current Store population.
    assert grocery_ids == expected_grocery_stores
    # GRC-C01 is present in ENGINE_STORE only for S001..S020; a GMR store
    # such as S037 must not leak into the category-scoped dropdown.
    assert fruit_ids == expected_grocery_stores
    assert "S037" not in fruit_ids
    assert all(
        "GRC-C01" in row["category_ids"]
        for row in grocery_fruit["filter_options"]["stores"]
    )


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
    assert _forecast(all_stores) == pytest.approx(1_809_147.2231469)

    for payload, store_id, expected in (
        (s001, "S001", 28_024.77359938824),
        (s002, "S002", 33_217.00649819611),
    ):
        assert payload["scope"] == {"store_id": store_id}
        assert "ignored_filters" not in payload
        assert len(payload["items"]) == 100
        assert {row["store_id"] for row in payload["items"]} == {store_id}
        assert {row["store_id"] for row in payload["stores"]} == {store_id}
        assert _forecast(payload) == pytest.approx(expected)

    assert _forecast(s001) != pytest.approx(_forecast(s002))
