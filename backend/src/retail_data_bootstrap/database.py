from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from mssql_python import connect
from mssql_python import constants as sql_constants

from .normalization import NormalizedDataset, PRIMARY_KEYS
from .paths import load_azure_sql_connection_string


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    keys: tuple[str, ...]


TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "LegalEntity": ("legal_entity_id", "legal_entity_name", "short_name", "workforce_base_per_size", "sales_per_fte", "peak_season_factor", "total_store_size"),
    "Store": ("store_id", "legal_entity_id", "store_name", "cluster", "size_factor", "health_factor", "footfall_index", "channel"),
    "Category": ("category_id", "legal_entity_id", "category_name", "is_perishable"),
    "Vendor": ("vendor_account", "vendor_code", "vendor_name", "vendor_group", "currency", "payment_terms", "delivery_terms", "lead_time_days", "moq_units", "otif_pct", "fill_pct", "defect_pct", "lead_adherence_pct"),
    "Brand": ("brand_name",),
    "Sku": ("sku_id", "legal_entity_id", "category_id", "item_name", "is_perishable", "base_ads", "price", "margin_pct", "cost", "lead_time_days", "on_hand_days", "open_po_units", "safety_days", "expiry_days", "growth_factor", "elasticity", "competitor_index", "funding_pct", "cannibalization_pct", "is_promo", "is_viral", "sales_uom", "buy_uom", "pack_factor", "channel", "seasonality_factor", "stock_factor", "sales_per_fte", "vendor_account", "brand_name"),
    "TradeAgreement": ("sku_id", "vendor_account", "valid_from", "min_quantity", "item_name", "unit_price", "currency", "lead_time_days", "discount_pct", "valid_to", "is_designated"),
    "Promotion": ("promotion_id", "promotion_name", "discount_type", "scope", "legal_entity_id", "target_category", "season", "peak_month", "mechanism", "discount_pct", "value_rule", "min_quantity_threshold", "supplier_funding_pct", "expected_uplift_pct", "prebuy_uplift_units", "valid_from", "valid_to", "d365_construct"),
    "InventorySnapshot": ("sku_id", "ads", "inventory_position", "reorder_point", "max_inventory", "days_of_supply", "inventory_state", "price", "inventory_value", "at_risk_value", "expiry_units", "order_units", "order_value", "weekly_gmv", "margin_amount", "funding_amount", "open_po_units"),
    "StoreSkuSnapshot": ("sku_id", "store_id", "ads", "on_hand_units", "open_po_units", "inventory_position", "reorder_point", "max_inventory", "days_of_supply", "inventory_state", "price", "inventory_value", "at_risk_value", "forecast_7d", "order_sales_units", "pack_factor", "order_buy_units", "order_value", "promo_incremental_margin", "contribution_per_day", "labour_fte"),
    "ReplenishmentProposal": ("sku_id", "reorder_required", "order_sales_units", "buy_uom", "order_buy_units", "designated_vendor_account", "designated_unit_price", "amount", "best_price_vendor_account", "best_price", "saving_vs_designated"),
    "BrandEvent": ("store_id", "event_name", "legal_entity_id", "demand_lift"),
    "WorkforceSnapshot": ("store_id", "event_name", "event_lift", "workforce_base", "peak_factor", "scheduled_fte", "required_fte", "gap_fte", "surplus_fte", "coverage_pct"),
    "MonthlySales": ("period_label", "legal_entity_id", "sales_amount"),
}

LOAD_ORDER = tuple(TABLE_COLUMNS)
TABLE_SPECS = {
    name: TableSpec(
        name=name,
        columns=columns + ("source_load_id", "source_sheet", "source_row"),
        keys=PRIMARY_KEYS[name],
    )
    for name, columns in TABLE_COLUMNS.items()
}

SOURCE_LOAD_COLUMNS = {
    "source_load_id", "workbook_name", "workbook_sha256", "source_type",
    "load_status", "loaded_at", "completed_at", "row_count",
}


def open_connection():
    return connect(load_azure_sql_connection_string(), timeout=30)


def inspect_catalog(connection=None) -> dict[str, Any]:
    owned = connection is None
    connection = connection or open_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT s.name, t.name, c.name, ty.name, c.max_length,
                   c.precision, c.scale, c.is_nullable, c.column_id
            FROM sys.tables AS t
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            JOIN sys.columns AS c ON c.object_id = t.object_id
            JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
            WHERE s.name = N'retail'
            ORDER BY t.name, c.column_id;
            """
        )
        tables: dict[str, list[dict[str, Any]]] = {}
        for row in cursor.fetchall():
            tables.setdefault(row[1], []).append(
                {
                    "name": row[2],
                    "type": row[3],
                    "max_length": row[4],
                    "precision": row[5],
                    "scale": row[6],
                    "nullable": bool(row[7]),
                }
            )
        return {"schema_exists": bool(tables) or _schema_exists(cursor), "tables": tables}
    finally:
        if owned:
            connection.close()


def _schema_exists(cursor) -> bool:
    cursor.execute("SELECT CASE WHEN SCHEMA_ID(N'retail') IS NULL THEN 0 ELSE 1 END;")
    return bool(cursor.fetchone()[0])


def _expected_columns(table: str) -> set[str]:
    if table == "SourceLoad":
        return SOURCE_LOAD_COLUMNS
    return set(TABLE_SPECS[table].columns) | {"loaded_at"}


def validate_no_conflicts(catalog: dict[str, Any]) -> None:
    expected_tables = {"SourceLoad", *TABLE_SPECS}
    conflicts: list[str] = []
    for table, columns in catalog["tables"].items():
        if table not in expected_tables:
            continue
        actual = {column["name"] for column in columns}
        expected = _expected_columns(table)
        if actual != expected:
            conflicts.append(
                f"retail.{table}: expected columns {sorted(expected)}, found {sorted(actual)}"
            )
    if conflicts:
        raise RuntimeError(
            "Existing Azure SQL objects conflict with this migration; no changes were made:\n"
            + "\n".join(conflicts)
        )


def validate_value_lengths(dataset: NormalizedDataset, catalog: dict[str, Any]) -> None:
    errors: list[str] = []
    for table, rows in dataset.tables.items():
        definitions = {column["name"]: column for column in catalog["tables"][table]}
        for row in rows:
            for column, value in row.items():
                definition = definitions.get(column)
                if value is None or not definition or definition["type"] not in {"nvarchar", "varchar", "char", "nchar"}:
                    continue
                maximum = int(definition["max_length"])
                if definition["type"] in {"nvarchar", "nchar"}:
                    maximum //= 2
                if len(str(value)) > maximum:
                    errors.append(
                        f"retail.{table}.{column} source row {row.get('source_row')} "
                        f"has {len(str(value))} characters; maximum is {maximum}"
                    )
    if errors:
        raise ValueError("Workbook text exceeds Azure SQL column limits:\n" + "\n".join(errors[:20]))


def apply_migration(path: Path) -> dict[str, Any]:
    connection = open_connection()
    try:
        before = inspect_catalog(connection)
        validate_no_conflicts(before)
        script = path.read_text(encoding="utf-8")
        batches = [
            batch.strip()
            for batch in re.split(r"^\s*GO\s*$", script, flags=re.IGNORECASE | re.MULTILINE)
            if batch.strip()
        ]
        cursor = connection.cursor()
        try:
            for batch in batches:
                cursor.execute(batch)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        after = inspect_catalog(connection)
        validate_no_conflicts(after)
        missing = sorted({"SourceLoad", *TABLE_SPECS} - set(after["tables"]))
        if missing:
            raise RuntimeError(f"Migration completed but expected tables are missing: {missing}")
        return {"before": before, "after": after, "batch_count": len(batches)}
    finally:
        connection.close()


def _source_load(cursor, dataset: NormalizedDataset) -> int:
    cursor.execute(
        """
        MERGE retail.SourceLoad WITH (HOLDLOCK) AS target
        USING (SELECT ? AS workbook_sha256) AS source
        ON target.workbook_sha256 = source.workbook_sha256
        WHEN MATCHED THEN UPDATE SET
            workbook_name = ?, source_type = N'EXCEL', load_status = N'STARTED',
            loaded_at = SYSUTCDATETIME(), completed_at = NULL, row_count = NULL
        WHEN NOT MATCHED THEN INSERT
            (workbook_name, workbook_sha256, source_type, load_status)
            VALUES (?, source.workbook_sha256, N'EXCEL', N'STARTED');
        """,
        (dataset.workbook_sha256, dataset.workbook_name, dataset.workbook_name),
    )
    cursor.execute(
        "SELECT source_load_id FROM retail.SourceLoad WHERE workbook_sha256 = ?;",
        (dataset.workbook_sha256,),
    )
    return int(cursor.fetchone()[0])


def _upsert_table(cursor, spec: TableSpec, rows: list[dict[str, Any]], load_id: int) -> None:
    if not rows:
        return
    columns = spec.columns
    quoted = ", ".join(f"[{column}]" for column in columns)
    stage = f"#Stage_{spec.name}"
    placeholders = ", ".join("?" for _ in columns)
    raw_values: list[tuple[Any, ...]] = []
    for row in rows:
        enriched = dict(row)
        enriched["source_load_id"] = load_id
        raw_values.append(tuple(_database_value(enriched[column]) for column in columns))
    lengths = [
        max(1, max((len(str(row[index])) for row in raw_values if row[index] is not None), default=1))
        for index in range(len(columns))
    ]
    if any(length > 4000 for length in lengths):
        raise ValueError(f"retail.{spec.name} staging value exceeds NVARCHAR(4000)")
    definitions = ", ".join(
        f"[{column}] NVARCHAR({length}) NULL"
        for column, length in zip(columns, lengths)
    )
    cursor.execute(f"CREATE TABLE {stage} ({definitions});")
    if hasattr(cursor, "fast_executemany"):
        cursor.fast_executemany = True
    cursor.setinputsizes(
        [(sql_constants.SQL_WVARCHAR, length, 0) for length in lengths]
    )
    try:
        cursor.executemany(
            f"INSERT INTO {stage} ({quoted}) VALUES ({placeholders});",
            raw_values,
        )
    except Exception as error:
        raise RuntimeError(
            f"Bulk staging failed for retail.{spec.name} ({len(rows)} rows)"
        ) from error
    join = " AND ".join(f"target.[{key}] = source.[{key}]" for key in spec.keys)
    updates = [column for column in columns if column not in spec.keys]
    update_sql = ", ".join(f"target.[{column}] = source.[{column}]" for column in updates)
    insert_values = ", ".join(f"source.[{column}]" for column in columns)
    cursor.execute(
        f"""
        MERGE retail.[{spec.name}] WITH (HOLDLOCK) AS target
        USING {stage} AS source
        ON {join}
        WHEN MATCHED THEN UPDATE SET {update_sql}, target.loaded_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT ({quoted}) VALUES ({insert_values});
        """
    )
    cursor.execute(f"DROP TABLE {stage};")


def _database_value(value: Any) -> Any:
    """Use stable driver-friendly values for Azure SQL bulk binding.

    mssql-python 1.13's column-wise executemany path cannot bind native Python
    floats reliably. Decimal also prevents binary-float noise from entering the
    normalized DECIMAL columns.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def ingest_structured(dataset: NormalizedDataset, *, dry_run: bool) -> dict[str, Any]:
    summary = {
        "dry_run": dry_run,
        "workbook": dataset.workbook_name,
        "source_row_counts": dataset.row_counts,
        "issues": list(dataset.issues),
    }
    if dry_run:
        summary["database_row_counts"] = None
        return summary

    connection = open_connection()
    try:
        catalog = inspect_catalog(connection)
        validate_no_conflicts(catalog)
        missing = sorted({"SourceLoad", *TABLE_SPECS} - set(catalog["tables"]))
        if missing:
            raise RuntimeError(
                f"Azure SQL setup is incomplete; apply the migration first. Missing: {missing}"
            )
        validate_value_lengths(dataset, catalog)
        cursor = connection.cursor()
        try:
            load_id = _source_load(cursor, dataset)
            for name in LOAD_ORDER:
                _upsert_table(cursor, TABLE_SPECS[name], dataset.tables[name], load_id)
            total = sum(dataset.row_counts.values())
            cursor.execute(
                """
                UPDATE retail.SourceLoad
                SET load_status = N'COMPLETED', completed_at = SYSUTCDATETIME(), row_count = ?
                WHERE source_load_id = ?;
                """,
                (total, load_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        counts: dict[str, int] = {}
        cursor = connection.cursor()
        for name in LOAD_ORDER:
            cursor.execute(f"SELECT COUNT_BIG(*) FROM retail.[{name}];")
            counts[name] = int(cursor.fetchone()[0])
        summary["database_row_counts"] = counts
        summary["source_load_id"] = load_id
        return summary
    finally:
        connection.close()


def validate_live_relational(dataset: NormalizedDataset) -> dict[str, Any]:
    connection = open_connection()
    try:
        cursor = connection.cursor()
        counts: dict[str, int] = {}
        for name in LOAD_ORDER:
            cursor.execute(f"SELECT COUNT_BIG(*) FROM retail.[{name}];")
            counts[name] = int(cursor.fetchone()[0])
        count_mismatches = {
            name: {"source": dataset.row_counts[name], "database": counts[name]}
            for name in LOAD_ORDER
            if dataset.row_counts[name] != counts[name]
        }
        cursor.execute(
            """
            SELECT load_status, row_count
            FROM retail.SourceLoad
            WHERE workbook_sha256 = ?;
            """,
            (dataset.workbook_sha256,),
        )
        load_row = cursor.fetchone()
        cursor.execute(
            """
            SELECT fk.name, fk.is_disabled, fk.is_not_trusted
            FROM sys.foreign_keys AS fk
            JOIN sys.tables AS t ON t.object_id = fk.parent_object_id
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            WHERE s.name = N'retail'
            ORDER BY fk.name;
            """
        )
        foreign_keys = [
            {"name": row[0], "disabled": bool(row[1]), "not_trusted": bool(row[2])}
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT t.name
            FROM sys.tables AS t
            JOIN sys.schemas AS s ON s.schema_id = t.schema_id
            JOIN sys.indexes AS i ON i.object_id = t.object_id AND i.is_primary_key = 1
            WHERE s.name = N'retail';
            """
        )
        primary_key_tables = {row[0] for row in cursor.fetchall()}
        expected_tables = {"SourceLoad", *TABLE_SPECS}
        constraint_errors = [
            item["name"] for item in foreign_keys if item["disabled"] or item["not_trusted"]
        ]
        errors: list[str] = []
        if count_mismatches:
            errors.append(f"row-count mismatches: {count_mismatches}")
        if not load_row or load_row[0] != "COMPLETED":
            errors.append("source load is not marked COMPLETED")
        elif int(load_row[1]) != sum(dataset.row_counts.values()):
            errors.append("source load row_count does not match normalized total")
        if constraint_errors:
            errors.append(f"disabled or untrusted foreign keys: {constraint_errors}")
        if primary_key_tables != expected_tables:
            errors.append(
                f"primary key table mismatch: missing={sorted(expected_tables - primary_key_tables)}"
            )
        return {
            "valid": not errors,
            "database_row_counts": counts,
            "count_mismatches": count_mismatches,
            "source_load_status": load_row[0] if load_row else None,
            "source_load_row_count": int(load_row[1]) if load_row and load_row[1] is not None else None,
            "foreign_key_count": len(foreign_keys),
            "foreign_keys_trusted": not constraint_errors,
            "primary_key_table_count": len(primary_key_tables),
            "errors": errors,
        }
    finally:
        connection.close()
