"""Fill `retail.fact_*`, `retail.trade_agreement` and
`retail.replenishment_proposal` from `resources/dbtemp/schema_with_data.json`.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/seed_retail_facts_from_json.py

Run `seed_retail_dims_from_json.py` first — every row here carries a foreign
key into a dimension, and this script refuses to start if the dimensions are
empty rather than failing 16,000 rows into a transaction.

WHAT THIS DOES NOT LOAD, DELIBERATELY
-------------------------------------
`fact_sales_daily` stays empty. The workbook holds one average daily rate per
SKU and no history at all, so any daily series written here would be invented.
That table will later hold real D365 history, and there would be no marker
separating the two — a reader six months from now would find a continuous
series and have no way to know the first two years were made up. An empty
table is a question; a fabricated one is a wrong answer.

THE SNAPSHOT DATE
-----------------
The workbook has no date column anywhere (the same caveat the dimension seeder
records for `dim_calendar`). But `fact_inventory_daily` is a daily series and
needs one, so every row lands on `SNAPSHOT_DATE`: a single stated day, not a
spread that would imply measurements taken over time.

It is a modelling decision, not a reading. `Constants` B6 carries
`month_index = 6`, which is July on the workbook's own zero-based months, and
the dataset is a 2026 vintage — hence 1 July 2026. Change it here if the
client states a real as-of date; nothing else needs to move.
"""

from __future__ import annotations

import getpass
import json
import socket
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
# `scripts/` is not a package, and this file is also imported by path from
# backend/tests, which puts neither directory on the path for us.
sys.path.insert(0, str(REPO / "scripts"))

import workbook_guard  # noqa: E402
from src.db.db import get_engine  # noqa: E402

SOURCE = REPO / "resources" / "dbtemp" / "schema_with_data.json"
SCHEMA = "retail"

# See THE SNAPSHOT DATE above. Must fall inside `dim_calendar`, which the
# dimension seeder generates for 2024-01-01 .. 2027-12-31.
SNAPSHOT_DATE = date(2026, 7, 1)


# --------------------------------------------------------------------- loading


def load_tables(source: Path = SOURCE) -> dict[str, list[dict[str, Any]]]:
    """Return {table_name: [row dict, ...]}, same shape as the dimension seeder."""
    payload = json.loads(source.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]
    return tables


# ----------------------------------------------------------------- coercions
#
# The workbook states booleans three different ways and dates as text. Each
# conversion is small; getting one wrong is not, because "NO" is a non-empty
# string and therefore true to Python.


def as_bool(value: Any) -> bool:
    """`Y`/`YES`/`TRUE`/`1` are true. Everything else, including `NO`, is false."""
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1"}


def as_date(value: Any) -> date | None:
    """ISO text to a date. Blank and `None` mean "open ended", not epoch zero."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).strip()[:10]).date()


def vendor_accounts_by_short(vendors: list[dict[str, Any]]) -> dict[str, str]:
    """`Vendor E` to `V0005`.

    `replenishment_detail` names vendors by their short label while every other
    table keys them by account. Storing the label in a column declared
    `REFERENCES dim_vendor (vendor_account)` fails on all 800 rows, and storing
    it in a re-declared text column would put two spellings of one vendor in
    the database.
    """
    return {row["vendor"]: row["vendor_account"] for row in vendors}


# ------------------------------------------------------------------- builders
#
# Pure: workbook rows in, table rows out, no connection. That is what lets
# `test_retail_fact_seed.py` cover the part most likely to be wrong — the
# column mapping and the coercions — without a database.


def build_inventory(
    tables: dict[str, list[dict[str, Any]]],
    as_of: date = SNAPSHOT_DATE,
) -> list[dict[str, Any]]:
    """`ENGINE_STORE` (16,000 rows) as one day of `fact_inventory_daily`.

    `is_stockout` is the literal state, not the reorder zone. A2 counts
    stockout *risk* as `Position < ROP`, which is `Stockout` and `Low`
    together — but that is a question the builder answers from `position_qty`
    and `rop_qty`, both of which are here. A column named `is_stockout` that
    quietly meant "at risk" would be read wrongly by whoever comes next.
    """
    return [
        {
            "item_key": row["sku_id"],
            "store_key": row["store_id"],
            "cal_date": as_of,
            "on_hand_qty": row["on_hand"],
            "open_po_qty": row["open_po"],
            "position_qty": row["position"],
            "rop_qty": row["rop"],
            "max_qty": row["max"],
            "days_cover": row["dos"],
            "state": row["state"],
            "is_stockout": row["state"] == "Stockout",
            # Read, not recomputed — see the schema comment on these columns.
            "ads": row["ads"],
            "forecast_7d": row["forecast_7d"],
            "order_qty_sales": row["order_sales"],
            "order_qty_buy": row["order_buy"],
            "order_value": row["order_value"],
            "import_batch_id": None,
        }
        for row in tables["engine_store"]
    ]


def build_inventory_chain(
    tables: dict[str, list[dict[str, Any]]],
    as_of: date = SNAPSHOT_DATE,
) -> list[dict[str, Any]]:
    """`ENGINE` (800 rows) — the chain-level position, stored not derived.

    Summing `fact_inventory_daily` per item does NOT reproduce these figures,
    which is why they get their own table. Each store row rounds on its own, so
    twenty rounded quantities add up a few percent away from the chain total
    rounded once — `rop` drifts by up to 4.5% on this dataset. And the chain
    `state` is evaluated on chain inputs rather than voted across stores, which
    moves `at_risk_value` by orders of magnitude.

    Every A-sheet reconciles against these, so a derived approximation would
    put the boards a few percent away from the workbook they claim to show.
    """
    return [
        {
            "item_key": row["sku_id"],
            "cal_date": as_of,
            "ads": row["ads"],
            # A2 spec 5c: Position = On-hand + Open PO, so on-hand is the
            # difference. The workbook stores the other two.
            "on_hand_qty": row["position"] - row["open_po"],
            "open_po_qty": row["open_po"],
            "position_qty": row["position"],
            "rop_qty": row["rop"],
            "max_qty": row["max"],
            "days_cover": row["dos"],
            "state": row["state"],
            "unit_price": row["price"],
            "inventory_value": row["inv_value"],
            "at_risk_value": row["at_risk"],
            "expiry_units": row["expiry_u"],
            "order_units": row["order_units"],
            "order_value": row["order_value"],
            "weekly_gmv": row["weekly_gmv"],
            "margin_rp": row["margin_rp"],
            "funding_rp": row["funding_rp"],
            "import_batch_id": None,
        }
        for row in tables["engine"]
    ]


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def build_gmv_monthly(
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """`Time Series 24mo` — 8 verticals x 24 months of GMV.

    NOT a history, and nothing may present it as one: year two is
    byte-identical to year one in all eight verticals, so year-on-year growth
    is exactly zero by construction. It is one seasonal profile written twice.

    Stored because that profile is genuinely useful — month GMV over the series
    mean gives twelve classical seasonal indices per vertical, which is what
    Agent 1's curve is built from. Used as a shape, never as an actual.
    """
    months = {name: index for index, name in enumerate(_MONTHS)}
    rows = []
    for row in tables["time_series_24mo"]:
        # "Jan-Y1" -> month 0 of year 1.
        label = str(row["month"]).strip()
        name, _, year = label.partition("-Y")
        rows.append(
            {
                "vertical_id": row["vertical_id"],
                "year_index": int(year),
                "month_index": months[name[:3]],
                "gmv": row["gmv"],
                "import_batch_id": None,
            }
        )
    return rows


def build_agent_kpi_reference(
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """The A-sheets' own KPI rows, long-format, as reconciliation anchors.

    Every agent sheet states its headline figures per vertical, and those are
    what each builder is checked against. Long format rather than one wide
    table per agent so agents 4 to 9 need no schema change to join in.

    Keyed by `vertical_id`, resolved from the sheets' `vertical_label` — the
    A-sheets label two verticals differently from the Verticals sheet
    ("General Merch" against "Department Store"), which is exactly why
    `dim_vertical` carries `dashboard_label`.
    """
    by_label = {
        row["dashboard_label"]: row["vertical_id"] for row in tables["verticals"]
    }

    sheets = {
        "retail.demand_forecasting": (
            "a1_demand_forecasting",
            ("forecast_7d", "accuracy_pct", "trend_pct", "stockout_risk_skus",
             "trending_skus", "seasonality_idx"),
        ),
        "retail.inventory_risk": (
            "a2_inventory_risk",
            ("stockout_risk_skus", "overstock_skus", "expiry_units",
             "inventory_value", "at_risk_value", "avg_dos"),
        ),
        "retail.replenishment": (
            "a3_replenishment",
            ("skus_to_reorder", "order_units", "order_value", "fill_rate_pct",
             "avg_cover_d"),
        ),
        "retail.promotion_effectiveness": (
            "a4_promotion",
            ("active_promo_skus", "uplift_pct", "incremental_margin", "roi_x",
             "cannib_pct", "funding_pct"),
        ),
        # A6 carries ONE metric, not the six its sheet has. A prior audit
        # (RC-2) found `delist_candidates`, `grow_candidates`, `avg_gmroi`,
        # `tail_share_pct` and `capital_freed` in B:F to be pasted values
        # rather than formulas -- they never recomputed, and the board derives
        # all five from the item rows instead. `contribution_day` is the one
        # column that audit did not flag, and it reconciles exactly, so it is
        # the only one worth storing as a reconciliation anchor. Seeding the
        # other five would put figures in the warehouse that nothing should
        # ever compare against.
        "retail.assortment_optimization": (
            "a6_assortment",
            # Stored under the name the board reads it by, not the name the
            # sheet spells it. Every other entry here happens to agree on both;
            # this one does not, and the alias belongs at the point of write so
            # exactly one spelling ever reaches the warehouse.
            (("contribution_day", "contribution_per_day"),),
        ),
    }

    rows: list[dict[str, Any]] = []
    unresolved: set[str] = set()
    for agent_id, (table, metrics) in sheets.items():
        for row in tables.get(table, []):
            vertical_id = by_label.get(row["vertical_label"])
            if vertical_id is None:
                unresolved.add(row["vertical_label"])
                continue
            for metric in metrics:
                # A metric is either a column name that doubles as the stored
                # name, or an explicit (column, stored_name) pair.
                column, stored = metric if isinstance(metric, tuple) else (metric, metric)
                rows.append(
                    {
                        "agent_id": agent_id,
                        "vertical_id": vertical_id,
                        "metric": stored,
                        "value": row[column],
                        "import_batch_id": None,
                    }
                )

    if unresolved:
        raise ValueError(
            f"agent sheets name verticals dim_vertical does not: {sorted(unresolved)}"
        )
    return rows


def build_assortment(
    tables: dict[str, list[dict[str, Any]]],
    as_of: date = SNAPSHOT_DATE,
) -> list[dict[str, Any]]:
    """Which items are carried in which stores, from the pairs ENGINE_STORE has.

    16,000 rows out of a possible 128,000: each SKU is ranged in 20 of the 160
    stores, and that selection is itself the assortment. `valid_to` is left
    open because the workbook states no end.
    """
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for row in tables["engine_store"]:
        pair = (row["sku_id"], row["store_id"])
        if pair in seen:
            continue
        seen.add(pair)
        rows.append(
            {
                "item_key": pair[0],
                "store_key": pair[1],
                "valid_from": as_of,
                "valid_to": None,
            }
        )
    return rows


def build_trade_agreements(
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """2,400 vendor quotes: every item priced by every vendor that carries it."""
    return [
        {
            "item_key": row["item"],
            "vendor_account": row["vendor_account"],
            "unit_price": row["unit_price"],
            "currency": row["currency"],
            "min_qty_break": row["min_qty_break"],
            "lead_time_days": row["lead_time_d"],
            "discount_pct": row["discount_pct"],
            "valid_from": as_date(row["valid_from"]),
            "valid_to": as_date(row["valid_to"]),
            "is_designated": as_bool(row["designated"]),
            "import_batch_id": None,
        }
        for row in tables["trade_agreements"]
    ]


def build_replenishment(
    tables: dict[str, list[dict[str, Any]]],
    as_of: date = SNAPSHOT_DATE,
) -> list[dict[str, Any]]:
    """800 proposed orders, with both vendors resolved to accounts."""
    account = vendor_accounts_by_short(tables["vendors"])

    return [
        {
            "item_key": row["item"],
            "as_of_date": as_of,
            "qty_on_hand": row["qty_on_hand"],
            "open_po_qty": row["open_po"],
            "demand_per_day": row["demand_day"],
            "rop_qty": row["rop"],
            "max_qty": row["max"],
            "is_reorder": as_bool(row["reorder"]),
            "order_qty_sales": row["order_qty_sales"],
            "order_qty_buy": row["order_qty_buy"],
            "buy_uom": row["buy_uom"],
            "designated_vendor": account[row["designated_vendor"]],
            "unit_price_ta": row["unit_price_ta"],
            "amount": row["amount"],
            "best_price_vendor": account[row["best_price_vendor"]],
            "best_price": row["best_price"],
            "saving_vs_designated": row["saving_vs_designated"],
            "import_batch_id": None,
        }
        for row in tables["replenishment_detail"]
    ]


def build_promotion_detail(
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """48 campaign rows from the Promotion & Discount Detail sheet.

    Each row is one planned discount construct with its D365 mapping, the
    supplier funding offset, the planned uplift and the pre-buy units A3 needs
    to secure before valid-from. `vertical_label` is kept verbatim — the board
    resolves it to `vertical_id` via `dim_vertical.dashboard_label`, the same
    indirection `agent_kpi_reference` uses, because two verticals are labelled
    differently on the A-sheets than on the Verticals sheet.
    """
    return [
        {
            "promo_id": row["promo_id"],
            "promo_name": row["promo_name"],
            "discount_type": row["discount_type"],
            "scope": row["scope"],
            "vertical_label": row["vertical_label"],
            "target_category": row["target_category"],
            "season": row["season"],
            "peak_month": row["peak_month"],
            "mechanism": row["mechanism"],
            "discount_pct": row["discount_pct"],
            "value_rule": row["value_rule"],
            "min_qty_threshold": row["min_qty_threshold"],
            "supplier_funding_pct": row["supplier_funding_pct"],
            "expected_uplift_pct": row["expected_uplift_pct"],
            "pre_buy_uplift_units": row["pre_buy_uplift_units"],
            "valid_from": as_date(row["valid_from"]),
            "valid_to": as_date(row["valid_to"]),
            "d365_construct": row["d365_construct"],
            "source_row": row["source_row"],
        }
        for row in tables["promotion_discount_detail"]
    ]


def build_promotion_vertical_kpi(
    tables: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """The A4 Promotion sheet: six promo-effectiveness KPIs per vertical.

    These are the reconciliation anchors every A4 headline ties out against, the
    same role the A1/A2/A3 sheets play for their boards. Kept as a standalone
    table so the board can read the wide shape directly; `agent_kpi_reference`
    carries the same figures long-format for the snapshot's `reference_by_vertical`.
    """
    return [
        {
            "vertical_label": row["vertical_label"],
            "active_promo_skus": row["active_promo_skus"],
            "uplift_pct": row["uplift_pct"],
            "incremental_margin": row["incremental_margin"],
            "roi_x": row["roi_x"],
            "cannib_pct": row["cannib_pct"],
            "funding_pct": row["funding_pct"],
        }
        for row in tables["a4_promotion"]
    ]


# -------------------------------------------------------------------- writing


def replace_all(
    connection: Any,
    table: str,
    rows: list[dict[str, Any]],
    chunk: int = 2000,
) -> int:
    """Delete every row, then bulk-insert the fresh set.

    This is a full re-import from the workbook, not an incremental sync, so a
    per-row `MERGE` (Azure SQL's `ON CONFLICT` equivalent) buys nothing but a
    lookup+branch per row and a round trip per chunk -- both are pure waste
    against a table that is about to be entirely replaced anyway. Delete-then-
    insert inside the caller's transaction gives the same guarantee
    `formulas/repository.py` relies on: a reader never observes a partially
    rewritten table, and a failed write leaves the previous one intact.

    Chunked on the insert because pyodbc builds one parameter set per row:
    16,000 rows in a single `executemany` is a large allocation for no gain,
    and a failure in it reports nothing about which row was at fault.
    """
    connection.execute(text(f"DELETE FROM {SCHEMA}.{table}"))
    if not rows:
        return 0

    columns = list(rows[0].keys())
    quoted = ", ".join(f'"{name}"' for name in columns)
    placeholders = ", ".join(f":{name}" for name in columns)
    statement = text(
        f"INSERT INTO {SCHEMA}.{table} ({quoted}) VALUES ({placeholders})"
    )

    for start in range(0, len(rows), chunk):
        connection.execute(statement, rows[start : start + chunk])
    return len(rows)


# ---------------------------------------------------------------------- audit


def run_fingerprint(workbook_sha: str, overridden: bool) -> str:
    """Who ran this, from where, against which workbook -- as the audit metadata.

    `workbook_path` already narrows a run to a checkout, which is how the three
    machines seeding this database were told apart after the fact. It does not
    name a person or a branch, and on the day two workbooks took turns in the
    warehouse that was the missing half: the times were recoverable from Query
    Store, the "who" was not recorded anywhere at all.

    `overridden` matters most of all. A run that skipped the workbook check is
    the one most worth finding later, so it is written down rather than merely
    printed to a terminal nobody kept.
    """
    def git(*args: str) -> str | None:
        try:
            done = subprocess.run(
                ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() or None if done.returncode == 0 else None

    return json.dumps(
        {
            "host": socket.gethostname(),
            "os_user": getpass.getuser(),
            "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_commit": git("rev-parse", "--short", "HEAD"),
            "workbook_sha256": workbook_sha or None,
            "workbook_check_overridden": overridden,
        }
    )


def open_batch(engine: Any, metadata: str, total_sheets: int) -> int:
    """Record the run as STARTED and return its id, in its own transaction.

    STARTED rather than any word of one's choosing: the table carries
    CK_audit_import_batches_status, which admits only STARTED, COMPLETED,
    FAILED and CANCELLED.

    Deliberately committed before the load rather than inside it. The load is
    one transaction so a reader never sees a half-rewritten table; if the audit
    row rode along, a failed seed would roll its own record away and leave no
    trace that anything was attempted. A crashed run is exactly the one worth
    finding.
    """
    with engine.begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO audit.import_batches (
                    agent_name, workbook_name, workbook_version, workbook_path,
                    import_status, imported_by, total_sheets, metadata
                )
                OUTPUT INSERTED.id
                VALUES (
                    'retail_facts_seed', :workbook_name, 'v8.2', :workbook_path,
                    'STARTED', 'seed_retail_facts_from_json.py', :total_sheets,
                    :metadata
                )
                """
            ),
            {
                "workbook_name": SOURCE.name,
                "workbook_path": str(SOURCE),
                "total_sheets": total_sheets,
                "metadata": metadata,
            },
        ).scalar_one()


def close_batch(
    engine: Any,
    batch_id: int,
    status: str,
    total_rows: int,
    error: str | None = None,
) -> None:
    """Stamp the run COMPLETED or FAILED. Never raises over the original error."""
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE audit.import_batches
                       SET import_status = :status,
                           completed_at  = CURRENT_TIMESTAMP,
                           total_rows    = :total_rows,
                           error_message = :error
                     WHERE id = :id
                    """
                ),
                {
                    "status": status,
                    "total_rows": total_rows,
                    # The column is narrower than a traceback, and the first
                    # line is the part that names the failure anyway.
                    "error": (error or "")[:1000] or None,
                    "id": batch_id,
                },
            )
    except Exception as closing:  # noqa: BLE001
        # A seed that worked must not be reported as broken because its
        # bookkeeping could not be written.
        print(f"WARN  could not close import batch {batch_id}: {closing}")


def dimension_counts(connection: Any) -> dict[str, int]:
    return {
        name: connection.execute(
            text(f"SELECT count(*) FROM {SCHEMA}.{name}")
        ).scalar_one()
        for name in ("dim_item", "dim_store", "dim_vendor", "dim_calendar")
    }


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL  source not found: {SOURCE}")
        print("      run scripts/extract_workbook_schema.py first")
        return 1

    # Before anything is read into memory, let alone written: this runs in
    # whichever checkout invoked it, and a stale one holds a different
    # workbook's figures under the same file name.
    workbook_sha, overridden = workbook_guard.check(SOURCE)

    tables = load_tables()
    required = (
        "engine",
        "engine_store",
        "trade_agreements",
        "replenishment_detail",
        "vendors",
        "verticals",
        "time_series_24mo",
        "a1_demand_forecasting",
        "a2_inventory_risk",
        "a3_replenishment",
        "a4_promotion",
        "promotion_discount_detail",
    )
    missing = [name for name in required if name not in tables]
    if missing:
        print(f"FAIL  source is missing tables: {', '.join(missing)}")
        return 1

    engine = get_engine()

    with engine.connect() as connection:
        counts = dimension_counts(connection)
    empty = [name for name, count in counts.items() if count == 0]
    if empty:
        print(f"FAIL  dimensions are empty: {', '.join(empty)}")
        print("      run scripts/seed_retail_dims_from_json.py first")
        return 1

    # The snapshot date has to exist in dim_calendar or every inventory row
    # fails its foreign key — better to say so now than 16,000 rows in.
    with engine.connect() as connection:
        known_day = connection.execute(
            text(f"SELECT 1 FROM {SCHEMA}.dim_calendar WHERE cal_date = :day"),
            {"day": SNAPSHOT_DATE},
        ).first()
    if not known_day:
        print(f"FAIL  {SNAPSHOT_DATE} is not in {SCHEMA}.dim_calendar")
        print("      widen CALENDAR_START/END in the dimension seeder, or move")
        print("      SNAPSHOT_DATE in this one")
        return 1

    loads = (
        ("assortment", build_assortment(tables)),
        ("fact_inventory_daily", build_inventory(tables)),
        ("fact_inventory_chain_daily", build_inventory_chain(tables)),
        ("trade_agreement", build_trade_agreements(tables)),
        ("replenishment_proposal", build_replenishment(tables)),
        ("fact_gmv_monthly", build_gmv_monthly(tables)),
        ("agent_kpi_reference", build_agent_kpi_reference(tables)),
        ("promotion_detail", build_promotion_detail(tables)),
        ("promotion_vertical_kpi", build_promotion_vertical_kpi(tables)),
    )

    batch_id = open_batch(
        engine, run_fingerprint(workbook_sha, overridden), len(loads)
    )
    written_total = 0

    try:
        with engine.begin() as connection:
            for table, rows in loads:
                # Stamped here rather than in the nine builders, so the id has
                # one home and a new builder cannot forget it. The key is
                # already present in every row, so column order does not move.
                for row in rows:
                    row["import_batch_id"] = batch_id
                written = replace_all(connection, table, rows)
                written_total += written
                print(f"  ok  {table:24} {written:>6} rows")
    except Exception as error:  # noqa: BLE001
        close_batch(engine, batch_id, "FAILED", written_total, str(error))
        raise

    close_batch(engine, batch_id, "COMPLETED", written_total)

    print(f"\nImport batch {batch_id}")
    print(f"Snapshot date: {SNAPSHOT_DATE}")
    print("fact_sales_daily left empty on purpose — see the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
