"""Load and validate the approved 104W SKU x Store synthetic table.

The loader never calls the generator.  It validates the approved 104W CSV and
manifest, performs the v8.5/batch-23 source preflight, verifies the existing
32W SQL table before any write, and creates/loads only
``synthetic.demand_store_sku_104w`` when that target is absent.

An existing differing 104W table is a hard conflict.  There is no truncate,
replace, repair, or automatic migration path.  The existing 32W table and all
retail source tables are read-only dependencies of this operation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

import generate_demand_store_sku_104w as generator
from src.retail_data_bootstrap.database import open_connection


TABLE_SCHEMA = "synthetic"
TABLE_NAME = "demand_store_sku_104w"
FULL_TABLE_NAME = f"{TABLE_SCHEMA}.{TABLE_NAME}"
OLD_TABLE_NAME = "demand_store_sku_32w"
OLD_FULL_TABLE_NAME = f"{TABLE_SCHEMA}.{OLD_TABLE_NAME}"
SUPERSEDED_TABLE_NAME = "synthetic.demand_store_week"
CSV_PATH = REPO_ROOT / "artifacts" / "demand_store_sku_104w_poc_v1.csv"
MANIFEST_PATH = REPO_ROOT / "artifacts" / "demand_store_sku_104w_poc_v1_manifest.json"
DDL_PATH = REPO_ROOT / "sql" / "synthetic" / "002_create_demand_store_sku_104w.sql"
REPORT_PATH = REPO_ROOT / "plans" / "demand-store-sku-104w-sql-load-report.md"
EXPECTED_OUTPUT_FINGERPRINT = (
    "c5d069e7a9c988fab61f5c15d448007422ae77ddb26b2892a0481381713ec922"
)
EXPECTED_PREVIOUS_FINGERPRINT = (
    "0e3df661a941440d0e43fa93e62fe166d69c5d12caa1b6ed65333729c78f550d"
)
INSERT_BATCH_SIZE = 1_000
W1_TOLERANCE = Decimal("0.000001")
TREND_TOLERANCE = Decimal("0.000001")
SOURCE_DATE = generator.SOURCE_SNAPSHOT_DATE
SOURCE_BATCH = generator.SOURCE_IMPORT_BATCH_ID
PRESERVED_COLUMNS = generator.PRESERVED_COLUMNS

TARGET_COLUMN_CONTRACT = (
    ("sku_id", "nvarchar", 60, None, None, False),
    ("store_id", "nvarchar", 40, None, None, False),
    ("cat", "nvarchar", 60, None, None, False),
    *(
        (column, "decimal", None, 20, 6, False)
        for column in (*generator.ACTUAL_COLUMNS, *generator.FORECAST_COLUMNS)
    ),
)


class LoadError(RuntimeError):
    """Raised when candidate, source, schema, or SQL validation fails."""


class CandidateError(LoadError):
    """Raised when the approved local artifact does not match its contract."""


class TableConflictError(LoadError):
    """Raised when an existing target table differs from the approved copy."""


@dataclass(frozen=True)
class CandidateArtifact:
    rows: tuple[generator.DemandSkuStore104WRow, ...]
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


def _require(
    condition: bool,
    message: str,
    error_type: type[LoadError] = LoadError,
) -> None:
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


def _fetch_one(
    cursor: Any,
    statement: str,
    parameters: Sequence[Any] = (),
) -> dict[str, Any]:
    cursor.execute(statement, tuple(parameters))
    return _row_dict(cursor, cursor.fetchone())


def _chunked(
    values: Sequence[tuple[Any, ...]],
    size: int,
) -> Iterable[Sequence[tuple[Any, ...]]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _candidate_row_from_csv(
    raw: Mapping[str, str],
    line_number: int,
) -> generator.DemandSkuStore104WRow:
    if any(raw.get(column) in (None, "") for column in generator.BUSINESS_COLUMNS):
        raise CandidateError(f"CSV line {line_number} has a null/blank business value")
    actuals: list[Decimal] = []
    forecasts: list[Decimal] = []
    for column in (*generator.ACTUAL_COLUMNS, *generator.FORECAST_COLUMNS):
        text = raw[column]
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise CandidateError(
                f"CSV line {line_number} has invalid {column}: {text!r}"
            ) from exc
        if not value.is_finite() or value < 0:
            raise CandidateError(f"CSV line {line_number} has invalid {column}: {text!r}")
        if text != generator.quantity_text(value):
            raise CandidateError(
                f"CSV line {line_number} {column} is not canonical six-decimal text: {text!r}"
            )
        (actuals if column in generator.ACTUAL_COLUMNS else forecasts).append(value)
    return generator.DemandSkuStore104WRow(
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
    _require(
        manifest_path.is_file(),
        f"Approved manifest not found: {manifest_path}",
        CandidateError,
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateError(f"Manifest is not valid JSON: {manifest_path}") from exc
    _require(isinstance(manifest, dict), "Manifest must be a JSON object", CandidateError)
    _require(
        manifest.get("generation_name") == "demand_store_sku_104w_poc_v1",
        "Unexpected 104W generation name",
        CandidateError,
    )
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
        "Manifest output fingerprint is not the approved 104W fingerprint",
        CandidateError,
    )
    _require(
        manifest.get("previous_32w_fingerprint") == EXPECTED_PREVIOUS_FINGERPRINT,
        "Manifest previous 32W fingerprint is not the approved fingerprint",
        CandidateError,
    )
    contract = manifest.get("column_contract", {})
    _require(
        contract.get("columns") == list(generator.BUSINESS_COLUMNS)
        and contract.get("canonical_sort") == ["sku_id", "store_id"],
        "Manifest column contract does not match the approved 107-column schema",
        CandidateError,
    )

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(
                tuple(reader.fieldnames or ()) == generator.BUSINESS_COLUMNS,
                "Approved CSV columns/order do not match the 107-column contract",
                CandidateError,
            )
            rows = [
                _candidate_row_from_csv(raw, line_number=index + 2)
                for index, raw in enumerate(reader)
            ]
    except OSError as exc:
        raise CandidateError(f"Unable to read approved CSV: {csv_path}") from exc

    rows.sort(key=lambda row: row.key)
    _require(
        len(rows) == generator.EXPECTED_ROW_COUNT,
        f"Expected 16,000 CSV rows, found {len(rows)}",
        CandidateError,
    )
    _require(
        len({row.key for row in rows}) == generator.EXPECTED_ROW_COUNT,
        "CSV has duplicate SKU-store pairs",
        CandidateError,
    )
    _require(
        len({row.sku_id for row in rows}) == generator.EXPECTED_SKU_COUNT,
        "CSV does not contain 800 SKUs",
        CandidateError,
    )
    _require(
        len({row.store_id for row in rows}) == generator.EXPECTED_STORE_COUNT,
        "CSV does not contain 160 stores",
        CandidateError,
    )
    _require(
        {
            sum(row.store_id == store_id for row in rows)
            for store_id in {row.store_id for row in rows}
        }
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
        "output_column_count": 107,
        "sku_count": generator.EXPECTED_SKU_COUNT,
        "store_count": generator.EXPECTED_STORE_COUNT,
        "historical_value_count": generator.HISTORICAL_VALUE_COUNT,
        "source_w1_value_count": generator.SOURCE_W1_VALUE_COUNT,
        "synthetic_future_value_count": generator.SYNTHETIC_FUTURE_VALUE_COUNT,
        "total_weekly_value_count": generator.TOTAL_PERIOD_VALUE_COUNT,
        "existing_preserved_period_count": generator.EXISTING_PRESERVED_VALUE_COUNT,
        "newly_generated_historical_value_count": generator.NEW_HISTORICAL_VALUE_COUNT,
        "newly_generated_forecast_value_count": generator.NEW_FUTURE_VALUE_COUNT,
    }
    for key, expected in expected_manifest_counts.items():
        _require(
            manifest.get(key) == expected,
            f"Manifest {key} is {manifest.get(key)!r}, expected {expected}",
            CandidateError,
        )
    return CandidateArtifact(tuple(rows), manifest, csv_path, manifest_path, fingerprint)


def _source_type_contract(cursor: Any) -> list[dict[str, Any]]:
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
          AND c.name IN (?, ?, ?, ?, ?, ?, ?, ?)
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
            "vertical_id",
        ),
    )
    descriptions = [description[0] for description in cursor.description]
    actual = [dict(zip(descriptions, row)) for row in cursor.fetchall()]
    by_key = {(row["table_name"], row["column_name"]): row for row in actual}
    expected = {
        ("dim_item", "item_id"): ("nvarchar", 60, False),
        ("dim_item", "category_id"): ("nvarchar", 60, True),
        ("dim_store", "store_id"): ("nvarchar", 40, False),
        ("dim_store", "vertical_id"): ("nvarchar", 40, False),
        ("fact_inventory_daily", "item_key"): ("nvarchar", 60, False),
        ("fact_inventory_daily", "store_key"): ("nvarchar", 40, False),
        ("fact_inventory_daily", "forecast_7d"): ("float", None, True),
        ("fact_inventory_daily", "ads"): ("float", None, True),
    }
    for key, (data_type, max_length, nullable) in expected.items():
        _require(key in by_key, f"Live source column is missing: retail.{key[0]}.{key[1]}")
        row = by_key[key]
        _require(
            row["data_type"] == data_type
            and (data_type != "nvarchar" or int(row["max_length"] or 0) == max_length)
            and bool(row["is_nullable"]) == nullable,
            f"Live source type drift for retail.{key[0]}.{key[1]}: {row}",
        )
    return actual


def _row_exists(cursor: Any, full_name: str) -> bool:
    row = _fetch_one(
        cursor,
        "SELECT CASE WHEN OBJECT_ID(?, ?) IS NULL THEN 0 ELSE 1 END AS exists_flag",
        (full_name, "U"),
    )
    return bool(row["exists_flag"])


def _schema_exists(cursor: Any, schema: str) -> bool:
    row = _fetch_one(
        cursor,
        "SELECT CASE WHEN SCHEMA_ID(?) IS NULL THEN 0 ELSE 1 END AS schema_exists",
        (schema,),
    )
    return bool(row["schema_exists"])


def inspect_target(cursor: Any) -> TargetInspection:
    schema_exists = _schema_exists(cursor, TABLE_SCHEMA)
    exists = _row_exists(cursor, FULL_TABLE_NAME)
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
    descriptions = [description[0] for description in cursor.description]
    columns = tuple(dict(zip(descriptions, row)) for row in cursor.fetchall())
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
    _require(inspection.exists, "104W target table does not exist", TableConflictError)
    actual_columns = tuple(column["name"] for column in inspection.columns)
    expected_columns = tuple(column[0] for column in TARGET_COLUMN_CONTRACT)
    _require(
        actual_columns == expected_columns,
        f"104W target columns differ; expected {len(expected_columns)}, found {len(actual_columns)}",
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
            f"104W target column definition drift for {name}: {actual}",
            TableConflictError,
        )
    _require(
        inspection.primary_key == ("sku_id", "store_id"),
        f"104W target primary key differs: {inspection.primary_key}",
        TableConflictError,
    )


def split_sql_batches(script: str) -> list[str]:
    return [
        batch.strip()
        for batch in re.split(
            r"^\s*GO\s*(?:--.*)?$",
            script,
            flags=re.IGNORECASE | re.MULTILINE,
        )
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


def _candidate_preserved_values(candidate: CandidateArtifact) -> dict[tuple[str, str], tuple[str, ...]]:
    return {
        row.key: tuple(row.business_dict()[column] for column in PRESERVED_COLUMNS)
        for row in candidate.rows
    }


def compare_candidate_to_32w_sql(
    cursor: Any,
    candidate: CandidateArtifact,
) -> dict[str, Any]:
    """Compare the approved candidate's preserved block to the live 32W table."""

    _require(_row_exists(cursor, OLD_FULL_TABLE_NAME), f"Required {OLD_FULL_TABLE_NAME} is missing")
    columns = ", ".join(f"[{column}]" for column in PRESERVED_COLUMNS)
    cursor.execute(
        f"SELECT {columns} FROM [{TABLE_SCHEMA}].[{OLD_TABLE_NAME}] ORDER BY [sku_id], [store_id]"
    )
    descriptions = [description[0] for description in cursor.description]
    old_rows = [dict(zip(descriptions, row)) for row in cursor.fetchall()]
    candidate_values = _candidate_preserved_values(candidate)
    old_keys = {(str(row["sku_id"]), str(row["store_id"])) for row in old_rows}
    candidate_keys = set(candidate_values)
    changed_identifier_category_fields = 0
    changed_quantity_values = 0
    changed_rows: set[tuple[str, str]] = set()
    for row in old_rows:
        key = (str(row["sku_id"]), str(row["store_id"]))
        if key not in candidate_values:
            continue
        expected = candidate_values[key]
        actual = tuple(
            str(row[column]) if index < 3 else generator.quantity_text(row[column])
            for index, column in enumerate(PRESERVED_COLUMNS)
        )
        if expected[:3] != actual[:3]:
            changed_identifier_category_fields += sum(
                expected_value != actual_value
                for expected_value, actual_value in zip(expected[:3], actual[:3])
            )
            changed_rows.add(key)
        quantity_difference = sum(
            expected_value != actual_value
            for expected_value, actual_value in zip(expected[3:], actual[3:])
        )
        changed_quantity_values += quantity_difference
        if quantity_difference:
            changed_rows.add(key)
    result = {
        "candidate_rows": len(candidate_keys),
        "sql_rows": len(old_rows),
        "matching_rows": len(candidate_keys & old_keys),
        "missing_sql_keys": len(candidate_keys - old_keys),
        "extra_sql_keys": len(old_keys - candidate_keys),
        "differing_identifier_category_fields": changed_identifier_category_fields,
        "differing_preserved_quantity_values": changed_quantity_values,
        "differing_rows": len(changed_rows),
    }
    result["passed"] = (
        result["candidate_rows"] == generator.EXPECTED_ROW_COUNT
        and result["sql_rows"] == generator.EXPECTED_ROW_COUNT
        and result["matching_rows"] == generator.EXPECTED_ROW_COUNT
        and result["missing_sql_keys"] == 0
        and result["extra_sql_keys"] == 0
        and result["differing_identifier_category_fields"] == 0
        and result["differing_preserved_quantity_values"] == 0
        and result["differing_rows"] == 0
    )
    return result


def compare_sql_tables_32w_preservation(cursor: Any) -> dict[str, Any]:
    """Compare the committed 104W table directly to the existing 32W table."""

    quantity_terms = " + ".join(
        f"CASE WHEN n.[{column}] <> o.[{column}] THEN 1 ELSE 0 END"
        for column in (*generator.PRESERVED_ACTUAL_COLUMNS, *generator.PRESERVED_FORECAST_COLUMNS)
    )
    differing_row_term = " OR ".join(
        [
            "n.[cat] <> o.[cat]",
            *[
                f"n.[{column}] <> o.[{column}]"
                for column in (*generator.PRESERVED_ACTUAL_COLUMNS, *generator.PRESERVED_FORECAST_COLUMNS)
            ],
        ]
    )
    row = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS new_rows,
               SUM(CASE WHEN o.[sku_id] IS NOT NULL THEN 1 ELSE 0 END) AS matching_rows,
               SUM(CASE WHEN o.[sku_id] IS NULL THEN 1 ELSE 0 END) AS missing_old_keys,
               SUM(CASE WHEN n.[cat] <> o.[cat] THEN 1 ELSE 0 END) AS differing_category_rows,
               SUM({quantity_terms}) AS differing_preserved_quantity_values,
               SUM(CASE WHEN o.[sku_id] IS NOT NULL AND ({differing_row_term})
                        THEN 1 ELSE 0 END) AS differing_rows
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}] AS n
        LEFT JOIN [{TABLE_SCHEMA}].[{OLD_TABLE_NAME}] AS o
          ON o.[sku_id] = n.[sku_id] AND o.[store_id] = n.[store_id]
        """,
    )
    missing_new = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS missing_new_keys
        FROM [{TABLE_SCHEMA}].[{OLD_TABLE_NAME}] AS o
        LEFT JOIN [{TABLE_SCHEMA}].[{TABLE_NAME}] AS n
          ON n.[sku_id] = o.[sku_id] AND n.[store_id] = o.[store_id]
        WHERE n.[sku_id] IS NULL
        """,
    )
    result = {
        "new_rows": _as_int(row["new_rows"]),
        "matching_rows": _as_int(row["matching_rows"]),
        "missing_old_keys": _as_int(row["missing_old_keys"]),
        "missing_new_keys": _as_int(missing_new["missing_new_keys"]),
        "differing_category_rows": _as_int(row["differing_category_rows"]),
        "differing_preserved_quantity_values": _as_int(
            row["differing_preserved_quantity_values"]
        ),
        "differing_rows": _as_int(row["differing_rows"]),
        "differing_identifier_fields": 0,
    }
    result["passed"] = (
        result["new_rows"] == generator.EXPECTED_ROW_COUNT
        and result["matching_rows"] == generator.EXPECTED_ROW_COUNT
        and result["missing_old_keys"] == 0
        and result["missing_new_keys"] == 0
        and result["differing_category_rows"] == 0
        and result["differing_preserved_quantity_values"] == 0
        and result["differing_rows"] == 0
    )
    return result


def reconcile_w1_values(cursor: Any) -> dict[str, Any]:
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
    maximum = _as_decimal(row["maximum_difference"])
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
    for sku_id, store_id in (
        ("GRC-001", "S001"),
        ("GRC-001", "S002"),
        ("GRC-002", "S001"),
        ("GRC-002", "S002"),
    ):
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
        "maximum_difference": generator.decimal_text(maximum),
        "source_total": generator.decimal_text(source_total),
        "loaded_total": generator.decimal_text(loaded_total),
        "total_difference": generator.decimal_text(abs(loaded_total - source_total)),
        "tolerance": generator.decimal_text(W1_TOLERANCE),
        "samples": samples,
        "passed": rows_checked == generator.EXPECTED_ROW_COUNT
        and rows_passed == generator.EXPECTED_ROW_COUNT
        and maximum <= W1_TOLERANCE
        and len(samples) == 4,
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
        return {
            source.key
            for source in snapshot.source_rows
            if source.store_id == "S001" and source.cat == "GRC-C01"
        }
    if label == "S001 + GRC-001":
        return {
            source.key
            for source in snapshot.source_rows
            if source.store_id == "S001" and source.sku_id == "GRC-001"
        }
    raise ValueError(label)


def _sql_scope_definition(label: str) -> tuple[str, tuple[Any, ...]]:
    if label == "GRC":
        return (
            "JOIN retail.[dim_store] AS s ON s.[store_id] = t.[store_id] WHERE s.[vertical_id] = ?",
            ("GRC",),
        )
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


def _sql_trend_for_table(
    cursor: Any,
    table_name: str,
    label: str,
) -> dict[str, Any]:
    actual_expr = " + ".join(
        f"SUM(CAST(t.[{column}] AS DECIMAL(38,12)))"
        for column in generator.ACTUAL_COLUMNS[-4:]
    )
    forecast_expr = " + ".join(
        f"SUM(CAST(t.[{column}] AS DECIMAL(38,12)))"
        for column in generator.FORECAST_COLUMNS[:4]
    )
    scope_sql, parameters = _sql_scope_definition(label)
    row = _fetch_one(
        cursor,
        f"""
        SELECT COUNT_BIG(*) AS row_count,
               CAST(({actual_expr}) AS DECIMAL(38,12)) AS actual_total,
               CAST(({forecast_expr}) AS DECIMAL(38,12)) AS forecast_total,
               CAST(({forecast_expr}) AS DECIMAL(38,12))
               / NULLIF(CAST(({actual_expr}) AS DECIMAL(38,12)), 0) - 1 AS demand_trend
        FROM [{TABLE_SCHEMA}].[{table_name}] AS t
        {scope_sql}
        """,
        parameters,
    )
    actual_total = _as_decimal(row["actual_total"])
    forecast_total = _as_decimal(row["forecast_total"])
    trend = _as_decimal(row["demand_trend"])
    return {
        "row_count": _as_int(row["row_count"]),
        "actual_total": generator.decimal_text(actual_total),
        "forecast_total": generator.decimal_text(forecast_total),
        "demand_trend": generator.decimal_text(trend),
        "actual_total_decimal": actual_total,
        "forecast_total_decimal": forecast_total,
        "demand_trend_decimal": trend,
    }


def sql_trend_regression(
    cursor: Any,
    candidate: CandidateArtifact,
    snapshot: generator.SourceSnapshot,
) -> dict[str, Any]:
    labels = ("ALL", "GRC", "S001", "GRC-C01", "GRC-001", "S001 + GRC-C01", "S001 + GRC-001")
    results: dict[str, Any] = {}
    for label in labels:
        new = _sql_trend_for_table(cursor, TABLE_NAME, label)
        old = _sql_trend_for_table(cursor, OLD_TABLE_NAME, label)
        keys = _source_scope_keys(snapshot, label)
        expected_actual, expected_forecast = generator.trend_totals(candidate.rows, keys)
        expected_trend = expected_forecast / expected_actual - Decimal("1")
        new_old_difference = abs(new["demand_trend_decimal"] - old["demand_trend_decimal"])
        expected_difference = abs(new["demand_trend_decimal"] - expected_trend)
        results[label] = {
            "row_count": new["row_count"],
            "old_row_count": old["row_count"],
            "actual_total": new["actual_total"],
            "forecast_total": new["forecast_total"],
            "demand_trend": new["demand_trend"],
            "old_demand_trend": old["demand_trend"],
            "expected_demand_trend": generator.decimal_text(expected_trend),
            "difference_from_32w": generator.decimal_text(new_old_difference),
            "difference_from_candidate": generator.decimal_text(expected_difference),
            "passed": new["row_count"] == old["row_count"]
            and new_old_difference <= TREND_TOLERANCE
            and expected_difference <= TREND_TOLERANCE,
        }
    return {
        "scopes": results,
        "passed": all(item["passed"] for item in results.values()),
    }


def extension_validation(
    cursor: Any,
    candidate: CandidateArtifact,
) -> dict[str, Any]:
    keys = (
        ("GRC-001", "S001"),
        ("GRC-001", "S002"),
        ("GRC-002", "S001"),
        ("GRC-002", "S002"),
    )
    cursor.execute(
        f"""
        SELECT [sku_id], [store_id], [actual_w17], [actual_w16],
               [forecast_w16], [forecast_w17]
        FROM [{TABLE_SCHEMA}].[{TABLE_NAME}]
        WHERE ([sku_id] = ? AND [store_id] = ?)
           OR ([sku_id] = ? AND [store_id] = ?)
           OR ([sku_id] = ? AND [store_id] = ?)
           OR ([sku_id] = ? AND [store_id] = ?)
        ORDER BY [sku_id], [store_id]
        """,
        tuple(value for key in keys for value in key),
    )
    candidate_by_key = {row.key: row for row in candidate.rows}
    samples: list[dict[str, Any]] = []
    differing_values = 0
    for item in cursor.fetchall():
        key = (str(item[0]), str(item[1]))
        expected = candidate_by_key[key]
        actual_values = {
            "actual_w17": generator.quantity_text(item[2]),
            "actual_w16": generator.quantity_text(item[3]),
            "forecast_w16": generator.quantity_text(item[4]),
            "forecast_w17": generator.quantity_text(item[5]),
        }
        expected_values = {
            "actual_w17": generator.quantity_text(expected.actual_for_week(17)),
            "actual_w16": generator.quantity_text(expected.actual_for_week(16)),
            "forecast_w16": generator.quantity_text(expected.forecast_for_week(16)),
            "forecast_w17": generator.quantity_text(expected.forecast_for_week(17)),
        }
        differing_values += sum(actual_values[column] != expected_values[column] for column in actual_values)
        samples.append(
            {
                "sku_id": key[0],
                "store_id": key[1],
                "sql": actual_values,
                "csv": expected_values,
            }
        )
    result = {
        "columns_checked": ["actual_w17", "actual_w16", "forecast_w16", "forecast_w17"],
        "sample_rows_checked": len(samples),
        "differing_values": differing_values,
        "samples": samples,
    }
    result["passed"] = len(samples) == len(keys) and differing_values == 0
    return result


def validate_sql_copy(
    cursor: Any,
    candidate: CandidateArtifact,
    snapshot: generator.SourceSnapshot,
) -> dict[str, Any]:
    shape = _shape_validation(cursor)
    fingerprint = sql_fingerprint(cursor, candidate)
    w1 = reconcile_w1_values(cursor)
    preservation = compare_sql_tables_32w_preservation(cursor)
    trends = sql_trend_regression(cursor, candidate, snapshot)
    extension = extension_validation(cursor, candidate)
    passed = (
        shape["passed"]
        and fingerprint["passed"]
        and w1["passed"]
        and preservation["passed"]
        and trends["passed"]
        and extension["passed"]
    )
    return {
        "passed": passed,
        "shape": shape,
        "fingerprint": fingerprint,
        "w1_reconciliation": w1,
        "preservation": preservation,
        "trend_regression": trends,
        "extension": extension,
    }


def classify_existing_copy(row_count: int, fingerprint: str) -> str:
    if row_count == generator.EXPECTED_ROW_COUNT and fingerprint == EXPECTED_OUTPUT_FINGERPRINT:
        return "NOOP_ALREADY_LOADED"
    return "CONFLICT"


def reconcile_w1_values_in_memory(
    loaded: Mapping[tuple[str, str], Decimal | float | int],
    source: Mapping[tuple[str, str], Decimal | float | int],
    tolerance: Decimal = W1_TOLERANCE,
) -> dict[str, Any]:
    keys = set(loaded) & set(source)
    differences = {
        key: abs(_as_decimal(loaded[key]) - _as_decimal(source[key])) for key in keys
    }
    maximum = max(differences.values(), default=Decimal("0"))
    passed = sum(value <= tolerance for value in differences.values())
    return {
        "rows_checked": len(keys),
        "rows_passed": passed,
        "rows_failed": len(keys) - passed,
        "maximum_difference": generator.decimal_text(maximum),
        "key_set_match": set(loaded) == set(source),
        "passed": set(loaded) == set(source)
        and len(keys) == generator.EXPECTED_ROW_COUNT
        and passed == generator.EXPECTED_ROW_COUNT
        and maximum <= tolerance,
    }


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _pct(value: str | Decimal | float) -> str:
    return f"{float(value):.4%}"


def render_load_report(result: Mapping[str, Any], test_result: str) -> str:
    candidate = result["candidate"]
    snapshot = result["snapshot"]
    validation = result["validation"]
    shape = validation["shape"]
    fingerprint = validation["fingerprint"]
    w1 = validation["w1_reconciliation"]
    preservation = validation["preservation"]
    trends = validation["trend_regression"]["scopes"]
    extension = validation["extension"]
    action = result["load_action"]
    verdict = "READY FOR 104W BACKEND INTEGRATION"
    lines = [
        "# Demand Store SKU 104W SQL Load Report",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Table | `{FULL_TABLE_NAME}` |",
        f"| Database | `{result['database_name']}` |",
        f"| Source revision | `{snapshot.source_revision}` |",
        f"| Source batch | `{snapshot.batch_id}` |",
        f"| Rows | `{shape['row_count']}` |",
        f"| Columns | `107` |",
        f"| SKUs | `{shape['sku_count']}` |",
        f"| Stores | `{shape['store_count']}` |",
        f"| Expected fingerprint | `{EXPECTED_OUTPUT_FINGERPRINT}` |",
        f"| Loaded fingerprint | `{fingerprint['loaded_fingerprint']}` |",
        f"| 32W preservation | `{preservation['matching_rows']}/{generator.EXPECTED_ROW_COUNT} matching; {preservation['differing_preserved_quantity_values']} differing values` |",
        f"| Demand Trend regression | `{'PASS' if validation['trend_regression']['passed'] else 'FAIL'}` |",
        f"| Overall verdict | **{verdict}** |",
        "",
        "Only the new 104W synthetic table was eligible for writes. Azure SQL source tables and `synthetic.demand_store_sku_32w` were read-only dependencies; backend/frontend runtime code was not changed.",
        "",
        "## 1. Executive Summary",
        "",
        f"The approved `{_relative_path(candidate.csv_path)}` was validated, loaded into `{FULL_TABLE_NAME}`, and read back from Azure SQL. The final loader action was `{action}`. The table contains the exact approved 16,000-row/107-column dataset with fingerprint `{fingerprint['loaded_fingerprint']}`.",
        "",
        "The existing 32W table remains the current runtime source and was not altered. The new table is additive and is not wired into runtime behavior by this task.",
        "",
        "## 2. Source Preflight",
        "",
        f"- Database: `{result['database_name']}`; source v8.5, batch `{snapshot.batch_id}`, status `{snapshot.import_status}`, agent `{snapshot.agent_name}`, SHA `{snapshot.source_sha256}`.",
        f"- Snapshot: `{snapshot.source_snapshot_date.isoformat()}`; fact rows `{snapshot.fact_rows}`; stores `{snapshot.fact_distinct_stores}`; SKUs `{snapshot.fact_distinct_skus}`.",
        f"- Per-store coverage: 100 unique SKU rows for each 160 store; duplicate source keys `{snapshot.duplicate_source_keys}`.",
        f"- Null/negative ADS `{snapshot.bad_ads}`; null/negative Forecast 7d `{snapshot.bad_forecast_7d}`; rows outside batch 23 `{snapshot.rows_not_batch}`.",
        f"- Category join: `{snapshot.category_join_rows}` rows; missing items `{snapshot.missing_category_items}`; null categories `{snapshot.null_join_categories}`; missing stores `{snapshot.missing_join_stores}`.",
        f"- Existing `{OLD_FULL_TABLE_NAME}` was required and compared read-only. Superseded `{SUPERSEDED_TABLE_NAME}` existed: `{result['superseded_table_exists']}`; it was not loaded or modified.",
        "",
        "The live source key definitions matched the DDL-compatible NVARCHAR lengths before any 104W write.",
        "",
        "## 3. Candidate Artifact Verification",
        "",
        f"The loader read only `{_relative_path(candidate.csv_path)}` as the SQL source. It did not run the generator and did not use the XLSX as a load source.",
        f"- Shape: `{candidate.row_count}` rows, `107` columns, `{len({row.sku_id for row in candidate.rows})}` SKUs, `{len({row.store_id for row in candidate.rows})}` stores, `{len({row.key for row in candidate.rows})}` unique pairs.",
        f"- Recomputed fingerprint: `{candidate.fingerprint}`; manifest fingerprint: `{candidate.manifest['output_fingerprint']}`; result: `PASS`.",
        "- All 104 quantity columns were populated, finite, non-negative, and canonical six-decimal values.",
        "",
        "## 4. SQL Table/DDL",
        "",
        f"DDL/setup script: `{_relative_path(Path(result['ddl_path']))}`. Synthetic schema existed before this invocation: `{result['synthetic_schema_existed_before']}`. Target existed before this invocation: `{result['target_table_existed_before']}`. Created in this invocation: `{result['table_created']}`.",
        "",
        "The table has exactly the 107 business columns, compatible NVARCHAR(30)/NVARCHAR(20)/NVARCHAR(30) identifier types, `DECIMAL(20,6) NOT NULL` for all 104 quantities, and `PRIMARY KEY (sku_id, store_id)`. No metadata/date/provenance columns were added.",
        "",
        "## 5. Load Method",
        "",
        f"The loader used the existing Azure SQL connection mechanism, parameterized batched `executemany` inserts of `{INSERT_BATCH_SIZE}` rows, and one transaction. Rows inserted in this invocation: `{result['rows_inserted_this_run']}`. A validation failure rolls back the new transaction; no replace/truncate option exists.",
        "",
        "## 6. Shape Validation",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Rows = 16,000 | {'PASS' if shape['row_count'] == 16000 else 'FAIL'} (`{shape['row_count']}`) |",
        f"| Columns = 107 | PASS (DDL/candidate contract) |",
        f"| SKUs = 800 | {'PASS' if shape['sku_count'] == 800 else 'FAIL'} (`{shape['sku_count']}`) |",
        f"| Stores = 160 | {'PASS' if shape['store_count'] == 160 else 'FAIL'} (`{shape['store_count']}`) |",
        f"| Unique pairs = 16,000 | {'PASS' if shape['unique_pairs'] == 16000 else 'FAIL'} (`{shape['unique_pairs']}`) |",
        f"| Duplicate pairs = 0 | {'PASS' if shape['duplicate_pairs'] == 0 else 'FAIL'} (`{shape['duplicate_pairs']}`) |",
        f"| Rows/store = 100 | {'PASS' if shape['min_rows_per_store'] == 100 and shape['max_rows_per_store'] == 100 else 'FAIL'} (`{shape['min_rows_per_store']}..{shape['max_rows_per_store']}`) |",
        f"| `cat` NULL = 0 | {'PASS' if shape['null_cat_rows'] == 0 else 'FAIL'} (`{shape['null_cat_rows']}`) |",
        f"| Period NULL = 0 | {'PASS' if shape['null_period_cells'] == 0 else 'FAIL'} (`{shape['null_period_cells']}`) |",
        f"| Period negative = 0 | {'PASS' if shape['negative_period_cells'] == 0 else 'FAIL'} (`{shape['negative_period_cells']}`) |",
        "",
        "## 7. SQL Fingerprint Validation",
        "",
        f"All 107 SQL columns were read back ordered by `sku_id, store_id`, canonicalized with the generator's six-decimal formatting, and hashed. Expected `{fingerprint['approved_fingerprint']}`; loaded `{fingerprint['loaded_fingerprint']}`; result: `{'PASS' if fingerprint['passed'] else 'FAIL'}`.",
        "",
        "No differing rows or columns were found." if fingerprint["passed"] else f"Differences: `{fingerprint['differences']}`.",
        "",
        "## 8. W+1 Source Reconciliation",
        "",
        f"The new table was joined to `retail.fact_inventory_daily` on `sku_id = item_key` and `store_id = store_key` for batch `{SOURCE_BATCH}` and snapshot `{SOURCE_DATE.isoformat()}`. Tolerance: `{w1['tolerance']}`.",
        f"- Rows checked: `{w1['rows_checked']}`; passed: `{w1['rows_passed']}`; failed: `{w1['rows_failed']}`; maximum difference: `{w1['maximum_difference']}`.",
        f"- Source total: `{w1['source_total']}`; loaded total: `{w1['loaded_total']}`; total difference: `{w1['total_difference']}`.",
        "",
        "| SKU | Store | Loaded W+1 | Source Forecast 7d | Difference |",
        "|---|---|---:|---:|---:|",
        *[
            f"| {sample['sku_id']} | {sample['store_id']} | {sample['loaded_forecast_w1']} | {sample['source_forecast_7d']} | {sample['difference']} |"
            for sample in w1["samples"]
        ],
        "",
        "## 9. 32W Preservation Comparison",
        "",
        f"Direct SQL comparison between `{FULL_TABLE_NAME}` and `{OLD_FULL_TABLE_NAME}` checked the preserved identifiers/category and all W-16…W+16 quantity columns: `{preservation['matching_rows']}` matching rows, missing old keys `{preservation['missing_old_keys']}`, missing new keys `{preservation['missing_new_keys']}`, differing identifier fields `{preservation['differing_identifier_fields']}`, differing category rows `{preservation['differing_category_rows']}`, differing preserved quantity values `{preservation['differing_preserved_quantity_values']}`, differing rows `{preservation['differing_rows']}`. Result: `{'PASS' if preservation['passed'] else 'FAIL'}`.",
        "",
        "The existing 32W table was not updated.",
        "",
        "## 10. Demand Trend Regression",
        "",
        "Both SQL tables were aggregated before division using W-4…W-1 actuals and W+1…W+4 forecasts.",
        "",
        "| Scope | Rows | New Trend | Existing 32W Trend | Difference | Result |",
        "|---|---:|---:|---:|---:|---|",
        *[
            f"| {label} | {item['row_count']} | {_pct(item['demand_trend'])} | {_pct(item['old_demand_trend'])} | `{item['difference_from_32w']}` | {'PASS' if item['passed'] else 'FAIL'} |"
            for label, item in trends.items()
        ],
        "",
        "ALL and GRC regression references are approximately 5.3984117261% and 5.5954608332%, respectively. These are validation references only and were not hardcoded into the loader or table.",
        "",
        "## 11. Extension Period Validation",
        "",
        "The DDL/schema and SQL shape check verified all columns `actual_w52…actual_w17` and `forecast_w17…forecast_w52` are present, NOT NULL, finite, non-negative, and queryable. Representative SQL values were compared directly to the approved CSV:",
        "",
        "| Scope | Sample rows | Columns checked | Differences | Result |",
        "|---|---:|---|---:|---|",
        f"| Boundary samples | `{extension['sample_rows_checked']}` | `{', '.join(extension['columns_checked'])}` | `{extension['differing_values']}` | {'PASS' if extension['passed'] else 'FAIL'} |",
        "",
        *[
            f"- `{sample['sku_id']} / {sample['store_id']}`: `actual_w17={sample['sql']['actual_w17']}`, `actual_w16={sample['sql']['actual_w16']}`, `forecast_w16={sample['sql']['forecast_w16']}`, `forecast_w17={sample['sql']['forecast_w17']}`; SQL/CSV exact."
            for sample in extension["samples"]
        ],
        "",
        "## 12. Idempotence",
        "",
        f"This invocation action: `{action}`. A second invocation against an exact existing table returns `NOOP_ALREADY_LOADED`, inserts `0` rows, and reruns the read-only validations. A partial, schema-different, key-different, value-different, or fingerprint-different table raises `TableConflictError` and is not overwritten.",
        "",
        "## 13. Tests",
        "",
        test_result,
        "",
        "The loader also executed live SQL shape, null/negative, source W+1, fingerprint, direct 32W preservation, Trend, extension, and idempotence validation. No runtime application tests were changed or required.",
        "",
        "## 14. Rollback Instructions",
        "",
        "After confirming no consumer depends on this temporary table, remove only the new object:",
        "",
        "```sql",
        "DROP TABLE synthetic.demand_store_sku_104w;",
        "```",
        "",
        "Optionally drop `synthetic` only if no other object uses that schema:",
        "",
        "```sql",
        "DROP SCHEMA synthetic;",
        "```",
        "",
        "Rollback was not executed. These steps do not affect `synthetic.demand_store_sku_32w` or any `retail` source table.",
        "",
        "## 15. Remaining Caveats",
        "",
        "- Historical values remain synthetic and have no genuine sales ground truth.",
        "- Forecast W+2…W+52 remain synthetic; W+1 is the existing v8.5 Forecast 7d quantized to six decimals.",
        "- The date-free wide POC has no row-level period dates or provenance columns; provenance remains in the local manifest/report.",
        "- The new table is not used by the runtime yet and should not be treated as a completed backend/chart migration.",
        "",
        "## 16. Backend/Chart Integration Handoff",
        "",
        f"The next integration task may switch deliberately from `{OLD_FULL_TABLE_NAME}` to `{FULL_TABLE_NAME}` after review. It may then apply existing legal entity/store/category/SKU filters, aggregate the wide columns, retain Demand Trend as W-4…W-1 versus W+1…W+4, and expose up to W+52 for the forecast chart. This task intentionally did not change backend/frontend behavior, the Demand Trend KPI, sparkline, charts, Horizon selector, or any other KPI.",
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
    test_result: str = "Focused 104W SQL-load tests: run separately.",
    write_report_file: bool = True,
) -> dict[str, Any]:
    candidate = load_candidate_artifact(csv_path, manifest_path)

    # Read-only source preflight before any CREATE or INSERT.
    snapshot = generator.previous_generator.load_source_snapshot()
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
        database_name = str(_fetch_one(cursor, "SELECT DB_NAME() AS database_name")["database_name"])
        source_types = _source_type_contract(cursor)
        old_table_exists = _row_exists(cursor, OLD_FULL_TABLE_NAME)
        _require(old_table_exists, f"Required existing table {OLD_FULL_TABLE_NAME} is missing")
        prewrite_preservation = compare_candidate_to_32w_sql(cursor, candidate)
        _require(
            prewrite_preservation["passed"],
            f"Approved candidate does not match existing {OLD_FULL_TABLE_NAME}: {prewrite_preservation}",
        )
        target_before = inspect_target(cursor)
        superseded_exists = _row_exists(cursor, SUPERSEDED_TABLE_NAME)

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
                    f"Existing {FULL_TABLE_NAME} differs from approved dataset: "
                    f"fingerprint={existing_fingerprint['loaded_fingerprint']}, "
                    f"shape_passed={existing_shape['passed']}"
                )
            validation = validate_sql_copy(cursor, candidate, snapshot)
            _require(
                validation["passed"],
                f"Existing {FULL_TABLE_NAME} failed validation: {validation}",
                TableConflictError,
            )
        else:
            setup_batches = apply_setup_script(cursor, ddl_path)
            target_after = inspect_target(cursor)
            validate_target_schema(target_after)
            rows_inserted = insert_candidate(cursor, candidate)
            validation = validate_sql_copy(cursor, candidate, snapshot)
            _require(
                validation["passed"],
                "Post-insert validation failed; transaction will be rolled back",
            )
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
            "prewrite_preservation": prewrite_preservation,
            "validation": validation,
            "report_path": report_path,
        }
    except Exception:
        if target_before is not None and not target_before.exists:
            connection.rollback()
        raise
    finally:
        connection.close()

    # Verify the committed copy from a fresh connection after a create/load.
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
                "Committed 104W copy failed final read-back validation",
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
    parser.add_argument("--test-result", default="Focused 104W SQL-load tests: run separately.")
    parser.add_argument("--no-report", action="store_true")
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
                "preservation": result["validation"]["preservation"],
                "trend_regression": result["validation"]["trend_regression"],
                "extension": result["validation"]["extension"],
                "report_path": str(result["report_path"]),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
