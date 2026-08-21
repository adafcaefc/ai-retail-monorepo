"""Focused contract tests for the Demand Forecasting forecast basket."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.api import agents_html
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting import forecast_basket as basket


FORMULA = "ads * week_factor"
REQUIRED_FIELDS = {
    "store_id",
    "store_name",
    "sku_id",
    "item_name",
    "category_id",
    "category",
    "target",
    "forecast_7d",
    "rop",
    "max",
    "position",
    "suggestion",
    "signal",
    "route",
    "lead_time_days",
    "eta",
    "eta_status",
    "perishable",
    "vendor",
}


def _raw_row(
    *,
    store_id: str = "S001",
    sku_id: str = "SKU-001",
    ads: float = 10.0,
    forecast_7d: float | None = None,
    rop: float = 20.0,
    max_qty: float = 40.0,
    position: float = 10.0,
    lead_time_days: float = 2.0,
    import_batch_id: int = 23,
    item_name: str = "Fresh Apples",
    category_id: str = "GRC-C01",
    category: str = "Fruit",
    promo: bool = True,
    viral: bool = True,
    growth_index: float = 1.2,
    perishable: bool = True,
) -> dict:
    return {
        "store_id": store_id,
        "store_name": "Store 001",
        "sku_id": sku_id,
        "item_name": item_name,
        "category_id": category_id,
        "category": category,
        "ads": ads,
        "forecast_7d": ads * 7.45 if forecast_7d is None else forecast_7d,
        "rop": rop,
        "max_qty": max_qty,
        "position": position,
        "lead_time_days": lead_time_days,
        "perishable": perishable,
        "promo": promo,
        "viral": viral,
        "growth_index": growth_index,
        "vendor": "Vendor A",
        "import_batch_id": import_batch_id,
        "snapshot_date": "2026-07-01",
    }


class _Rows:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.rows)


class _Connection:
    """Small SQLAlchemy-result-shaped fake; captures SQL and bound params."""

    def __init__(self, basket_rows: list[dict], dashboard_rows: list[dict]) -> None:
        self.basket_rows = basket_rows
        self.dashboard_rows = dashboard_rows
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters or {}))
        if "f.forecast_7d AS forecast_7d" in sql:
            return _Rows(self.basket_rows)
        return _Rows(self.dashboard_rows)


class _Request:
    def __init__(self, query_params: dict[str, str]) -> None:
        self.query_params = query_params


def _build_fake(
    monkeypatch: pytest.MonkeyPatch,
    connection: _Connection,
    scope: DashboardScope | None = None,
) -> dict:
    monkeypatch.setattr(
        basket,
        "formulas",
        lambda wanted: {basket.FORECAST_FORMULA_ID: FORMULA},
    )
    return basket.build_forecast_basket(scope, connection=connection)


def test_basket_contract_calculates_suggestion_signals_route_and_eta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _raw_row(
            sku_id="SKU-DIRECT",
            ads=10,
            rop=20,
            max_qty=40,
            position=10,
            lead_time_days=2,
            growth_index=1.2,
        ),
        _raw_row(
            sku_id="SKU-FLOW",
            ads=5,
            rop=5,
            max_qty=2,
            position=5,
            lead_time_days=4,
            promo=False,
            viral=False,
            growth_index=0.8,
        ),
        _raw_row(
            sku_id="SKU-CROSS",
            ads=3,
            rop=7,
            max_qty=12,
            position=5,
            lead_time_days=7,
            promo=False,
            viral=False,
            growth_index=1.5,
        ),
    ]
    connection = _Connection(rows, [{"ads": 10}, {"ads": 5}, {"ads": 3}])

    payload = _build_fake(monkeypatch, connection)

    assert payload["grain"] == "sku_store"
    assert payload["source"] == basket.BASKET_SOURCE
    assert payload["row_count"] == 3
    assert payload["action_row_count"] == 2
    assert payload["suggestion_units"] == pytest.approx(37)
    assert payload["basket_forecast_7d"] == pytest.approx(18 * 7.45)
    assert payload["dashboard_forecast_7d"] == pytest.approx(18 * 7.45)
    assert payload["reconciles"] is True

    by_sku = {row["sku_id"]: row for row in payload["rows"]}
    assert by_sku["SKU-DIRECT"]["suggestion"] == 30
    assert by_sku["SKU-FLOW"]["suggestion"] == 0
    assert by_sku["SKU-CROSS"]["suggestion"] == 7
    assert by_sku["SKU-DIRECT"]["signal"] == [
        "below_rop",
        "viral",
        "promo",
        "growth",
    ]
    assert by_sku["SKU-CROSS"]["signal"] == ["below_rop", "growth"]
    assert by_sku["SKU-DIRECT"]["route"] == "direct"
    assert by_sku["SKU-FLOW"]["route"] == "flow"
    assert by_sku["SKU-CROSS"]["route"] == "cross"
    assert all(row["eta"] is None for row in payload["rows"])
    assert all(row["eta_status"] == "unavailable" for row in payload["rows"])
    assert all(REQUIRED_FIELDS <= set(row) for row in payload["rows"])


def test_suggestion_is_never_negative_when_max_is_below_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _raw_row(rop=30, max_qty=4, position=10, ads=1)
    connection = _Connection([row], [{"ads": 1}])

    payload = _build_fake(monkeypatch, connection)

    assert payload["rows"][0]["suggestion"] == 0
    assert payload["suggestion_units"] == 0
    assert payload["action_row_count"] == 0


def test_duplicate_store_sku_rows_fail_without_aggregation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _raw_row()
    connection = _Connection([row, dict(row)], [{"ads": 10}])
    monkeypatch.setattr(
        basket,
        "formulas",
        lambda wanted: {basket.FORECAST_FORMULA_ID: FORMULA},
    )

    with pytest.raises(basket.ForecastBasketIntegrityError, match="Duplicate"):
        basket.build_forecast_basket(connection=connection)


def test_reconciliation_mismatch_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection([_raw_row(ads=10)], [{"ads": 11}])
    monkeypatch.setattr(
        basket,
        "formulas",
        lambda wanted: {basket.FORECAST_FORMULA_ID: FORMULA},
    )

    with pytest.raises(basket.ForecastBasketReconciliationError, match="reconcile"):
        basket.build_forecast_basket(connection=connection)


def test_filters_are_parameterized_and_store_grain_query_has_no_chain_source() -> None:
    scope = DashboardScope(
        legal_entity_id="GRC",
        category_group="GRC-C01",
        store_id="S001",
        sku="Apple",
    )
    sql, params = basket._basket_query(scope)

    assert "fact_inventory_daily" in sql
    assert "fact_inventory_chain_daily" not in sql
    assert "7.05" not in sql
    assert ":legal_entity_id" in sql
    assert ":category_group" in sql
    assert ":store_id" in sql
    assert ":sku_pattern" in sql
    assert params == {
        "legal_entity_id": "GRC",
        "category_group": "GRC-C01",
        "store_id": "S001",
        "sku_pattern": "%apple%",
        "snapshot_date": "2026-07-01",
    }


def test_dashboard_comparison_uses_current_source_branch() -> None:
    all_sql, _ = basket._dashboard_forecast_query(DashboardScope())
    store_sql, _ = basket._dashboard_forecast_query(
        DashboardScope(store_id="S001")
    )

    assert "fact_inventory_chain_daily" in all_sql
    assert "fact_inventory_daily" in store_sql
    assert "synthetic.demand_store_sku_104w" not in all_sql + store_sql
    assert "7.05" not in all_sql + store_sql


def test_unknown_basket_filters_are_rejected_before_backend_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fail_if_called(_scope):
        nonlocal called
        called = True
        raise AssertionError("backend should not run for an unsupported filter")

    monkeypatch.setattr(agents_html, "build_forecast_basket", fail_if_called)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            agents_html.get_demand_forecast_basket(
                _Request({"state": "Low"}),
                None,
                None,
                None,
                None,
            )
        )

    assert raised.value.status_code == 400
    assert "state" in str(raised.value.detail)
    assert called is False


def test_basket_route_passes_only_supported_scope_and_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[DashboardScope] = []
    expected = {"agent": basket.AGENT_ID, "rows": [], "reconciles": True}

    def fake_build(scope):
        seen.append(scope)
        return expected

    monkeypatch.setattr(agents_html, "build_forecast_basket", fake_build)
    response = asyncio.run(
        agents_html.get_demand_forecast_basket(
            _Request(
                {
                    "legal_entity_id": "GRC",
                    "category_group": "GRC-C01",
                    "store_id": "S001",
                    "sku": "Apple",
                }
            ),
            "GRC",
            "GRC-C01",
            "S001",
            "Apple",
        )
    )

    assert response == expected
    assert seen == [
        DashboardScope(
            legal_entity_id="GRC",
            category_group="GRC-C01",
            store_id="S001",
            sku="Apple",
        )
    ]


def _live_or_skip(scope: DashboardScope | None = None) -> dict:
    try:
        return basket.build_forecast_basket(scope)
    except basket.ForecastBasketError as error:
        pytest.fail(f"seeded live source violates basket contract: {error}")
    except Exception as error:  # noqa: BLE001 - environment-only skip
        pytest.skip(f"no seeded retail database: {error}")


@pytest.fixture(scope="module")
def live_all() -> dict:
    return _live_or_skip()


def test_live_all_stores_shape_keys_totals_and_reconciliation(live_all: dict) -> None:
    rows = live_all["rows"]
    keys = {(row["store_id"], row["sku_id"]) for row in rows}

    assert live_all["row_count"] == 16_000
    assert len(rows) == 16_000
    assert len(keys) == 16_000
    assert live_all["action_row_count"] == sum(
        row["suggestion"] > 0 for row in rows
    )
    assert live_all["suggestion_units"] == pytest.approx(
        sum(row["suggestion"] for row in rows)
    )
    assert live_all["basket_forecast_7d"] == pytest.approx(1_809_147.2231469)
    assert live_all["dashboard_forecast_7d"] == pytest.approx(
        live_all["basket_forecast_7d"]
    )
    assert live_all["reconciles"] is True
    assert all(REQUIRED_FIELDS <= set(row) for row in rows)
    assert all(row["eta"] is None for row in rows)
    assert all(row["eta_status"] == "unavailable" for row in rows)


def test_live_selected_store_has_100_rows_and_reconciles() -> None:
    payload = _live_or_skip(DashboardScope(store_id="S001"))

    assert payload["row_count"] == 100
    assert len(payload["rows"]) == 100
    assert {row["store_id"] for row in payload["rows"]} == {"S001"}
    assert payload["basket_forecast_7d"] == pytest.approx(28_024.77359938824)
    assert payload["basket_forecast_7d"] == pytest.approx(
        payload["dashboard_forecast_7d"]
    )
    assert payload["reconciles"] is True


def test_live_filters_apply_before_basket_totals(live_all: dict) -> None:
    grocery = _live_or_skip(DashboardScope(legal_entity_id="GRC"))
    assert grocery["row_count"] < live_all["row_count"]
    assert all(row["category_id"].startswith("GRC-") for row in grocery["rows"])

    category = _live_or_skip(
        DashboardScope(legal_entity_id="GRC", category_group="GRC-C01")
    )
    assert category["row_count"] > 0
    assert all(row["category_id"] == "GRC-C01" for row in category["rows"])

    sample = category["rows"][0]
    sku_search = _live_or_skip(
        DashboardScope(
            legal_entity_id="GRC",
            category_group="GRC-C01",
            sku=sample["sku_id"],
        )
    )
    assert sku_search["row_count"] > 0
    assert all(
        sample["sku_id"].lower() in row["sku_id"].lower()
        or sample["sku_id"].lower() in row["item_name"].lower()
        for row in sku_search["rows"]
    )

    name_token = sample["item_name"].split()[0]
    name_search = _live_or_skip(
        DashboardScope(
            legal_entity_id="GRC",
            category_group="GRC-C01",
            sku=name_token,
        )
    )
    assert name_search["row_count"] > 0
    assert all(
        name_token.lower() in row["sku_id"].lower()
        or name_token.lower() in row["item_name"].lower()
        for row in name_search["rows"]
    )

    combined = _live_or_skip(
        DashboardScope(
            legal_entity_id="GRC",
            category_group="GRC-C01",
            sku=sample["sku_id"],
        )
    )
    assert combined["row_count"] == sku_search["row_count"]
    assert combined["basket_forecast_7d"] == pytest.approx(
        combined["dashboard_forecast_7d"]
    )


def test_live_route_mapping_matches_replenishment_convention(live_all: dict) -> None:
    for row in live_all["rows"]:
        lead = row["lead_time_days"]
        expected = "direct" if lead <= 2 else "flow" if lead <= 4 else "cross"
        assert row["route"] == expected


def test_live_source_does_not_use_mockup_or_synthetic_forecast() -> None:
    assert basket.BASKET_SOURCE == "retail.fact_inventory_daily.forecast_7d"
    assert "synthetic" not in basket.BASKET_SOURCE
    assert "7.05" not in basket.BASKET_SOURCE
