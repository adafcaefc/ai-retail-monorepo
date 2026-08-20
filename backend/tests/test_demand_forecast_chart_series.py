from __future__ import annotations

from decimal import Decimal

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.retail.demand_forecasting import dashboard


class _MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.statement = ""
        self.parameters = None

    def execute(self, statement, parameters=None):
        self.statement = str(statement)
        self.parameters = parameters or {}
        return _MappingResult(self.row)


def _aggregate_row():
    return {
        "row_count": 7,
        **{
            f"actual_w{week}_total": Decimal(str(week))
            for week in dashboard.CHART_ACTUAL_WEEKS
        },
        **{
            f"forecast_w{week}_total": Decimal(str(100 + week))
            for week in dashboard.CHART_FORECAST_WEEKS
        },
    }


def test_chart_series_uses_104w_source_and_exposes_all_weekly_columns():
    connection = _Connection(_aggregate_row())

    result = dashboard._demand_forecast_series(
        connection,
        DashboardScope(),
    )

    assert result["source"] == "synthetic.demand_store_sku_104w"
    assert result["grain"] == "sku_store"
    assert result["row_count"] == 7
    assert len([key for key in result if key.startswith("actual_w")]) == 52
    assert len([key for key in result if key.startswith("forecast_w")]) == 52
    assert result["actual_w52"] == 52
    assert result["actual_w1"] == 1
    assert result["forecast_w1"] == 101
    assert result["forecast_w52"] == 152
    assert "synthetic.demand_store_sku_104w" in connection.statement
    assert "synthetic.demand_store_sku_32w" not in connection.statement


def test_chart_series_binds_legal_entity_category_store_and_sku_search_filters():
    connection = _Connection(_aggregate_row())

    dashboard._demand_forecast_series(
        connection,
        DashboardScope(
            legal_entity_id="GRC",
            category_group="GRC-C01",
            store_id="S001",
            sku="Fruit",
        ),
    )

    assert "s.vertical_id = :legal_entity_id" in connection.statement
    assert "d.cat = :category_group" in connection.statement
    assert "d.store_id = :store_id" in connection.statement
    assert "JOIN retail.dim_item i ON i.item_id = d.sku_id" in connection.statement
    assert "LOWER(d.sku_id) LIKE :sku_pattern" in connection.statement
    assert "LOWER(i.name) LIKE :sku_pattern" in connection.statement
    assert connection.parameters == {
        "legal_entity_id": "GRC",
        "category_group": "GRC-C01",
        "store_id": "S001",
        "sku_pattern": "%fruit%",
    }


def test_demand_trend_source_remains_32w_while_chart_source_is_104w():
    assert dashboard.SYNTHETIC_DEMAND_TABLE == "synthetic.demand_store_sku_32w"
    assert dashboard.SYNTHETIC_DEMAND_CHART_TABLE == "synthetic.demand_store_sku_104w"
