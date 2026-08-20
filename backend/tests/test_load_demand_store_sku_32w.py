from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "backend" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_demand_store_sku_32w as generator
import load_demand_store_sku_32w as loader


@pytest.fixture(scope="module")
def candidate() -> loader.CandidateArtifact:
    return loader.load_candidate_artifact()


def test_approved_candidate_schema_shape_and_fingerprint(
    candidate: loader.CandidateArtifact,
) -> None:
    assert candidate.row_count == 16_000
    assert generator.BUSINESS_COLUMNS == (
        "sku_id",
        "store_id",
        "cat",
        *generator.ACTUAL_COLUMNS,
        *generator.FORECAST_COLUMNS,
    )
    assert len(generator.BUSINESS_COLUMNS) == 35
    assert len({row.key for row in candidate.rows}) == 16_000
    assert len({row.sku_id for row in candidate.rows}) == 800
    assert len({row.store_id for row in candidate.rows}) == 160
    assert {
        sum(row.store_id == store_id for row in candidate.rows)
        for store_id in {row.store_id for row in candidate.rows}
    } == {100}
    assert all(row.cat for row in candidate.rows)
    assert candidate.fingerprint == loader.EXPECTED_OUTPUT_FINGERPRINT


def test_candidate_quantity_values_are_populated_and_non_negative(
    candidate: loader.CandidateArtifact,
) -> None:
    values = [value for row in candidate.rows for value in (*row.actuals, *row.forecasts)]
    assert len(values) == 512_000
    assert all(value.is_finite() and value >= 0 for value in values)


def test_ddl_contract_is_simple_and_exact() -> None:
    ddl = loader.DDL_PATH.read_text(encoding="utf-8").lower()
    assert len(loader.split_sql_batches(ddl)) == 2
    assert "create schema synthetic" in ddl
    assert "create table synthetic.demand_store_sku_32w" in ddl
    assert "primary key clustered (sku_id, store_id)" in ddl
    assert ddl.count("decimal(20,6) not null") == 32
    assert ddl.count("nvarchar(30) not null") == 2
    assert "nvarchar(20) not null" in ddl
    assert "demand_store_week" not in ddl
    assert all(f"{column} " in ddl for column in generator.BUSINESS_COLUMNS)


def test_w1_reconciliation_logic_accepts_quantization_and_rejects_large_drift(
    candidate: loader.CandidateArtifact,
) -> None:
    loaded = {row.key: row.forecasts[0] for row in candidate.rows}
    source_with_quantization = dict(loaded)
    first_key = candidate.rows[0].key
    source_with_quantization[first_key] += Decimal("0.0000005")
    passing = loader.reconcile_w1_values(loaded, source_with_quantization)
    assert passing["rows_checked"] == 16_000
    assert passing["rows_passed"] == 16_000
    assert passing["rows_failed"] == 0
    assert passing["passed"] is True

    source_with_drift = dict(loaded)
    source_with_drift[first_key] += Decimal("0.0000011")
    failing = loader.reconcile_w1_values(loaded, source_with_drift)
    assert failing["rows_passed"] == 15_999
    assert failing["rows_failed"] == 1
    assert failing["passed"] is False


def test_existing_table_idempotence_and_conflict_classification() -> None:
    assert (
        loader.classify_existing_copy(
            generator.EXPECTED_ROW_COUNT,
            loader.EXPECTED_OUTPUT_FINGERPRINT,
        )
        == "NOOP_ALREADY_LOADED"
    )
    assert loader.classify_existing_copy(15_999, loader.EXPECTED_OUTPUT_FINGERPRINT) == "CONFLICT"
    assert loader.classify_existing_copy(16_000, "0" * 64) == "CONFLICT"


def test_demand_trend_aggregates_before_dividing() -> None:
    row_a = generator.DemandSkuStoreRow(
        sku_id="A",
        store_id="S1",
        cat="C1",
        actuals=(Decimal("1"),) * 16,
        forecasts=(Decimal("2"),) * 16,
    )
    row_b = generator.DemandSkuStoreRow(
        sku_id="B",
        store_id="S1",
        cat="C1",
        actuals=(Decimal("100"),) * 16,
        forecasts=(Decimal("100"),) * 16,
    )
    aggregate_trend = generator.calculate_trend([row_a, row_b])
    expected = float(Decimal("408") / Decimal("404") - Decimal("1"))
    assert aggregate_trend == pytest.approx(expected)
    assert aggregate_trend != pytest.approx(0.5)
