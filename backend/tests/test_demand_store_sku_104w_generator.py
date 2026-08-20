from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_demand_store_sku_104w as generator


@pytest.fixture(scope="module")
def previous_rows():
    rows, _manifest, fingerprint = generator.load_previous_rows()
    assert fingerprint == generator.APPROVED_PREVIOUS_FINGERPRINT
    return rows


@pytest.fixture(scope="module")
def snapshot(previous_rows):
    vertical_by_store = {}
    for row in previous_rows:
        vertical = row.sku_id.split("-", 1)[0]
        vertical_by_store.setdefault(row.store_id, vertical)
        assert vertical_by_store[row.store_id] == vertical

    sources = []
    for row in previous_rows:
        sources.append(
            generator.SourceSkuStore(
                sku_id=row.sku_id,
                store_id=row.store_id,
                cat=row.cat,
                ads=Decimal("10.00"),
                forecast_7d=row.forecasts[0],
                vertical_id=vertical_by_store[row.store_id],
                size_index=Decimal("1.00"),
                health_index=Decimal("1.00"),
                footfall_index=Decimal("1.00"),
                cluster="Test",
                channel="Physical",
                seasonality_index=Decimal("1.00"),
                growth_index=Decimal("1.00"),
            )
        )
    return generator.SourceSnapshot(source_rows=tuple(sources))


@pytest.fixture(scope="module")
def rows(snapshot, previous_rows):
    return generator.generate_dataset(snapshot, previous_rows)


@pytest.fixture(scope="module")
def validation(rows, snapshot, previous_rows):
    return generator.validate_dataset(rows, snapshot, previous_rows)


def test_shape_and_104w_schema(rows):
    assert len(rows) == 16_000
    assert len(generator.BUSINESS_COLUMNS) == 107
    assert len(generator.ACTUAL_COLUMNS) == 52
    assert len(generator.FORECAST_COLUMNS) == 52
    assert generator.ACTUAL_COLUMNS[0] == "actual_w52"
    assert generator.ACTUAL_COLUMNS[-1] == "actual_w1"
    assert generator.FORECAST_COLUMNS[0] == "forecast_w1"
    assert generator.FORECAST_COLUMNS[-1] == "forecast_w52"
    assert all(tuple(row.business_dict()) == generator.BUSINESS_COLUMNS for row in rows)
    assert len({row.key for row in rows}) == 16_000
    assert len({row.sku_id for row in rows}) == 800
    assert len({row.store_id for row in rows}) == 160
    assert {
        sum(row.store_id == store for row in rows)
        for store in {row.store_id for row in rows}
    } == {100}
    assert all(row.cat for row in rows)


def test_all_104_period_values_are_finite_and_non_negative(rows):
    values = [value for row in rows for value in (*row.actuals, *row.forecasts)]
    assert len(values) == 1_664_000
    assert all(value.is_finite() and value >= 0 for value in values)
    assert all(len(set(row.actuals)) > 1 for row in rows)
    assert all(len(set(row.forecasts[1:])) > 1 for row in rows)


def test_approved_32w_block_is_preserved_exactly(rows, previous_rows, validation):
    assert validation["preservation"]["matching_rows"] == 16_000
    assert validation["preservation"]["preserved_rows"] == 16_000
    assert validation["preservation"]["changed_existing_values"] == 0

    previous = {row.key: row.business_dict() for row in previous_rows}
    current = {row.key: row.business_dict() for row in rows}
    for key, old_values in previous.items():
        assert all(current[key][column] == old_values[column] for column in generator.PRESERVED_COLUMNS)


def test_w1_and_new_extension_seed_behavior(rows, snapshot, previous_rows):
    source_by_key = {source.key: source for source in snapshot.source_rows}
    assert all(
        row.forecast_for_week(1) == generator.quantize_qty(source_by_key[row.key].forecast_7d)
        for row in rows
    )

    changed = generator.generate_dataset(
        snapshot,
        previous_rows,
        generator.GeneratorParameters(seed=generator.FIXED_SEED + 1),
    )
    assert any(a.actuals[:36] != b.actuals[:36] for a, b in zip(rows, changed))
    assert any(a.forecasts[16:] != b.forecasts[16:] for a, b in zip(rows, changed))
    assert all(a.actuals[36:] == b.actuals[36:] for a, b in zip(rows, changed))
    assert all(a.forecasts[:16] == b.forecasts[:16] for a, b in zip(rows, changed))
    assert all(
        (a.sku_id, a.store_id, a.cat) == (b.sku_id, b.store_id, b.cat)
        for a, b in zip(rows, changed)
    )


def test_same_seed_fingerprint_is_reproducible(rows, snapshot, previous_rows):
    rerun = generator.generate_dataset(snapshot, previous_rows)
    assert generator.output_fingerprint(rows) == generator.output_fingerprint(rerun)
    assert [generator.canonical_row_text(row) for row in rows] == [
        generator.canonical_row_text(row) for row in rerun
    ]


def test_extension_boundaries_and_demand_trend_regression(validation):
    assert validation["continuity"]["historical_w17_to_w16"]["rows_exceeding_threshold"] == 0
    assert validation["continuity"]["future_w16_to_w17"]["rows_exceeding_threshold"] == 0
    assert validation["demand_trend_regression"]["changed_scope_count"] == 0
    assert validation["demand_trend_regression"]["scopes"]["GRC"]["after_trend_pct"] == pytest.approx(
        5.595460833244484
    )
    assert validation["demand_trend_regression"]["scopes"]["ALL"]["after_trend_pct"] == pytest.approx(
        5.398411726147
    )


def test_required_value_counts_and_w1_reconciliation(validation):
    assert validation["shape"] == {
        "row_count": 16_000,
        "column_count": 107,
        "sku_count": 800,
        "store_count": 160,
        "rows_per_store": 100,
        "unique_sku_store_pairs": 16_000,
    }
    assert validation["value_counts"] == {
        "historical_synthetic": 832_000,
        "source_w1": 16_000,
        "synthetic_future": 816_000,
        "total_period_values": 1_664_000,
        "existing_preserved": 512_000,
        "new_historical": 576_000,
        "new_future": 576_000,
    }
    assert validation["w1_reconciliation"]["passed_count"] == 16_000
    assert validation["w1_reconciliation"]["failed_count"] == 0


@pytest.mark.skipif(
    not (
        generator.REPO_ROOT / "artifacts" / "demand_store_sku_104w_poc_v1.csv"
    ).exists(),
    reason="104W artifacts have not been generated yet",
)
def test_generated_csv_and_xlsx_have_identical_canonical_rows():
    parity = generator.validate_export_parity(
        generator.REPO_ROOT / "artifacts" / "demand_store_sku_104w_poc_v1.csv",
        generator.REPO_ROOT / "artifacts" / "demand_store_sku_104w_poc_v1.xlsx",
    )
    assert parity == {
        "csv_rows": 16_000,
        "xlsx_rows": 16_000,
        "same_logical_rows": True,
    }
