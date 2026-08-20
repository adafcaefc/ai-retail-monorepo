from __future__ import annotations

import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import generate_demand_store_sku_32w as generator


VERTICALS = ("GRC", "DGT", "ELC", "FSH", "GMR", "HNB", "HNL", "OMN")


@pytest.fixture(scope="module")
def snapshot() -> generator.SourceSnapshot:
    source_rows: list[generator.SourceSkuStore] = []
    for store_index in range(1, 161):
        store_id = f"S{store_index:03d}"
        store_group = (store_index - 1) // 20
        for local_sku_index in range(1, 101):
            sku_index = store_group * 100 + local_sku_index
            vertical = VERTICALS[(sku_index - 1) // 100]
            sku_id = f"{vertical}-{local_sku_index:03d}"
            cat = f"{vertical}-C{((local_sku_index - 1) % 10) + 1:02d}"
            ads = Decimal("1.25") + Decimal(sku_index % 37) / Decimal("100")
            ads += Decimal(store_index % 19) / Decimal("200")
            forecast = ads * Decimal("7.45")
            source_rows.append(
                generator.SourceSkuStore(
                    sku_id=sku_id,
                    store_id=store_id,
                    cat=cat,
                    ads=ads,
                    forecast_7d=forecast,
                    vertical_id=VERTICALS[(store_index - 1) // 20],
                    size_index=Decimal("0.90") + Decimal(store_index % 11) / Decimal("100"),
                    health_index=Decimal("0.95") + Decimal(store_index % 7) / Decimal("200"),
                    footfall_index=Decimal("0.88") + Decimal(store_index % 13) / Decimal("100"),
                    cluster=f"Cluster {store_index % 4}",
                    channel="Physical",
                    seasonality_index=Decimal("0.90") + Decimal(sku_index % 15) / Decimal("100"),
                    growth_index=Decimal("0.96") + Decimal(sku_index % 12) / Decimal("100"),
                    is_promo_eligible=sku_index % 3 == 0,
                    cannibalisation_pct=Decimal("0.05"),
                    is_viral=sku_index % 47 == 0,
                )
            )
    return generator.SourceSnapshot(source_rows=tuple(source_rows))


@pytest.fixture(scope="module")
def rows(snapshot: generator.SourceSnapshot) -> list[generator.DemandSkuStoreRow]:
    return generator.generate_dataset(snapshot)


def test_shape_schema_uniqueness_and_category_mapping(
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    assert len(rows) == 16_000
    assert len(generator.BUSINESS_COLUMNS) == 35
    assert all(tuple(row.business_dict()) == generator.BUSINESS_COLUMNS for row in rows)
    assert len({row.key for row in rows}) == 16_000
    assert len({row.sku_id for row in rows}) == 800
    assert len({row.store_id for row in rows}) == 160
    assert {sum(row.store_id == store for row in rows) for store in {row.store_id for row in rows}} == {100}
    assert all(row.cat for row in rows)


def test_source_forecast_w1_is_preserved_per_sku_store(
    snapshot: generator.SourceSnapshot,
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    source_by_key = {source.key: source for source in snapshot.source_rows}
    differences = [
        abs(row.forecast_for_week(1) - source_by_key[row.key].forecast_7d)
        for row in rows
    ]
    assert len(differences) == 16_000
    assert max(differences) <= generator.W1_RECONCILIATION_TOLERANCE
    assert all(
        row.forecast_for_week(1)
        == generator.quantize_qty(source_by_key[row.key].forecast_7d)
        for row in rows
    )


def test_all_period_values_are_finite_and_non_negative(
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    values = [value for row in rows for value in (*row.actuals, *row.forecasts)]
    assert len(values) == 512_000
    assert all(value.is_finite() and value >= 0 for value in values)
    assert all(len(set(row.actuals)) > 1 for row in rows)
    assert all(len(set(row.forecasts[1:])) > 1 for row in rows)


def test_same_seed_is_deterministic_and_changed_seed_is_controlled(
    snapshot: generator.SourceSnapshot,
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    rerun = generator.generate_dataset(snapshot)
    assert generator.output_fingerprint(rows) == generator.output_fingerprint(rerun)
    assert [generator.canonical_row_text(row) for row in rows] == [
        generator.canonical_row_text(row) for row in rerun
    ]

    changed = generator.generate_dataset(
        snapshot,
        generator.GeneratorParameters(seed=generator.FIXED_SEED + 1),
    )
    assert any(a.actuals != b.actuals for a, b in zip(rows, changed))
    assert any(a.forecasts[1:] != b.forecasts[1:] for a, b in zip(rows, changed))
    assert all(a.forecasts[0] == b.forecasts[0] for a, b in zip(rows, changed))
    assert all((a.sku_id, a.store_id, a.cat) == (b.sku_id, b.store_id, b.cat) for a, b in zip(rows, changed))


def test_trend_supports_store_category_and_sku_filters(
    snapshot: generator.SourceSnapshot,
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    category_keys = {source.key for source in snapshot.source_rows if source.cat == "GRC-C01"}
    store_keys = {source.key for source in snapshot.source_rows if source.store_id == "S001"}
    sku_keys = {source.key for source in snapshot.source_rows if source.sku_id == "GRC-001"}
    assert category_keys and store_keys and sku_keys
    trends = [
        generator.calculate_trend(rows, category_keys),
        generator.calculate_trend(rows, store_keys),
        generator.calculate_trend(rows, sku_keys),
        generator.calculate_trend(rows, category_keys & store_keys),
        generator.calculate_trend(rows, sku_keys & store_keys),
    ]
    assert all(isinstance(value, float) and math.isfinite(value) for value in trends)


def test_trend_aggregates_before_dividing() -> None:
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


def test_full_validation_reports_required_counts_and_trend(
    snapshot: generator.SourceSnapshot,
    rows: list[generator.DemandSkuStoreRow],
) -> None:
    validation = generator.validate_dataset(rows, snapshot)
    assert validation["shape"]["row_count"] == 16_000
    assert validation["shape"]["column_count"] == 35
    assert validation["value_counts"] == {
        "historical_synthetic": 256_000,
        "source_w1": 16_000,
        "synthetic_future": 240_000,
        "total_period_values": 512_000,
    }
    assert validation["w1_reconciliation"]["passed_count"] == 16_000
    assert validation["w1_reconciliation"]["failed_count"] == 0
    assert validation["filter_scope_validation"]["scopes"]["GRC"]["row_count"] == 2_000
    assert validation["plausibility"]["invalid_extreme_series_count"] == 0
