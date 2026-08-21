"""Measure what changes when the boards stop reading the chain-net table.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/measure_chain_migration_delta.py
    ../.venv/Scripts/python.exe ../scripts/measure_chain_migration_delta.py --json

READ-ONLY. Opens one connection, issues nothing but SELECT, and writes nothing
anywhere. Safe to run against production at any time.

WHY THIS EXISTS. `retail.fact_inventory_chain_daily` (Excel `ENGINE`, 800 rows,
one per SKU) and `retail.fact_inventory_daily` (Excel `ENGINE_STORE`, 16,000
rows, SKU x store) are two independent loads of the same workbook, and they do
not agree: `seed_retail_facts_from_json.py` documents rounding drift up to 4.5%
on `rop`, and a `state` computed on chain inputs rather than voted across
stores. So "SKUs to reorder" is 345 read one way and 524 read the other, and
which number a board showed came down to which table its author happened to
query.

The application code has been moved onto `fact_inventory_daily` alone. This
script is the record of what that moved. It runs each metric BOTH ways against
the same snapshot in the same connection, so the pair is measured under
identical conditions and the difference is attributable to grain and nothing
else.

It stays runnable indefinitely -- the chain table was deliberately left in the
database, still seeded and still fresh -- so it doubles as a standing
reconciliation between the two grains rather than a one-shot migration report.

THE SHAPE OF THE ANSWER, stated here so a reader can check the output against
it: money is flat, counts go up. Anything linear in `ads` -- GMV, margin,
funding, contribution, forecast -- sums exactly across stores and lands within
rounding. What moves is every COUNT, because a SKU that nets out healthy across
the chain can be broken in six of its twenty stores. `at_risk_value` moves with
the counts because it is gated on `state`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pyodbc

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / "backend" / ".env"

# The workbook's only snapshot day. Both tables carry exactly this date; a
# missing filter here would average the two grains over whatever else has been
# loaded and quietly compare different populations.
SNAPSHOT_DATE = "2026-07-01"

# `Constants` B23 -- the day-of-week factors summed over a week. Forecast is
# `ads * DOW_SUM`, so it is linear in ads and must come out identical at both
# grains. It is measured anyway: if it ever moves, the ads roll-up is broken
# and every other "flat" row in this report is suspect too.
DOW_SUM = 7.45

CHAIN_FROM = (
    "retail.fact_inventory_chain_daily c "
    "JOIN retail.dim_item i ON i.item_id = c.item_key"
)
STORE_FROM = (
    "retail.fact_inventory_daily c "
    "JOIN retail.dim_item i ON i.item_id = c.item_key"
)

# f22-expiry-units, spelled once. ROUND sits INSIDE the row so the sum rounds
# per row the way the formula does; rounding only the total drifts by a few
# units per vertical, which is small enough to read as noise and wrong for a
# reason nobody would go looking for.
F22 = (
    "round(CASE WHEN i.is_perishable = 1 AND c.days_cover > i.shelf_life_days "
    "THEN c.position_qty - c.ads * i.shelf_life_days ELSE 0 END, 0)"
)

# f12-at-risk-value and f21-inventory-value at store grain. Verified against
# ENGINE_STORE's own stored `at_risk` / `inv_value` columns: 0 of 16,000 rows
# differ, which is why those columns are derived rather than loaded.
F12 = "CASE WHEN c.state <> 'Healthy' THEN c.position_qty * i.price ELSE 0 END"
F21 = "c.position_qty * i.price"


@dataclass
class Metric:
    """One number, computed both ways.

    `chain` and `store` are SELECT-list expressions rather than whole queries,
    so the same pair drives both the headline scalar and the per-vertical
    breakdown without being written twice and drifting apart.
    """

    name: str
    chain: str
    store: str
    note: str = ""
    # Money is expected flat; counts are expected to rise. Recording the
    # expectation next to the measurement is what turns a surprising number
    # into a caught defect rather than a row someone skims past.
    expect: str = ""


@dataclass
class Section:
    label: str
    metrics: list[Metric] = field(default_factory=list)


SECTIONS = [
    Section(
        "Population",
        [
            Metric("sku_count", "count(*)", "count(DISTINCT c.item_key)",
                   expect="flat"),
            Metric("row_count", "count(*)", "count(*)",
                   note="the grain change itself: 800 -> 16,000"),
        ],
    ),
    Section(
        "Counts -- these move",
        [
            Metric(
                "skus_to_reorder",
                "sum(CASE WHEN c.position_qty < c.rop_qty THEN 1 ELSE 0 END)",
                "count(DISTINCT CASE WHEN c.position_qty < c.rop_qty THEN c.item_key END)",
                note="A3 headline / A1 stockout_risk_skus",
                expect="up",
            ),
            Metric(
                "rows_below_rop",
                "sum(CASE WHEN c.position_qty < c.rop_qty THEN 1 ELSE 0 END)",
                "sum(CASE WHEN c.position_qty < c.rop_qty THEN 1 ELSE 0 END)",
                note="store-grain ROWS, not SKUs -- the number to never show as a SKU count",
            ),
            Metric(
                "stockout_skus",
                "sum(CASE WHEN c.state = 'Stockout' THEN 1 ELSE 0 END)",
                "count(DISTINCT CASE WHEN c.state = 'Stockout' THEN c.item_key END)",
                expect="up",
            ),
            Metric(
                "overstock_skus",
                "sum(CASE WHEN c.state = 'Overstock' THEN 1 ELSE 0 END)",
                "count(DISTINCT CASE WHEN c.state = 'Overstock' THEN c.item_key END)",
                expect="up",
            ),
            Metric(
                "slow_mover_skus",
                "sum(CASE WHEN c.state = 'Slow-mover' THEN 1 ELSE 0 END)",
                "count(DISTINCT CASE WHEN c.state = 'Slow-mover' THEN c.item_key END)",
                expect="up",
            ),
            Metric(
                "expiry_skus",
                "sum(CASE WHEN c.expiry_units > 0 THEN 1 ELSE 0 END)",
                f"count(DISTINCT CASE WHEN {F22} > 0 THEN c.item_key END)",
                expect="up",
            ),
        ],
    ),
    Section(
        "Money and units",
        [
            Metric(
                "at_risk_value",
                "sum(c.at_risk_value)",
                f"sum({F12})",
                note="gated on `state`, so it moves with the counts above",
                expect="up",
            ),
            Metric(
                "inventory_value",
                "sum(c.inventory_value)",
                f"sum({F21})",
                expect="flat",
            ),
            Metric("order_value", "sum(c.order_value)", "sum(c.order_value)",
                   expect="up"),
            Metric("order_units", "sum(c.order_units)", "sum(c.order_qty_sales)",
                   expect="up"),
            Metric("expiry_units", "sum(c.expiry_units)", f"sum({F22})",
                   expect="up"),
        ],
    ),
    Section(
        "Linear in ads -- these must stay flat",
        [
            Metric("ads_total", "sum(c.ads)", "sum(c.ads)", expect="flat"),
            Metric(
                "forecast_7d",
                f"sum(c.ads) * {DOW_SUM}",
                f"sum(c.ads) * {DOW_SUM}",
                note="A1 headline",
                expect="flat",
            ),
            Metric(
                "weekly_gmv",
                "sum(c.weekly_gmv)",
                "sum(c.ads * 7 * i.price)",
                expect="flat",
            ),
            Metric(
                "margin_rp",
                "sum(c.margin_rp)",
                "sum(c.ads * 7 * i.price * i.margin_pct)",
                note="A4 incremental margin base; = f15 x 7",
                expect="flat",
            ),
            Metric(
                "funding_rp",
                "sum(c.funding_rp)",
                "sum(c.ads * 7 * i.price * i.funding_pct)",
                note="dim_item.funding_pct, NEVER ENGINE_STORE's 3dp `fund`",
                expect="flat",
            ),
        ],
    ),
]

# Beyond this the two grains are telling materially different stories and the
# metric earns a per-vertical breakdown, so a reader can see which verticals
# drove it rather than being handed one blended ratio.
FLAT_BAND = 0.005


def connection_string() -> str:
    """Read the connection string out of backend/.env.

    Same reader as `scripts/apply_sql_migration.py` -- deliberately, so there
    is one way a script in here reaches the warehouse and no second spelling of
    the driver and timeout defaults to keep in step.
    """
    if not ENV.exists():
        sys.exit(f"{ENV} not found")
    value = None
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("AZURE_SQL_CONNECTIONSTRING="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not value:
        sys.exit("AZURE_SQL_CONNECTIONSTRING missing from backend/.env")
    if "driver=" not in value.lower():
        value = value.rstrip("; ") + ";Driver={ODBC Driver 18 for SQL Server}"
    if "connection timeout" not in value.lower():
        value = value.rstrip("; ") + ";Connection Timeout=90"
    return value


def scalar(cur: pyodbc.Cursor, expr: str, source: str) -> float | None:
    cur.execute(
        f"SELECT {expr} FROM {source} WHERE c.cal_date = ?",  # noqa: S608
        SNAPSHOT_DATE,
    )
    row = cur.fetchone()
    return None if row is None or row[0] is None else float(row[0])


def by_vertical(cur: pyodbc.Cursor, expr: str, source: str) -> dict[str, float]:
    cur.execute(
        f"""
        SELECT i.vertical_id, {expr}
        FROM {source}
        WHERE c.cal_date = ?
        GROUP BY i.vertical_id
        """,  # noqa: S608
        SNAPSHOT_DATE,
    )
    return {row[0]: float(row[1] or 0) for row in cur.fetchall()}


def ratio(old: float | None, new: float | None) -> float | None:
    if old is None or new is None or old == 0:
        return None
    return new / old


def direction(r: float | None) -> str:
    if r is None:
        return "?"
    if abs(r - 1.0) <= FLAT_BAND:
        return "="
    return "^" if r > 1.0 else "v"


def fmt(value: float | None) -> str:
    if value is None:
        return "-"
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.2f}"


def measure(cur: pyodbc.Cursor) -> list[dict]:
    results = []
    for section in SECTIONS:
        for metric in section.metrics:
            old = scalar(cur, metric.chain, CHAIN_FROM)
            new = scalar(cur, metric.store, STORE_FROM)
            r = ratio(old, new)
            record = {
                "section": section.label,
                "metric": metric.name,
                "note": metric.note,
                "expect": metric.expect,
                "chain": old,
                "store": new,
                "delta": None if old is None or new is None else new - old,
                "ratio": r,
                "direction": direction(r),
                "verticals": {},
            }
            # A metric that moved gets decomposed; one that did not would only
            # add eight rows of 1.000 to scroll past.
            if r is not None and abs(r - 1.0) > FLAT_BAND:
                old_v = by_vertical(cur, metric.chain, CHAIN_FROM)
                new_v = by_vertical(cur, metric.store, STORE_FROM)
                record["verticals"] = {
                    key: {
                        "chain": old_v.get(key),
                        "store": new_v.get(key),
                        "ratio": ratio(old_v.get(key), new_v.get(key)),
                    }
                    for key in sorted(set(old_v) | set(new_v))
                }
            results.append(record)
    return results


def report(results: list[dict], counts: dict[str, int]) -> None:
    print("CHAIN GRAIN RETIREMENT - MEASURED DELTA")
    print(
        f"snapshot {SNAPSHOT_DATE} - "
        f"fact_inventory_chain_daily {counts['chain']:,} rows - "
        f"fact_inventory_daily {counts['store']:,} rows"
    )
    print()

    section = None
    for row in results:
        if row["section"] != section:
            section = row["section"]
            print(f"== {section} " + "=" * max(0, 66 - len(section)))
            print(
                f"{'metric':<22}{'chain (old)':>23}{'store (new)':>23}"
                f"{'ratio':>10}{'':>4}{'expect':>8}"
            )
            print("-" * 90)

        flag = ""
        # The expectation is checked, not just printed. A row marked flat that
        # did not come out flat is the finding this whole report exists to
        # surface, and it should not depend on a reader noticing it.
        if row["expect"] == "flat" and row["direction"] != "=":
            flag = "  <-- EXPECTED FLAT"
        elif row["expect"] == "up" and row["direction"] not in ("^", "?"):
            flag = "  <-- EXPECTED TO RISE"

        r = row["ratio"]
        print(
            f"{row['metric']:<22}{fmt(row['chain']):>23}{fmt(row['store']):>23}"
            f"{('-' if r is None else f'{r:.6f}'):>10}"
            f"{row['direction']:>4}{row['expect']:>8}{flag}"
        )
        if row["note"]:
            print(f"{'':<22}{row['note']}")

        if row["verticals"]:
            movers = sorted(
                (
                    (key, val)
                    for key, val in row["verticals"].items()
                    if val["ratio"] is not None
                ),
                key=lambda pair: abs(pair[1]["ratio"] - 1.0),
                reverse=True,
            )
            print(f"{'':<4}by vertical")
            for key, val in movers:
                largest = "   <-- largest mover" if key == movers[0][0] else ""
                print(
                    f"{'':<6}{key:<6}{fmt(val['chain']):>18}"
                    f"{fmt(val['store']):>18}{val['ratio']:>10.3f}{largest}"
                )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    args = parser.parse_args()

    # Read-only throughout: autocommit so nothing opens a write transaction,
    # and every statement below is a SELECT.
    with pyodbc.connect(connection_string(), autocommit=True) as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT count(*) FROM retail.fact_inventory_chain_daily WHERE cal_date = ?",
            SNAPSHOT_DATE,
        )
        chain_rows = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM retail.fact_inventory_daily WHERE cal_date = ?",
            SNAPSHOT_DATE,
        )
        store_rows = cur.fetchone()[0]
        if not chain_rows or not store_rows:
            sys.exit(
                f"nothing to compare at {SNAPSHOT_DATE}: "
                f"chain={chain_rows}, store={store_rows}"
            )
        results = measure(cur)

    counts = {"chain": chain_rows, "store": store_rows}
    if args.json:
        print(json.dumps(
            {"snapshot": SNAPSHOT_DATE, "counts": counts, "metrics": results},
            indent=2,
        ))
    else:
        report(results, counts)


if __name__ == "__main__":
    main()
