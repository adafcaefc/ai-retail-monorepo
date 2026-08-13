"""Fill `retail.dim_*` from `resources/dbtemp/schema_with_data.json`.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/seed_retail_dims_from_json.py

Why the JSON and not the workbook: `scripts/extract_workbook_schema.py` already
read the 10 MB workbook once, inferred every column type, and verified that
every primary key is unique and every foreign key resolves with zero orphans.
Re-opening the workbook here with openpyxl would cost ~13 s and ~220 MB to
re-derive facts that are already checked in. The workbook stays the origin of
the data; regenerate the JSON from it whenever the workbook changes.

Upserts rather than truncate-and-load, so this is safe to re-run: the fact
tables carry foreign keys into these dimensions, and deleting a dimension row
would either fail or orphan history.

CALENDAR CAVEAT: the workbook has no date column anywhere, so `dim_calendar` is
generated arithmetically. `is_ramadan_est` and `is_idulfitri_est` are
ESTIMATES derived from published approximate Gregorian dates — they are not
confirmed against an authoritative Hijri calendar and have not been signed off
by the client. Do not present them as official dates; treat them as a modelling
hint that needs replacing before anything depends on it.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
SCHEMA = "retail"

CALENDAR_START = date(2024, 1, 1)
CALENDAR_END = date(2027, 12, 31)

# Approximate Gregorian spans. See the CALENDAR CAVEAT in the module docstring:
# these are estimates, not authoritative Hijri conversions.
RAMADAN_EST: tuple[tuple[date, date], ...] = (
    (date(2024, 3, 11), date(2024, 4, 9)),
    (date(2025, 3, 1), date(2025, 3, 30)),
    (date(2026, 2, 18), date(2026, 3, 19)),
    (date(2027, 2, 8), date(2027, 3, 9)),
)
IDULFITRI_EST: tuple[tuple[date, date], ...] = (
    (date(2024, 4, 10), date(2024, 4, 11)),
    (date(2025, 3, 31), date(2025, 4, 1)),
    (date(2026, 3, 20), date(2026, 3, 21)),
    (date(2027, 3, 10), date(2027, 3, 11)),
)


def load_tables() -> dict[str, dict[str, Any]]:
    """Return {table_name: {"columns": [...], "rows": [dict, ...]}}."""
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    tables: dict[str, dict[str, Any]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = {
            "columns": names,
            "rows": [dict(zip(names, row)) for row in table["rows"]],
        }
    return tables


def upsert(connection: Any, table: str, key: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    columns = list(rows[0].keys())
    quoted = ", ".join(f'"{name}"' for name in columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    updates = ", ".join(
        f'"{name}" = EXCLUDED."{name}"' for name in columns if name != key
    )

    connection.execute(
        text(
            f"INSERT INTO {SCHEMA}.{table} ({quoted}) VALUES ({placeholders})"
            f" ON CONFLICT ({key}) DO UPDATE SET {updates}"
        ),
        rows,
    )
    return len(rows)


def build_calendar() -> list[dict[str, Any]]:
    def within(day: date, spans: tuple[tuple[date, date], ...]) -> bool:
        return any(start <= day <= end for start, end in spans)

    rows: list[dict[str, Any]] = []
    day = CALENDAR_START
    while day <= CALENDAR_END:
        # Payday window: the 1st, and the 25th to month end. Indonesian retail
        # demand lifts in that window (see the plan's §6.4 reference).
        last_day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_day -= timedelta(days=1)
        rows.append(
            {
                "cal_date": day,
                "dow": day.weekday(),
                "iso_week": day.isocalendar().week,
                "month": day.month,
                "year": day.year,
                "is_weekend": day.weekday() >= 5,
                "is_payday_window": day.day == 1 or day.day >= 25,
                "is_ramadan_est": within(day, RAMADAN_EST),
                "is_idulfitri_est": within(day, IDULFITRI_EST),
            }
        )
        day += timedelta(days=1)
    return rows


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        print("      run scripts/extract_workbook_schema.py first")
        return 1

    tables = load_tables()
    missing = [
        name
        for name in ("verticals", "stores", "vendors", "sku_master")
        if name not in tables
    ]
    if missing:
        print(f"FAIL  source is missing tables: {', '.join(missing)}")
        return 1

    verticals = [
        {
            "vertical_id": row["vertical_id"],
            "name": row["vertical"],
            "dashboard_label": row["dashboard_label"],
            "sales_per_fte": row["sales_per_fte"],
            "d365_data_area": None,
            # Preserves the sheet's ordering, which the dashboards follow.
            "sort_order": index,
        }
        for index, row in enumerate(tables["verticals"]["rows"])
    ]

    vendors = [
        {
            "vendor_account": row["vendor_account"],
            "vendor_short": row["vendor"],
            "vendor_name": row["vendor_name"],
            "vendor_group": row["group"],
            "currency": row["currency"],
            "payment_terms": row["payment_terms"],
            "delivery_terms": row["delivery_terms"],
            "lead_time_days": row["lead_time_d"],
            "moq_units": row["moq_units"],
            "otif_pct": row["otif_pct"],
            "fill_pct": row["fill_pct"],
            "defect_pct": row["defect_pct"],
            "lead_adherence_pct": row["lead_adherence_pct"],
        }
        for row in tables["vendors"]["rows"]
    ]

    stores = [
        {
            "store_id": row["store_id"],
            "vertical_id": row["vertical_id"],
            "name": row["store_name"],
            "cluster": row["cluster"],
            "channel": row["channel"],
            "size_index": row["size"],
            "health_index": row["health"],
            "footfall_index": row["footfall_idx"],
            "invent_location_id": None,
            "opened_at": None,
            "closed_at": None,
        }
        for row in tables["stores"]["rows"]
    ]

    # SKU_Master carries the vendor's short name ("Vendor E"), not its account
    # code. schema_with_data.json already declares and verifies
    # sku_master.vendor -> vendors.vendor as a foreign key with zero orphans,
    # so every lookup below is guaranteed to resolve.
    vendor_account_of = {
        row["vendor"]: row["vendor_account"] for row in tables["vendors"]["rows"]
    }

    items = []
    unresolved: list[str] = []
    for row in tables["sku_master"]["rows"]:
        account = vendor_account_of.get(row["vendor"])
        if row["vendor"] and account is None:
            unresolved.append(row["vendor"])
        items.append(
            {
                "item_id": row["sku_id"],
                "vertical_id": row["vertical_id"],
                "category_id": row["cat_id"],
                "category_name": row["category"],
                "name": row["item"],
                "brand": row["brand"],
                "vendor_account": account,
                "is_perishable": str(row["perishable"]).strip().upper() == "Y",
                "shelf_life_days": row["expiry_d"],
                "sales_uom": row["sales_uom"],
                "buy_uom": row["buy_uom"],
                "pack_factor": row["pack_factor"],
                "lead_time_days": row["lead_d"],
                "safety_days": row["safety_d"],
                "base_ads": row["base_ads"],
                "price": row["price"],
                "unit_cost": row["cost"],
                "margin_pct": row["margin_pct"],
                "seasonality_index": row["seasonality"],
                "lifecycle": None,
                # What-If parameters. `f07` classifies a slow mover by growth;
                # `f01` prices a promo lift from the other two. Carried on the
                # item because they describe the item, not any one day of it.
                "growth_index": row["growth"],
                "is_promo_eligible": str(row["promo"]).strip().upper() == "Y",
                "cannibalisation_pct": row["cannib_pct"],
                "elasticity": row["elasticity"],
                # A1 badges a SKU with up to three signals; this is one of them.
                "is_viral": str(row["viral"]).strip().upper() == "Y",
                # The pair that makes a store-scoped board possible without the
                # 16,000-row grid:
                #
                #   on_hand(sku, store) = base_ads * onhand_days * stock_factor
                #                         * store.health_index * store.size_index
                #
                # Checked against every ENGINE_STORE row at zero difference, so
                # a store-scoped position is the workbook's own figure and not
                # an approximation of it.
                "onhand_days": row["onhand_days"],
                "stock_factor": row["stockf"],
            }
        )

    if unresolved:
        print(f"FAIL  {len(unresolved)} items name a vendor with no account code")
        print(f"      first few: {sorted(set(unresolved))[:5]}")
        return 1

    calendar = build_calendar()

    engine = get_engine()
    counts: list[tuple[str, int]] = []

    with engine.begin() as connection:
        counts.append(
            ("dim_vertical", upsert(connection, "dim_vertical", "vertical_id", verticals))
        )
        counts.append(
            ("dim_vendor", upsert(connection, "dim_vendor", "vendor_account", vendors))
        )
        counts.append(("dim_store", upsert(connection, "dim_store", "store_id", stores)))
        counts.append(("dim_item", upsert(connection, "dim_item", "item_id", items)))
        counts.append(
            ("dim_calendar", upsert(connection, "dim_calendar", "cal_date", calendar))
        )

        batch_id = connection.execute(
            text(
                """
                INSERT INTO audit.import_batches (
                    agent_name, workbook_name, workbook_version, workbook_path,
                    import_status, imported_by, completed_at,
                    total_sheets, total_rows
                ) VALUES (
                    'retail_dims_seed', :workbook_name, 'v8.2', :workbook_path,
                    'COMPLETED', 'seed_retail_dims_from_json.py',
                    CURRENT_TIMESTAMP, :total_sheets, :total_rows
                )
                RETURNING id
                """
            ),
            {
                "workbook_name": SOURCE.name,
                "workbook_path": str(SOURCE),
                "total_sheets": len(counts),
                "total_rows": sum(rows for _, rows in counts),
            },
        ).scalar_one()

    print(f"Seeded {SCHEMA} dimensions, import batch {batch_id}\n")
    for name, rows in counts:
        print(f"  {name:<16} {rows:>6}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
