"""Load and validate the approved SKU x Store synthetic demand table.

This loader deliberately does not call the generator.  It validates the
approved canonical CSV and manifest, reruns the v8.5/batch-23 read-only source
preflight, then creates and loads only ``synthetic.demand_store_sku_32w`` when
that table is absent.  An existing differing table is a hard conflict; there
is no replace or truncate mode.

Run from the repository root::

    .venv/bin/python backend/scripts/load_demand_store_sku_32w.py \
        --test-result 'PASS: focused SQL-load tests'

The SQL write is one transaction with parameterized batched inserts.  Shape,
source W+1, fingerprint, Trend, horizon, and filter checks run before commit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "backend" / "scripts"
if str(REPO_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import generate_demand_store_sku_32w as generator
from src.retail_data_bootstrap.database import open_connection


GENERATION_NAME = generator.GENERATION_NAME
EXPECTED_OUTPUT_FINGERPRINT = (
    "0e3df661a941440d0e43fa93e62fe166d69c5d12caa1b6ed65333729c78f550d"
)
TABLE_SCHEMA = "synthetic"
TABLE_NAME = "demand_store_sku_32w"
FULL_TABLE_NAME = f"{TABLE_SCHEMA}.{TABLE_NAME}"
SUPERSEDED_TABLE_NAME = "synthetic.demand_store_week"
CSV_PATH = REPO_ROOT / "artifacts" / "demand_store_sku_32w_poc_v1.csv"
MANIFEST_PATH = REPO_ROOT / "artifacts" / "demand_store_sku_32w_poc_v1_manifest.json"
DDL_PATH = REPO_ROOT / "sql" / "synthetic" / "001_create_demand_store_sku_32w.sql"
REPORT_PATH = REPO_ROOT / "plans" / "demand-store-sku-32w-sql-load-report.md"
INSERT_BATCH_SIZE = 1_000
W1_TOLERANCE = Decimal("0.000001")
TREND_TOLERANCE = Decimal("0.000001")
SOURCE_DATE = generator.SOURCE_SNAPSHOT_DATE
SOURCE_BATCH = generator.SOURCE_IMPORT_BATCH_ID

SAMPLE_KEYS = (
    ("GRC-001", "S001"),
    ("GRC-001", "S002"),
    ("GRC-002", "S001"),
    ("GRC-002", "S002"),
)

TARGET_COLUMN_CONTRACT = (
    ("sku_id", "nvarchar", 60, None, None, False),
    ("store_id", "nvarchar", 40, None, None, False),
    ("cat", "nvarchar", 60, None, None, False),
    *(
        (column, "decimal", None, 20, 6, False)
        for column in (*generator.ACTUAL_COLUMNS, *generator.FORECAST_COLUMNS)
    ),
)
SOURCE_TYPE_CONTRACT = {
    ("dim_item", "item_id"): ("nvarchar", 60, False),
    ("dim_item", "category_id"): ("nvarchar", 60, True),
    ("dim_store", "store_id"): ("nvarchar", 40, False),
    ("fact_inventory_daily", "item_key"): ("nvarchar", 60, False),
    ("fact_inventory_daily", "store_key"): ("nvarchar", 40, False),
}


class LoadError(RuntimeError):
    """Raised when candidate, source, schema, or SQL validation fails."""


class CandidateError(LoadError):
    """Raised when the approved local artifact does not match its contract."""


class TableConflictError(LoadError):
    """Raised when an existing target table differs from the approved copy."""


@dataclass(frozen=True)
class CandidateArtifact:
    rows: tuple[generator.DemandSkuStoreRow, ...]
    manifest: dict[str, Any]
    csv_path: Path
    manifest_path: Path
    fingerprint: str

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class TargetInspection:
    schema_exists: bool
    exists: bool
    columns: tuple[dict[str, Any], ...] = ()
    primary_key: tuple[str, ...] = ()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return generator.decimal_text(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _require(condition: bool, message: str, error_type: type[LoadError] = LoadError) -> None:
    if not condition:
        raise error_type(message)


def _as_int(value: Any) -> int:
    return int(value or 0)


def _as_decimal(value: Any) -> Decimal:
    try:
        result = generator.decimal_value(value)
    except (InvalidOperation, ValueError) as exc:
        raise LoadError(f"Expected a finite SQL numeric value, got {value!r}") from exc
    return result


def _row_dict(cursor: Any, row: Any) -> dict[str, Any]:
    if row is None:
        raise LoadError("Expected a SQL row but received none")
    return {description[0]: value for description, value in zip(cursor.description, row)}


def _fetch_one(cursor: Any, statement: str, parameters: Sequence[Any] = ()) -> dict[str, Any]:
    cursor.execute(statement, tuple(parameters))
    return _row_dict(cursor, cursor.fetchone())


def _chunked(values: Sequence[tuple[Any, ...]], size: int) -> Iterable[Sequence[tuple[Any, ...]]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _candidate_row_from_csv(raw: Mapping[str, str], line_number: int) -> generator.DemandSkuStoreRow:
    if any(raw.get(column) in (None, "") for column in generator.BUSINESS_COLUMNS):
        raise CandidateError(f"CSV line {line_number} has a null/blank business value")
    actuals: list[Decimal] = []
    forecasts: list[Decimal] = []
    for column in (*generator.ACTUAL_COLUMNS, *generator.FORECAST_COLUMNS):
        text = raw[column]
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise CandidateError(f"CSV line {line_number} has invalid {column}: {text!r}") from exc
        if not value.is_finite() or value < 0:
            raise CandidateError(f"CSV line {line_number} has invalid {column}: {text!r}")
        if text != generator.quantity_text(value):
            raise CandidateError(
                f"CSV line {line_number} {column} is not canonical six-decimal text: {text!r}"
            )
        (actuals if column in generator.ACTUAL_COLUMNS else forecasts).append(value)
    return generator.DemandSkuStoreRow(
        sku_id=raw["sku_id"],
        store_id=raw["store_id"],
        cat=raw["cat"],
        actuals=tuple(actuals),
        forecasts=tuple(forecasts),
    )


def load_candidate_artifact(
    csv_path: Path = CSV_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> CandidateArtifact:
    """Validate the approved CSV/manifest without generating or changing values."""

    _require(csv_path.is_file(), f"Approved CSV not found: {csv_path}", CandidateError)
    _require(manifest_path.is_file(), f"Approved manifest not found: {manifest_path}", CandidateError)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CandidateError(f"Manifest is not valid JSON: {manifest_path}") from exc
    _require(isinstance(manifest, dict), "Manifest must be a JSON object", CandidateError)
    _require(manifest.get("generation_name") == GENERATION_NAME, "Unexpected generation name", CandidateError)
    _require(
        manifest.get("source_revision") == generator.SOURCE_REVISION,
        "Manifest source revision is not the approved v8.5 revision",
        CandidateError,
    )
    _require(
        manifest.get("source_import_batch") == SOURCE_BATCH,
        "Manifest source import batch is not 23",
        CandidateError,
    )
    _require(
        manifest.get("source_snapshot_date") == SOURCE_DATE.isoformat(),
        "Manifest source snapshot date is not 2026-07-01",
        CandidateError,
    )
    _require(
        manifest.get("output_fingerprint") == EXPECTED_OUTPUT_FINGERPRINT,
        "Manifest output fingerprint is not the approved fingerprint",
        CandidateError,
    )
    contract = manifest.get("column_contract", {})
    _require(
        contract.get("columns") == list(generator.BUSINESS_COLUMNS)
        and contract.get("canonical_sort") == ["sku_id", "store_id"],
        "Manifest column contract does not match the approved 35-column schema",
        CandidateError,
    )

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(
            tuple(reader.fieldnames or ()) == generator.BUSINESS_COLUMNS,
            "Approved CSV columns/order do not match the 35-column contract",
            CandidateError,
        )
        rows = [
            _candidate_row_from_csv(raw, line_number=index + 2)
            for index, raw in enumerate(reader)
        ]

    rows.sort(key=lambda row: row.key)
    _require(len(rows) == generator.EXPECTED_ROW_COUNT, f"Expected 16,000 CSV rows, found {len(rows)}", CandidateError)
    _require(len({row.key for row in rows}) == generator.EXPECTED_ROW_COUNT, "CSV has duplicate SKU-store pairs", CandidateError)
    _require(len({row.sku_id for row in rows}) == generator.EXPECTED_SKU_COUNT, "CSV does not contain 800 SKUs", CandidateError)
    _require(len({row.store_id for row in rows}) == generator.EXPECTED_STORE_COUNT, "CSV does not contain 160 stores", CandidateError)
    _require(
        {sum(row.store_id == store_id for row in rows) for store_id in {row.store_id for row in rows}}
        == {generator.EXPECTED_ROWS_PER_STORE},
        "CSV does not contain exactly 100 rows per store",
        CandidateError,
    )
    _require(all(row.cat.strip() for row in rows), "CSV contains a blank category", CandidateError)

    fingerprint = generator.output_fingerprint(rows)
    _require(
        fingerprint == EXPECTED_OUTPUT_FINGERPRINT,
        f"Approved CSV fingerprint mismatch: {fingerprint}",
        CandidateError,
    )
    expected_manifest_counts = {
        "output_row_count": generator.EXPECTED_ROW_COUNT,
        "sku_count": generator.EXPECTED_SKU_COUNT,
        "store_count": generator.EXPECTED_STORE_COUNT,
        "historical_value_count": generator.HISTORICAL_VALUE_COUNT,
        "source_w1_value_count": generator.SOURCE_W1_VALUE_COUNT,
        "synthetic_future_value_count": generator.SYNTHETIC_FUTURE_VALUE_COUNT,
        "total_period_value_count": generator.TOTAL_PERIOD_VALUE_COUNT,
    }
    for key, expected in expected_manifest_counts.items():
        _require(manifest.get(key) == expected, f"Manifest {key} is {manifest.get(key)!r}, expected {expected}", CandidateError)
    return CandidateArtifact(tuple(rows), manifest, csv_path, manifest_path, fingerprint)


def source_type_contract(cursor: Any) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT s.name AS schema_name, t.name AS table_name, c.name AS column_name,
               ty.name AS data_type, c.max_length, c.precision, c.scale,
               c.is_nullable, c.column_id
        FROM sys.tables AS t
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.columns AS c ON c.object_id = t.object_id
        JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
        WHERE s.name = ?
          AND t.name IN (?, ?, ?)
          AND c.name IN (?, ?, ?, ?, ?, ?, ?)
        ORDER BY t.name, c.column_id
        """,
        (
            "retail",
            "fact_inventory_daily",
            "dim_store",
            "dim_item",
            "item_key",
            "store_key",
            "item_id",
            "store_id",
            "category_id",
            "forecast_7d",
            "ads",
        ),
    )
    columns = []
    for row in cursor.fetchall():
        values = dict(zip([description[0] for description in cursor.description], row))
        columns.append(values)
    actual = {
        (row["table_name"], row["column_name"]): row for row in columns
    }
    for key, (data_type, max_length, nullable) in SOURCE_TYPE_CONTRACT.items():
        _require(key in actual, f"Live source column is missing: retail.{key[0]}.{key[1]}", LoadError)
        row = actual[key]
        _require(
            row["data_type"] == data_type
            and int(row["max_length"] or 0) == max_length
            and bool(row["is_nullable"]) == nullable,
            f"Live source type drift for retail.{key[0]}.{key[1]}: {row}",
            LoadError,
        )
    return columns


def inspect_target(cursor: Any) -> TargetInspection:
    schema_row = _fetch_one(cursor, "SELECT CASE WHEN SCHEMA_ID(?) IS NULL THEN 0 ELSE 1 END AS schema_exists", (TABLE_SCHEMA,))
    object_row = _fetch_one(
        cursor,
        "SELECT CASE WHEN OBJECT_ID(?, ?) IS NULL THEN 0 ELSE 1 END AS table_exists",
        (FULL_TABLE_NAME, "U"),
    )
    schema_exists = bool(schema_row["schema_exists"])
    exists = bool(object_row["table_exists"])
    if not exists:
        return TargetInspection(schema_exists=schema_exists, exists=False)
    cursor.execute(
        """
        SELECT c.name, ty.name AS data_type, c.max_length, c.precision,
               c.scale, c.is_nullable, c.column_id
        FROM sys.tables AS t
        JOIN sys.schemas AS s ON s.schema_id = t.schema_id
        JOIN sys.columns AS c ON c.object_id = t.object_id
        JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
        WHERE s.name = ? AND t.name = ?
        ORDER BY c.column_id
        """,
        (TABLE_SCHEMA, TABLE_NAME),
    )
    columns = tuple(
        dict(zip([description[0] for description in cursor.description], row))
        for row in cursor.fetchall()
    )
    cursor.execute(
        """
        SELECT c.name, ic.key_ordinal
        FROM sys.indexes AS i
        JOIN sys.index_columns AS ic
          ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns AS c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = OBJECT_ID(?) AND i.is_primary_key = 1
        ORDER BY ic.key_ordinal
        """,
        (FULL_TABLE_NAME,),
    )
    primary_key = tuple(row[0] for row in cursor.fetchall())
    return TargetInspection(schema_exists, True, columns, primary_key)


def validate_target_schema(inspection: TargetInspection) -> None:
    _require(inspection.exists, "Target table does not exist", TableConflictError)
    actual_columns = tuple(column["name"] for column in inspection.columns)
    expected_columns = tuple(column[0] for column in TARGET_COLUMN_CONTRACT)
    _require(
        actual_columns == expected_columns,
        f"Target columns differ; expected {expected_columns}, found {actual_columns}",
        TableConflictError,
    )
    for actual, expected in zip(inspection.columns, TARGET_COLUMN_CONTRACT):
        name, data_type, max_length, precision, scale, nullable = expected
        _require(
            actual["name"] == name
            and actual["data_type"] == data_type
            and (data_type != "nvarchar" or int(actual["max_length"] or 0) == max_length)
            and (data_type != "decimal" or int(actual["precision"] or 0) == precision)
            and (data_type != "decimal" or int(actual["scale"] or 0) == scale)
            and bool(actual["is_nullable"]) == nullable,
            f"Target column definition drift for {name}: {actual}",
            TableConflictError,
        )
    _require(
        inspection.primary_key == ("sku_id", "store_id"),
        f"Target primary key differs: {inspection.primary_key}",
        TableConflictError,
    )


def split_sql_batches(script: str) -> list[str]:
    return [
        batch.strip()
        for batch in re.split(r"^\s*GO\s*(?:--.*)?$", script, flags=re.IGNORECASE | re.MULTILINE)
        if batch.strip()
    ]


def apply_setup_script(cursor: Any, ddl_path: Path = DDL_PATH) -> int:
    _require(ddl_path.is_file(), f"DDL/setup script not found: {ddl_path}")
    batches = split_sql_batches(ddl_path.read_text(encoding="utf-8"))
    for batch in batches:
        cursor.execute(batch)
    return len(batches)


def insert_candidate(cursor: Any, candidate: CandidateArtifact) -> int:
    columns = generator.BUSINESS_COLUMNS
    quoted_columns = ", ".join(f"[{column}]" for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    statement = (
        f"INSERT INTO [{TABLE_SCHEMA}].[{TABLE_NAME}] ({quoted_columns}) "
        f"VALUES ({placeholders});"
    )
    values = [
        tuple(row.business_dict()[column] for column in columns)
        for row in candidate.rows
    ]
    if hasattr(cursor, "fast_executemany"):
        cursor.fast_executemany = True
    inserted = 0
    for batch in _chunked(values, INSERT_BATCH_SIZE):
        cursor.executemany(statement, batch)
        inserted += len(batch)
    return inserted


def _period_invalid_sql() -> tuple[str, str]:
    quantity_columns = (*generator.ACTUAL_COLUMNS, *generator.FORECAST_COLUMNS)
    null_terms = " + ".join(
        f"CASE WHEN [{column}] IS NULL THEN 1 ELSE 0 END"
        for column in quantity_columns
    )
    negative_terms = " + ".join(
        f"CASE WHEN [{column}] < 0 THEN 1 ELSE 0 END"
        for column in quantity_columns
    )
    return null_terms, negative_terms


def classify_existing_copy(row_count: int, fingerprint: str) -> str:
    """Return the only safe action for an already-existing target table."""

    if row_count == generator.EXPECTED_ROW_COUNT and fingerprint == EXPECTED_OUTPUT_FINGERPRINT:
        return "NOOP_ALREADY_LOADED"
    return "CONFLICT"


def reconcile_w1_values(
    loaded: Mapping[tuple[str, str], Decimal | float | int],
    source: Mapping[tuple[str, str], Decimal | float | int],
    tolerance: Decimal = W1_TOLERANCE,
) -> dict[str, Any]:
    """Apply the exact SKU-store W+1 reconciliation rule to in-memory values.

    The live loader performs the same comparison in Azure SQL.  Keeping this
    small pure helper makes the hard-gate rule directly testable without a
    database fixture.
    """

    keys = set(loaded) & set(source)
    differences = {
        key: abs(_as_decimal(loaded[key]) - _as_decimal(source[key]))
        for key in keys
    }
    maximum = max(differences.values(), default=Decimal("0"))
    rows_passed = sum(difference <= tolerance for difference in differences.values())
    return {
        "rows_checked": len(keys),
        "rows_passed": rows_passed,
        "rows_failed": len(keys) - rows_passed,
        "maximum_difference": generator.decimal_text(maximum),
        "key_set_match": set(loaded) == set(source),
        "passed": set(loaded) == set(source)
        and len(keys) == generator.EXPECTED_ROW_COUNT
        and rows_passed == generator.EXPECTED_ROW_COUNT
        and maximum <= tolerance,
    }


def _shape_validation(cursor: Any) -> dict[str, Any]:
    counts = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS row_count,
               COUNT(DISTINCT [sku_id]) AS sku_count,
               COUNT(DISTINCT [store_id]) AS store_count
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
        """,
    )
    key_groups = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS unique_pairs
        FROM (
            SELECT [sku_id], [store_id]
            FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
            GROUP BY [sku_id], [store_id]
        ) AS pairs
        """,
    )
    duplicate_groups = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS duplicate_pairs
        FROM (
            SELECT [sku_id], [store_id]
            FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
            GROUP BY [sku_id], [store_id]
            HAVING COUNT_BIG(*) > 1
        ) AS duplicates
        """,
    )
    store_distribution = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS store_groups,
               MIN(row_count) AS min_rows_per_store,
               MAX(row_count) AS max_rows_per_store,
               SUM(CASE WHEN row_count <> 100 THEN 1 ELSE 0 END) AS invalid_stores
        FROM (
            SELECT [store_id], COUNT_BIG(*) AS row_count
            FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
            GROUP BY [store_id]
        ) AS store_counts
        """,
    )
    null_cat = _fetch_one(
        cursor,
        f"SELECT SUM(CASE WHEN [cat] IS NULL THEN 1 ELSE 0 END) AS null_cat_rows FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]",
    )
    null_terms, negative_terms = _period_invalid_sql()
    period = _fetch_one(
        cursor,
        f"""
        SELECT COALESCE(SUM({null_terms}), 0) AS null_period_cells,
               COALESCE(SUM({negative_terms}), 0) AS negative_period_cells
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
        """,
    )
    result = {
        "row_count": _as_int(counts["row_count"]),
        "sku_count": _as_int(counts["sku_count"]),
        "store_count": _as_int(counts["store_count"]),
        "unique_pairs": _as_int(key_groups["unique_pairs"]),
        "duplicate_pairs": _as_int(duplicate_groups["duplicate_pairs"]),
        "store_groups": _as_int(store_distribution["store_groups"]),
        "min_rows_per_store": _as_int(store_distribution["min_rows_per_store"]),
        "max_rows_per_store": _as_int(store_distribution["max_rows_per_store"]),
        "invalid_stores": _as_int(store_distribution["invalid_stores"]),
        "null_cat_rows": _as_int(null_cat["null_cat_rows"]),
        "null_period_cells": _as_int(period["null_period_cells"]),
        "negative_period_cells": _as_int(period["negative_period_cells"]),
    }
    result["passed"] = (
        result["row_count"] == generator.EXPECTED_ROW_COUNT
        and result["sku_count"] == generator.EXPECTED_SKU_COUNT
        and result["store_count"] == generator.EXPECTED_STORE_COUNT
        and result["unique_pairs"] == generator.EXPECTED_ROW_COUNT
        and result["duplicate_pairs"] == 0
        and result["store_groups"] == generator.EXPECTED_STORE_COUNT
        and result["min_rows_per_store"] == generator.EXPECTED_ROWS_PER_STORE
        and result["max_rows_per_store"] == generator.EXPECTED_ROWS_PER_STORE
        and result["invalid_stores"] == 0
        and result["null_cat_rows"] == 0
        and result["null_period_cells"] == 0
        and result["negative_period_cells"] == 0
    )
    return result


def _canonical_loaded_row(values: Sequence[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for index, value in enumerate(values):
        if index < 3:
            result.append("" if value is None else str(value))
        else:
            result.append("" if value is None else generator.quantity_text(value))
    return tuple(result)


def _fingerprint_canonical_rows(rows: Iterable[Sequence[str]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update("|".join(row).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def sql_fingerprint(cursor: Any, candidate: CandidateArtifact) -> dict[str, Any]:
    columns = ", ".join(f"[{column}]" for column in generator.BUSINESS_COLUMNS)
    cursor.execute(
        f"SELECT {columns} FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] ORDER BY [sku_id], [store_id]"
    )
    loaded_rows = [_canonical_loaded_row(row) for row in cursor.fetchall()]
    loaded_fingerprint = _fingerprint_canonical_rows(loaded_rows)
    approved_rows = [
        tuple(row.business_dict()[column] for column in generator.BUSINESS_COLUMNS)
        for row in candidate.rows
    ]
    differences: list[dict[str, Any]] = []
    for row_index, (approved, loaded) in enumerate(zip(approved_rows, loaded_rows)):
        for column, expected, actual in zip(generator.BUSINESS_COLUMNS, approved, loaded):
            if expected != actual:
                differences.append(
                    {
                        "row_index": row_index,
                        "sku_id": approved[0],
                        "store_id": approved[1],
                        "column": column,
                        "approved": expected,
                        "loaded": actual,
                    }
                )
                if len(differences) >= 10:
                    break
        if len(differences) >= 10:
            break
    return {
        "approved_fingerprint": candidate.fingerprint,
        "loaded_fingerprint": loaded_fingerprint,
        "row_count": len(loaded_rows),
        "passed": loaded_fingerprint == candidate.fingerprint
        and len(loaded_rows) == candidate.row_count,
        "differences": differences,
    }


def w1_reconciliation(cursor: Any) -> dict[str, Any]:
    row = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS rows_checked,
               SUM(CASE WHEN ABS(
                   CAST(t.[forecast_w1] AS DECIMAL(38,12))
                   - CAST(f.[forecast_7d] AS DECIMAL(38,12))
               ) <= CAST(? AS DECIMAL(38,12)) THEN 1 ELSE 0 END) AS rows_passed,
               MAX(ABS(
                   CAST(t.[forecast_w1] AS DECIMAL(38,12))
                   - CAST(f.[forecast_7d] AS DECIMAL(38,12))
               )) AS maximum_difference,
               CAST(SUM(CAST(f.[forecast_7d] AS DECIMAL(38,12))) AS DECIMAL(38,12)) AS source_total,
               CAST(SUM(CAST(t.[forecast_w1] AS DECIMAL(38,12))) AS DECIMAL(38,12)) AS loaded_total
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] AS t
        JOIN retail.[fact_inventory_daily] AS f
          ON f.[item_key] = t.[sku_id]
         AND f.[store_key] = t.[store_id]
         AND f.[cal_date] = ?
         AND f.[import_batch_id] = ?
        """,
        (generator.decimal_text(W1_TOLERANCE), SOURCE_DATE, SOURCE_BATCH),
    )
    rows_checked = _as_int(row["rows_checked"])
    rows_passed = _as_int(row["rows_passed"])
    source_total = _as_decimal(row["source_total"])
    loaded_total = _as_decimal(row["loaded_total"])
    total_difference = abs(loaded_total - source_total)
    samples: list[dict[str, Any]] = []
    sample_sql = f"""
        SELECT t.[sku_id], t.[store_id], t.[forecast_w1], f.[forecast_7d],
               ABS(CAST(t.[forecast_w1] AS DECIMAL(38,12))
                   - CAST(f.[forecast_7d] AS DECIMAL(38,12))) AS difference
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] AS t
        JOIN retail.[fact_inventory_daily] AS f
          ON f.[item_key] = t.[sku_id]
         AND f.[store_key] = t.[store_id]
         AND f.[cal_date] = ?
         AND f.[import_batch_id] = ?
        WHERE (t.[sku_id] = ? AND t.[store_id] = ?)
           OR (t.[sku_id] = ? AND t.[store_id] = ?)
           OR (t.[sku_id] = ? AND t.[store_id] = ?)
           OR (t.[sku_id] = ? AND t.[store_id] = ?)
        ORDER BY t.[sku_id], t.[store_id]
    """
    parameters: list[Any] = [SOURCE_DATE, SOURCE_BATCH]
    for sku_id, store_id in SAMPLE_KEYS:
        parameters.extend((sku_id, store_id))
    cursor.execute(sample_sql, tuple(parameters))
    for item in cursor.fetchall():
        samples.append(
            {
                "sku_id": str(item[0]),
                "store_id": str(item[1]),
                "loaded_forecast_w1": generator.quantity_text(item[2]),
                "source_forecast_7d": generator.decimal_text(item[3]),
                "difference": generator.decimal_text(item[4]),
            }
        )
    result = {
        "rows_checked": rows_checked,
        "rows_passed": rows_passed,
        "rows_failed": rows_checked - rows_passed,
        "maximum_difference": generator.decimal_text(row["maximum_difference"]),
        "source_total": generator.decimal_text(source_total),
        "loaded_total": generator.decimal_text(loaded_total),
        "total_difference": generator.decimal_text(total_difference),
        "tolerance": generator.decimal_text(W1_TOLERANCE),
        "samples": samples,
        "passed": rows_checked == generator.EXPECTED_ROW_COUNT
        and rows_passed == generator.EXPECTED_ROW_COUNT
        and len(samples) == len(SAMPLE_KEYS)
        and _as_decimal(row["maximum_difference"]) <= W1_TOLERANCE,
    }
    return result


def _source_scope_keys(snapshot: generator.SourceSnapshot, label: str) -> set[tuple[str, str]]:
    if label == "ALL":
        return {source.key for source in snapshot.source_rows}
    if label == "GRC":
        return {source.key for source in snapshot.source_rows if source.vertical_id == "GRC"}
    if label == "S001":
        return {source.key for source in snapshot.source_rows if source.store_id == "S001"}
    if label == "GRC-C01":
        return {source.key for source in snapshot.source_rows if source.cat == "GRC-C01"}
    if label == "GRC-001":
        return {source.key for source in snapshot.source_rows if source.sku_id == "GRC-001"}
    if label == "S001 + GRC-C01":
        return {source.key for source in snapshot.source_rows if source.store_id == "S001" and source.cat == "GRC-C01"}
    if label == "S001 + GRC-001":
        return {source.key for source in snapshot.source_rows if source.store_id == "S001" and source.sku_id == "GRC-001"}
    raise ValueError(label)


def _sql_scope_definition(label: str) -> tuple[str, tuple[Any, ...]]:
    if label == "GRC":
        return "JOIN retail.[dim_store] AS s ON s.[store_id] = t.[store_id] WHERE s.[vertical_id] = ?", ("GRC",)
    if label == "S001":
        return "WHERE t.[store_id] = ?", ("S001",)
    if label == "GRC-C01":
        return "WHERE t.[cat] = ?", ("GRC-C01",)
    if label == "GRC-001":
        return "WHERE t.[sku_id] = ?", ("GRC-001",)
    if label == "S001 + GRC-C01":
        return "WHERE t.[store_id] = ? AND t.[cat] = ?", ("S001", "GRC-C01")
    if label == "S001 + GRC-001":
        return "WHERE t.[store_id] = ? AND t.[sku_id] = ?", ("S001", "GRC-001")
    if label == "ALL":
        return "", ()
    raise ValueError(label)


def _expected_scope(candidate: CandidateArtifact, snapshot: generator.SourceSnapshot, label: str) -> dict[str, Any]:
    keys = _source_scope_keys(snapshot, label)
    actual_total, forecast_total = generator.trend_totals(candidate.rows, keys)
    trend = forecast_total / actual_total - Decimal("1")
    return {
        "row_count": len(keys),
        "actual_total": actual_total,
        "forecast_total": forecast_total,
        "trend": trend,
    }


def sql_trend_results(
    cursor: Any,
    candidate: CandidateArtifact,
    snapshot: generator.SourceSnapshot,
) -> dict[str, dict[str, Any]]:
    actual_expr = " + ".join(
        f"CAST(t.[{column}] AS DECIMAL(38,12))" for column in generator.ACTUAL_COLUMNS[-4:]
    )
    forecast_expr = " + ".join(
        f"CAST(t.[{column}] AS DECIMAL(38,12))" for column in generator.FORECAST_COLUMNS[:4]
    )
    results: dict[str, dict[str, Any]] = {}
    labels = ("ALL", "GRC", "S001", "GRC-C01", "GRC-001", "S001 + GRC-C01", "S001 + GRC-001")
    for label in labels:
        scope_sql, parameters = _sql_scope_definition(label)
        row = _fetch_one(
            cursor,
            f"""
            SELECT COUNT_BIG(*) AS row_count,
                   CAST(SUM({actual_expr}) AS DECIMAL(38,12)) AS actual_total,
                   CAST(SUM({forecast_expr}) AS DECIMAL(38,12)) AS forecast_total,
                   CAST(SUM({forecast_expr}) AS DECIMAL(38,12))
                   / NULLIF(CAST(SUM({actual_expr}) AS DECIMAL(38,12)), 0)
                   - 1 AS demand_trend
            FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] AS t
            {scope_sql}
            """,
            parameters,
        )
        expected = _expected_scope(candidate, snapshot, label)
        actual_total = _as_decimal(row["actual_total"])
        forecast_total = _as_decimal(row["forecast_total"])
        loaded_trend = _as_decimal(row["demand_trend"])
        actual_difference = abs(actual_total - expected["actual_total"])
        forecast_difference = abs(forecast_total - expected["forecast_total"])
        trend_difference = abs(loaded_trend - expected["trend"])
        results[label] = {
            "row_count": _as_int(row["row_count"]),
            "actual_total": generator.decimal_text(actual_total),
            "forecast_total": generator.decimal_text(forecast_total),
            "demand_trend": generator.decimal_text(loaded_trend),
            "expected_actual_total": generator.decimal_text(expected["actual_total"]),
            "expected_forecast_total": generator.decimal_text(expected["forecast_total"]),
            "expected_demand_trend": generator.decimal_text(expected["trend"]),
            "actual_total_difference": generator.decimal_text(actual_difference),
            "forecast_total_difference": generator.decimal_text(forecast_difference),
            "trend_difference": generator.decimal_text(trend_difference),
            "passed": _as_int(row["row_count"]) == expected["row_count"]
            and actual_difference <= TREND_TOLERANCE
            and forecast_difference <= TREND_TOLERANCE
            and trend_difference <= TREND_TOLERANCE,
        }
    return results


def horizon_validation(cursor: Any, candidate: CandidateArtifact) -> dict[str, Any]:
    columns = generator.FORECAST_COLUMNS
    select = ", ".join(
        f"CAST(SUM(CAST([{column}] AS DECIMAL(38,12))) AS DECIMAL(38,12)) AS [{column}]"
        for column in columns
    )
    row = _fetch_one(cursor, f"SELECT {select} FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]")
    totals_decimal = {column: _as_decimal(row[column]) for column in columns}
    totals = {column: generator.decimal_text(value) for column, value in totals_decimal.items()}
    expected_decimal = {
        column: sum((item.forecasts[index] for item in candidate.rows), Decimal("0"))
        for index, column in enumerate(columns)
    }
    differences = {
        column: generator.decimal_text(abs(totals_decimal[column] - expected_decimal[column]))
        for column in columns
    }
    horizons = {
        "4w": list(columns[:4]),
        "8w": list(columns[:8]),
        "12w": list(columns[:12]),
        "16w": list(columns[:16]),
    }
    return {
        "forecast_totals_all_rows": totals,
        "expected_forecast_totals_all_rows": {
            column: generator.decimal_text(value)
            for column, value in expected_decimal.items()
        },
        "differences": differences,
        "horizons": horizons,
        "passed": all(all(column in totals for column in selected) for selected in horizons.values())
        and all(Decimal(difference) <= TREND_TOLERANCE for difference in differences.values()),
    }


def validate_sql_copy(
    cursor: Any,
    candidate: CandidateArtifact,
    snapshot: generator.SourceSnapshot,
) -> dict[str, Any]:
    shape = _shape_validation(cursor)
    fingerprint = sql_fingerprint(cursor, candidate)
    reconciliation = w1_reconciliation(cursor)
    trends = sql_trend_results(cursor, candidate, snapshot)
    horizon = horizon_validation(cursor, candidate)
    passed = (
        shape["passed"]
        and fingerprint["passed"]
        and reconciliation["passed"]
        and all(item["passed"] for item in trends.values())
        and horizon["passed"]
    )
    return {
        "passed": passed,
        "shape": shape,
        "fingerprint": fingerprint,
        "w1_reconciliation": reconciliation,
        "trend_results": trends,
        "horizon": horizon,
    }


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _pct(value: str | Decimal | float) -> str:
    return f"{float(value):.2%}"


def render_load_report(result: Mapping[str, Any], test_result: str) -> str:
    candidate = result["candidate"]
    snapshot = result["snapshot"]
    validation = result["validation"]
    shape = validation["shape"]
    fingerprint = validation["fingerprint"]
    w1 = validation["w1_reconciliation"]
    trends = validation["trend_results"]
    horizon = validation["horizon"]
    action = result["load_action"]
    verdict = "READY FOR BACKEND INTEGRATION WITH CAVEATS"
    lines = [
        "# Demand Store SKU 32W SQL Load Report",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Table name | `{FULL_TABLE_NAME}` |",
        f"| Source revision | `{snapshot.source_revision}` |",
        f"| Source batch | `{snapshot.batch_id}` |",
        f"| CSV path | `{_relative_path(candidate.csv_path)}` |",
        f"| Expected fingerprint | `{EXPECTED_OUTPUT_FINGERPRINT}` |",
        f"| Loaded fingerprint | `{fingerprint['loaded_fingerprint']}` |",
        f"| Rows loaded/in table | `{shape['row_count']}` |",
        f"| Columns | `{len(generator.BUSINESS_COLUMNS)}` |",
        f"| SKUs | `{shape['sku_count']}` |",
        f"| Stores | `{shape['store_count']}` |",
        f"| Overall verdict | **{verdict}** |",
        "",
        "## 1. Executive Summary",
        "",
        f"The approved `{GENERATION_NAME}` CSV was validated and loaded into `{FULL_TABLE_NAME}` at one row per SKU × Store. The loader action for the final invocation was `{action}`; it never regenerates values and has no replace/truncate mode. All post-load hard gates passed, including exact SQL fingerprint and SKU-store Forecast W+1 reconciliation. The previous 5,120-row store-week candidate was not loaded.",
        "",
        "Only the new `synthetic` POC layer was eligible for writes. Existing `retail` source tables and application runtime code were not modified.",
        "",
        "## 2. Source Preflight",
        "",
        f"- Database: `{result['database_name']}`.",
        f"- Source: v8.5, batch `{snapshot.batch_id}`, `{snapshot.import_status}`, agent `{snapshot.agent_name}`, SHA `{snapshot.source_sha256}`.",
        f"- Snapshot: `{snapshot.source_snapshot_date.isoformat()}`; fact rows `{snapshot.fact_rows}`; stores `{snapshot.fact_distinct_stores}`; SKUs `{snapshot.fact_distinct_skus}`.",
        f"- Per-store source coverage: 100 unique SKU rows for every 160 store; duplicate source keys `{snapshot.duplicate_source_keys}`.",
        f"- Null/negative ADS `{snapshot.bad_ads}`; null/negative Forecast 7d `{snapshot.bad_forecast_7d}`; rows outside batch 23 `{snapshot.rows_not_batch}`.",
        f"- Category join: `{snapshot.category_join_rows}` rows, missing items `{snapshot.missing_category_items}`, null categories `{snapshot.null_join_categories}`, missing stores `{snapshot.missing_join_stores}`.",
        f"- Superseded `{SUPERSEDED_TABLE_NAME}` existed before load: `{result['superseded_table_exists']}`; it was not queried for data, created, modified, or loaded.",
        "",
        "The source type guard also matched the live definitions used by the DDL: `dim_item.item_id`/`fact.item_key` NVARCHAR(30), `dim_store.store_id`/`fact.store_key` NVARCHAR(20), and `dim_item.category_id` NVARCHAR(30).",
        "",
        "## 3. Candidate Artifact Verification",
        "",
        f"The loader read only `{_relative_path(candidate.csv_path)}` and its manifest; it did not use the XLSX as a SQL source and did not run the generator.",
        f"- Rows `{candidate.row_count}`; columns `{len(generator.BUSINESS_COLUMNS)}`; SKUs `{len({row.sku_id for row in candidate.rows})}`; stores `{len({row.store_id for row in candidate.rows})}`; unique pairs `{len({row.key for row in candidate.rows})}`.",
        f"- Exact column order: `{', '.join(generator.BUSINESS_COLUMNS)}`.",
        f"- All 32 quantity columns were populated, finite, non-negative, and canonical six-decimal text before SQL changes.",
        f"- Recomputed candidate fingerprint: `{candidate.fingerprint}`; manifest fingerprint matched the approved value.",
        "",
        "## 4. SQL Schema/Table Created",
        "",
        f"Setup script: `{_relative_path(Path(result['ddl_path']))}`.",
        f"Synthetic schema existed before load: `{result['synthetic_schema_existed_before']}`. Target table existed before load: `{result['target_table_existed_before']}`. Table created by the first load path: `{result['table_created']}`.",
        "",
        "The table contains exactly the 35 approved business columns, all identifier/quantity columns are `NOT NULL`, quantities are `DECIMAL(20,6)`, and the only key is `PRIMARY KEY (sku_id, store_id)`. The only additional schema rule is a non-negative quantity CHECK constraint.",
        "",
        "## 5. Load Method",
        "",
        f"The loader used the repository's `mssql_python` Azure SQL connection, parameterized `executemany` inserts in batches of `{INSERT_BATCH_SIZE}`, and one transaction. It committed only after all shape, W+1, fingerprint, Trend, horizon, and filter validations passed. Rows inserted in this invocation: `{result['rows_inserted_this_run']}`.",
        "",
        "## 6. Row/Column Validation",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Row count = 16,000 | {'PASS' if shape['row_count'] == 16000 else 'FAIL'} (`{shape['row_count']}`) |",
        f"| Distinct SKUs = 800 | {'PASS' if shape['sku_count'] == 800 else 'FAIL'} (`{shape['sku_count']}`) |",
        f"| Distinct stores = 160 | {'PASS' if shape['store_count'] == 160 else 'FAIL'} (`{shape['store_count']}`) |",
        f"| Unique SKU-store pairs = 16,000 | {'PASS' if shape['unique_pairs'] == 16000 else 'FAIL'} (`{shape['unique_pairs']}`) |",
        f"| Duplicate pairs = 0 | {'PASS' if shape['duplicate_pairs'] == 0 else 'FAIL'} (`{shape['duplicate_pairs']}`) |",
        f"| Rows per store = 100 | {'PASS' if shape['min_rows_per_store'] == 100 and shape['max_rows_per_store'] == 100 else 'FAIL'} (`{shape['min_rows_per_store']}..{shape['max_rows_per_store']}`) |",
        f"| Null period cells = 0 | {'PASS' if shape['null_period_cells'] == 0 else 'FAIL'} (`{shape['null_period_cells']}`) |",
        f"| Negative period cells = 0 | {'PASS' if shape['negative_period_cells'] == 0 else 'FAIL'} (`{shape['negative_period_cells']}`) |",
        "",
        "## 7. SKU/Store/Category Validation",
        "",
        f"The SQL copy retains the approved SKU-store key set and category values through the canonical fingerprint. `cat` NULL rows: `{shape['null_cat_rows']}`. Store, category, SKU, and combined filter scopes are validated below from the loaded SQL table.",
        "",
        "## 8. W+1 Source Reconciliation",
        "",
        f"The SQL copy was joined to `retail.fact_inventory_daily` on `sku_id = item_key` and `store_id = store_key` for batch 23 and 2026-07-01. Tolerance was `{w1['tolerance']}`.",
        "",
        f"- Rows checked: `{w1['rows_checked']}`; passed: `{w1['rows_passed']}`; failed: `{w1['rows_failed']}`.",
        f"- Maximum difference: `{w1['maximum_difference']}`.",
        f"- Source W+1 total: `{w1['source_total']}`; loaded W+1 total: `{w1['loaded_total']}`; total difference: `{w1['total_difference']}`.",
        "",
        "| SKU | Store | Loaded forecast_w1 | Source Forecast 7d | Difference |",
        "|---|---|---:|---:|---:|",
        *[
            f"| {sample['sku_id']} | {sample['store_id']} | {sample['loaded_forecast_w1']} | {sample['source_forecast_7d']} | {sample['difference']} |"
            for sample in w1["samples"]
        ],
        "",
        "## 9. SQL Fingerprint Reconciliation",
        "",
        f"All 35 SQL columns were read back ordered by `sku_id, store_id`, canonicalized with the generator's six-decimal formatting, and hashed. Expected `{fingerprint['approved_fingerprint']}`; loaded `{fingerprint['loaded_fingerprint']}`; result: `{'PASS' if fingerprint['passed'] else 'FAIL'}`.",
        "",
        ("No differing rows or columns were found." if fingerprint["passed"] else f"First differences: `{fingerprint['differences']}`."),
        "",
        "## 10. Demand Trend SQL Results",
        "",
        "The SQL validation aggregates quantities first, then divides:",
        "",
        "```text",
        "SUM(forecast_w1 + forecast_w2 + forecast_w3 + forecast_w4)",
        "/ SUM(actual_w4 + actual_w3 + actual_w2 + actual_w1) - 1",
        "```",
        "",
        "| Scope | SQL rows | SQL actual total | SQL forecast total | SQL Trend | Expected Trend | Result |",
        "|---|---:|---:|---:|---:|---:|---|",
        *[
            f"| {label} | {item['row_count']} | {item['actual_total']} | {item['forecast_total']} | {_pct(item['demand_trend'])} | {_pct(item['expected_demand_trend'])} | {'PASS' if item['passed'] else 'FAIL'} |"
            for label, item in trends.items()
        ],
        "",
        "The SQL results are compared to the approved CSV-derived totals, not to the superseded workbook `-6.5%` constant.",
        "",
        "## 11. Horizon Data Validation",
        "",
        "The loaded wide table exposes the full forecast sequence for all rows. The following prefixes were verified from aggregate SQL values:",
        "",
        *[
            f"- `{label}`: `{' → '.join(columns)}`."
            for label, columns in horizon["horizons"].items()
        ],
        "",
        f"ALL-row aggregate forecast columns W+1...W+16 were non-null and readable; horizon validation: `{'PASS' if horizon['passed'] else 'FAIL'}`.",
        "",
        "## 12. Filter-Scope Validation",
        "",
        "Loaded SQL supports the required subsets without store-level collapse: `S001`, `GRC-C01`, `GRC-001`, `S001 + GRC-C01`, and `S001 + GRC-001`. Their row counts and four-week aggregate totals are shown in Section 10; all passed against the approved candidate.",
        "",
        "## 13. Tests",
        "",
        test_result,
        "",
        "The loader also performed live SQL shape, null/negative, per-store, source W+1, fingerprint, Trend, horizon, and filter validation during the load transaction.",
        "",
        "## 14. Idempotence / Re-run Behavior",
        "",
        f"The loader's final invocation action was `{action}`. If `{FULL_TABLE_NAME}` already contains the exact approved 16,000-row fingerprint, the loader returns a no-op success and performs no INSERT, overwrite, truncate, or replace. A partial, differing, or schema-conflicting existing table raises `TableConflictError` and is left untouched. There is no automatic `--replace` option.",
        "",
        "## 15. Rollback / Removal Instructions",
        "",
        "This is a standalone temporary additive table. After confirming no consumer depends on it, remove only the POC table with:",
        "",
        "```sql",
        "DROP TABLE synthetic.demand_store_sku_32w;",
        "```",
        "",
        "Optionally remove the schema only if no other object uses it:",
        "",
        "```sql",
        "DROP SCHEMA synthetic;",
        "```",
        "",
        "These steps do not affect `retail.fact_inventory_daily`, `retail.dim_store`, `retail.dim_item`, or any other original source table. Rollback was not executed.",
        "",
        "## 16. Remaining Caveats",
        "",
        "- Historical actual columns remain synthetic and have no genuine sales ground truth.",
        "- Forecast W+2 through W+16 remain synthetic; Forecast W+1 is the existing source Forecast 7d quantized to six decimals and is not a target-dated 16-week forecast.",
        "- The date-free wide layout intentionally carries no row-level period dates or provenance columns; the manifest/report retain provenance.",
        "- This is a temporary POC using current sales-unit aggregation semantics; no returns, cancellations, pack-factor normalization, or stockout-censored demand policy is claimed.",
        "",
        "## 17. Backend Integration Handoff",
        "",
        f"The next task may rely on `{FULL_TABLE_NAME}` containing one row per SKU × Store with `sku_id`, `store_id`, `cat`, `actual_w16...actual_w1`, and `forecast_w1...forecast_w16`. Backend integration should apply legal entity/store/category/SKU filters, aggregate matching wide columns, calculate Demand Trend from W-4...W-1 versus W+1...W+4, and expose up to W+16 according to Horizon. This task intentionally did not implement any backend/frontend wiring or change runtime behavior.",
        "",
    ]
    return "\n".join(lines)


def write_report(result: Mapping[str, Any], test_result: str, path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_load_report(result, test_result), encoding="utf-8")


def run_load(
    *,
    csv_path: Path = CSV_PATH,
    manifest_path: Path = MANIFEST_PATH,
    ddl_path: Path = DDL_PATH,
    report_path: Path = REPORT_PATH,
    test_result: str = "Focused SQL-load tests: run separately.",
    write_report_file: bool = True,
) -> dict[str, Any]:
    candidate = load_candidate_artifact(csv_path, manifest_path)

    # This is the mandatory read-only preflight.  It loads source rows into
    # memory for reconciliation but never generates or writes any values.
    snapshot = generator.load_source_snapshot()
    _require(
        snapshot.source_revision == generator.SOURCE_REVISION
        and snapshot.batch_id == SOURCE_BATCH
        and snapshot.source_snapshot_date == SOURCE_DATE,
        "Live source drifted from the approved v8.5/batch-23 contract",
    )

    connection = open_connection()
    table_created = False
    rows_inserted = 0
    target_before: TargetInspection | None = None
    setup_batches = 0
    try:
        cursor = connection.cursor()
        database_row = _fetch_one(cursor, "SELECT DB_NAME() AS database_name")
        database_name = str(database_row["database_name"])
        source_types = source_type_contract(cursor)
        target_before = inspect_target(cursor)
        superseded_row = _fetch_one(
            cursor,
            "SELECT CASE WHEN OBJECT_ID(?, ?) IS NULL THEN 0 ELSE 1 END AS exists_flag",
            (SUPERSEDED_TABLE_NAME, "U"),
        )
        superseded_exists = bool(superseded_row["exists_flag"])

        if target_before.exists:
            validate_target_schema(target_before)
            existing_shape = _shape_validation(cursor)
            existing_fingerprint = sql_fingerprint(cursor, candidate)
            load_action = classify_existing_copy(
                existing_shape["row_count"],
                existing_fingerprint["loaded_fingerprint"],
            )
            if load_action != "NOOP_ALREADY_LOADED":
                raise TableConflictError(
                    f"Existing {FULL_TABLE_NAME} differs from the approved dataset: "
                    f"fingerprint={existing_fingerprint['loaded_fingerprint']}, "
                    f"shape_passed={existing_shape['passed']}"
                )
            validation = validate_sql_copy(cursor, candidate, snapshot)
            if not validation["passed"]:
                raise TableConflictError(
                    f"Existing {FULL_TABLE_NAME} differs from the approved dataset: "
                    f"fingerprint={validation['fingerprint']['loaded_fingerprint']}, "
                    f"shape_passed={validation['shape']['passed']}"
                )
        else:
            setup_batches = apply_setup_script(cursor, ddl_path)
            target_after = inspect_target(cursor)
            validate_target_schema(target_after)
            rows_inserted = insert_candidate(cursor, candidate)
            validation = validate_sql_copy(cursor, candidate, snapshot)
            if not validation["passed"]:
                raise LoadError("Post-insert validation failed; transaction will be rolled back")
            connection.commit()
            table_created = True
            load_action = "CREATED_AND_LOADED"

        result = {
            "database_name": database_name,
            "candidate": candidate,
            "snapshot": snapshot,
            "source_types": source_types,
            "ddl_path": ddl_path,
            "setup_batches": setup_batches,
            "synthetic_schema_existed_before": target_before.schema_exists,
            "target_table_existed_before": target_before.exists,
            "superseded_table_exists": superseded_exists,
            "table_created": table_created,
            "rows_inserted_this_run": rows_inserted,
            "load_action": load_action,
            "validation": validation,
            "report_path": report_path,
        }
    except Exception:
        if target_before is not None and not target_before.exists:
            connection.rollback()
        raise
    finally:
        connection.close()

    # Re-open after the first commit so the report is based on the committed
    # copy, not just the transaction-local view.
    if table_created:
        final_connection = open_connection()
        try:
            final_cursor = final_connection.cursor()
            final_inspection = inspect_target(final_cursor)
            validate_target_schema(final_inspection)
            result["validation_after_commit"] = validate_sql_copy(
                final_cursor, candidate, snapshot
            )
            _require(
                result["validation_after_commit"]["passed"],
                "Committed SQL copy failed the final read-back validation",
            )
        finally:
            final_connection.close()
    if write_report_file:
        write_report(result, test_result, report_path)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--ddl", type=Path, default=DDL_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--test-result", default="Focused SQL-load tests: run separately.")
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Validate/load but do not write the SQL load report.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_load(
            csv_path=args.csv,
            manifest_path=args.manifest,
            ddl_path=args.ddl,
            report_path=args.report,
            test_result=args.test_result,
            write_report_file=not args.no_report,
        )
    except CandidateError as exc:
        print(f"CANDIDATE VALIDATION FAILED: {exc}", file=sys.stderr)
        return 2
    except TableConflictError as exc:
        print(f"EXISTING TABLE CONFLICT: {exc}", file=sys.stderr)
        return 3
    except LoadError as exc:
        print(f"SQL LOAD FAILED: {exc}", file=sys.stderr)
        return 4
    print(
        json.dumps(
            {
                "database_name": result["database_name"],
                "table": FULL_TABLE_NAME,
                "load_action": result["load_action"],
                "rows_inserted_this_run": result["rows_inserted_this_run"],
                "row_count": result["validation"]["shape"]["row_count"],
                "loaded_fingerprint": result["validation"]["fingerprint"]["loaded_fingerprint"],
                "w1_reconciliation": result["validation"]["w1_reconciliation"],
                "trend": {
                    label: item["demand_trend"]
                    for label, item in result["validation"]["trend_results"].items()
                },
                "report_path": str(result["report_path"]),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
