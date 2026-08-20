"""Generate `resources/inbound_store_sku_16w_v1.csv` -- a 16-week arrival schedule.

Run it yourself:

    ./.venv/Scripts/python.exe scripts/generate_synthetic_inbound_16w.py

Input:  resources/demand_store_sku_32w_poc_v1.csv   (forecast_w1..forecast_w16)
        resources/dbtemp/schema_with_data.json      (lead_d, pack_factor)
Output: resources/inbound_store_sku_16w_v1.csv
        resources/inbound_store_sku_16w_v1_manifest.json

WHY THIS TABLE EXISTS
---------------------
No table in this warehouse records WHEN an inbound order arrives. The workbook
stores how much is on order per SKU (`open_po_qty`) and never a date, which is
stated outright in `REQUIREMENT_NOTE` and in A3's own chart comment. The
requirement chart therefore had to place every open PO on its SKU's lead day --
2, 4 or 7 -- and since the chart steps weekly, every route lands inside the
first week and cover is a flat line from W+1 onward. Cumulative demand rising
against a flat stock diverges without bound, which is why that board always
read "Cover runs out at W+1" no matter what was in scope.

This file invents the missing arrival calendar, and says so. It is synthetic
and labelled synthetic everywhere it surfaces.

HOW THE SCHEDULE IS BUILT
-------------------------
Demand-anchored: what arrives over the horizon is what the horizon is forecast
to sell, so cover tracks requirement instead of falling behind it. That is the
whole point -- an inbound stream that under-delivers by construction would
reproduce the runaway gap this replaces.

Batched, not trickled. Each route receives on its own cadence:

    direct (lead 2d)  every week      -- fresh, store-direct
    flow   (lead 4d)  every 2 weeks   -- DC pick and pass
    cross  (lead 7d)  every 3 weeks   -- DC consolidation across vendors

A delivery covers demand from its own week until the next one, rounded to
whole cases (`pack_factor`) because a purchase order buys cases, not units.

THE PHASE IS SHARED WITHIN A ROUTE, AND THAT IS DELIBERATE
----------------------------------------------------------
Every SKU on a route receives in the same weeks. Staggering the phase per SKU
would be equally defensible in isolation, but 16,000 independently-phased rows
average each other out completely: the chain-level cover line would come back
smooth and the chart would show a flat line again, which is the defect this is
meant to fix. Synchronising by route is also the more realistic of the two --
a DC consolidation run ships on a fixed calendar, it does not re-randomise per
item. Three routes on three cadences give three overlapping rhythms.

There is no random component anywhere in this generator. The schedule is a
function of the demand curve and the route, so a rerun reproduces the file
byte for byte and the manifest records no seed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

DEMAND_CSV = REPO / "resources" / "demand_store_sku_32w_poc_v1.csv"
WORKBOOK = REPO / "resources" / "dbtemp" / "schema_with_data.json"
TARGET_CSV = REPO / "resources" / "inbound_store_sku_16w_v1.csv"
TARGET_MANIFEST = REPO / "resources" / "inbound_store_sku_16w_v1_manifest.json"

GENERATION_NAME = "inbound_store_sku_16w_v1"
GENERATOR_VERSION = "inbound-store-sku-16w-generator-v1.0.0"

WEEKS = 16
FORECAST_COLUMNS = [f"forecast_w{n}" for n in range(1, WEEKS + 1)]
ARRIVAL_COLUMNS = [f"arrival_w{n}" for n in range(1, WEEKS + 1)]
COLUMNS = ["sku_id", "store_id", "route"] + ARRIVAL_COLUMNS

# Route selection is `route_for` from the dashboards, restated: the first route
# whose lead time the SKU does not exceed. Cadence is this file's own addition.
ROUTE_CADENCE: tuple[tuple[str, int, int], ...] = (
    # (route id, max lead days, weeks between deliveries)
    ("direct", 2, 1),
    ("flow", 4, 2),
    ("cross", 7, 3),
)

# The two gates this generator refuses to write a file without.
RATIO_BOUNDS = (0.98, 1.02)
MIN_COVER_AMPLITUDE = 0.15


def route_and_cadence(lead_days: float) -> tuple[str, int]:
    for route, max_lead, cadence in ROUTE_CADENCE:
        if lead_days <= max_lead:
            return route, cadence
    route, _, cadence = ROUTE_CADENCE[-1]
    return route, cadence


def delivery_weeks(cadence: int) -> list[int]:
    """Weeks 1..16 this cadence receives in, counting from the first one.

    Shared by every SKU on the route -- see the module docstring on why the
    phase is not staggered.
    """
    return list(range(1, WEEKS + 1, cadence))


def load_demand() -> list[dict[str, Any]]:
    with DEMAND_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {
                "sku_id": row["sku_id"],
                "store_id": row["store_id"],
                "forecast": [float(row[column]) for column in FORECAST_COLUMNS],
            }
            for row in csv.DictReader(handle)
        ]


def load_workbook() -> tuple[dict[str, dict[str, Any]], float]:
    payload = json.loads(WORKBOOK.read_text(encoding="utf-8"))
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in payload["tables"]:
        names = [column["name"] for column in table["columns"]]
        tables[table["name"]] = [dict(zip(names, row)) for row in table["rows"]]

    sku_master = {row["sku_id"]: row for row in tables["sku_master"]}
    # Chain on-hand, the same figure `build_lines` puts on each line. Only the
    # cover-amplitude gate below uses it; nothing is written from it.
    on_hand = sum(float(row["qty_on_hand"]) for row in tables["replenishment_detail"])
    return sku_master, on_hand


def build_rows(
    demand: list[dict[str, Any]], sku_master: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for record in demand:
        sku = sku_master[record["sku_id"]]
        route, cadence = route_and_cadence(float(sku["lead_d"]))
        pack = float(sku["pack_factor"]) or 1.0
        weeks = delivery_weeks(cadence)
        forecast = record["forecast"]

        arrivals = [0.0] * WEEKS
        for position, week in enumerate(weeks):
            # This delivery carries the shelf to the next one.
            until = weeks[position + 1] if position + 1 < len(weeks) else WEEKS + 1
            need = sum(forecast[week - 1 : until - 1])
            # Whole cases. Nearest rather than always-up: rounding every one of
            # ~110,000 deliveries up would add half a case each and push total
            # inbound past the demand it is anchored to, which is the one thing
            # this schedule must not do.
            arrivals[week - 1] = round(need / pack) * pack

        rows.append(
            {
                "sku_id": record["sku_id"],
                "store_id": record["store_id"],
                "route": route,
                **{
                    column: f"{value:.6f}"
                    for column, value in zip(ARRIVAL_COLUMNS, arrivals)
                },
            }
        )
    return rows


def cover_amplitude(
    rows: list[dict[str, Any]], demand: list[dict[str, Any]], on_hand: float
) -> tuple[float, list[float]]:
    """Peak-to-trough of the chain cover line the chart will actually draw.

    Reproduces `computeRequirement`'s forward loop: cover is last week's
    leftover plus this week's arrivals, and requirement is that week's demand.
    Measured here so "the line moves" is a checked number rather than a hope.
    """
    weekly_demand = [0.0] * WEEKS
    for record in demand:
        for index, value in enumerate(record["forecast"]):
            weekly_demand[index] += value

    weekly_arrivals = [0.0] * WEEKS
    for row in rows:
        for index, column in enumerate(ARRIVAL_COLUMNS):
            weekly_arrivals[index] += float(row[column])

    cover = []
    opening = on_hand
    for index in range(WEEKS):
        value = opening + weekly_arrivals[index]
        cover.append(value)
        opening = max(0.0, value - weekly_demand[index])

    low, high = min(cover), max(cover)
    return (high / low - 1.0) if low else 0.0, cover


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for path in (DEMAND_CSV, WORKBOOK):
        if not path.exists():
            print(f"FAIL  source not found: {path}")
            return 1

    demand = load_demand()
    sku_master, on_hand = load_workbook()

    unknown = sorted({r["sku_id"] for r in demand} - set(sku_master))[:5]
    if unknown:
        print(f"FAIL  demand CSV references SKUs the workbook does not hold: {unknown}")
        return 1

    rows = build_rows(demand, sku_master)

    total_forecast = sum(sum(record["forecast"]) for record in demand)
    total_arrivals = sum(
        float(row[column]) for row in rows for column in ARRIVAL_COLUMNS
    )
    ratio = total_arrivals / total_forecast if total_forecast else 0.0
    amplitude, cover = cover_amplitude(rows, demand, on_hand)

    print(f"  ..  {len(rows):,} rows, chain on-hand {on_hand:,.0f}")
    print(f"  ..  inbound {total_arrivals:,.0f} against demand {total_forecast:,.0f}")

    # GATE 1: no creep. Total inbound must match total demand across the
    # horizon, or cover drifts away from requirement exactly as it did before.
    low, high = RATIO_BOUNDS
    if not low <= ratio <= high:
        print(f"FAIL  inbound/demand ratio {ratio:.4f} outside [{low}, {high}]")
        return 1
    print(f"  ok  inbound/demand ratio {ratio:.4f} within [{low}, {high}]")

    # GATE 2: the line moves. A schedule that averages out to a flat cover
    # curve would satisfy gate 1 and still leave the chart unreadable.
    if amplitude < MIN_COVER_AMPLITUDE:
        print(
            f"FAIL  chain cover peak-to-trough {amplitude:.1%}"
            f" below {MIN_COVER_AMPLITUDE:.0%}"
        )
        return 1
    print(f"  ok  chain cover peak-to-trough {amplitude:.1%}")

    with TARGET_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    by_route: dict[str, int] = {}
    for row in rows:
        by_route[row["route"]] = by_route.get(row["route"], 0) + 1

    manifest = {
        "generation_name": GENERATION_NAME,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "business_timezone": "Asia/Jakarta",
        "output_row_count": len(rows),
        "quantity_precision": 6,
        "input_fingerprint": fingerprint(DEMAND_CSV),
        "output_fingerprint": fingerprint(TARGET_CSV),
        "column_contract": {
            "columns": COLUMNS,
            "identifier_columns": ["sku_id", "store_id", "route"],
            "arrival_columns": ARRIVAL_COLUMNS,
            "canonical_sort": ["sku_id", "store_id"],
            "numeric_precision": 6,
        },
        "provenance": {
            "arrival_w1_to_arrival_w16": (
                "synthetic. No table in this warehouse records an inbound"
                " arrival date; this schedule is invented to supply one."
            ),
            "quantities": (
                "demand-anchored: each delivery carries forecast_w* demand from"
                " its own week until the next delivery, rounded to whole"
                " pack_factor cases."
            ),
            "timing": (
                "route cadence, phase shared within a route -- direct weekly,"
                " flow every 2 weeks, cross every 3 weeks."
            ),
            "lead_d_and_pack_factor": (
                "resources/dbtemp/schema_with_data.json sku_master"
            ),
        },
        "determinism": {
            "seed": None,
            "note": (
                "No random component. The schedule is a function of the demand"
                " curve and the SKU's route, so a rerun is byte-identical."
            ),
        },
        "plausibility": {
            "inbound_demand_ratio": ratio,
            "inbound_demand_ratio_bounds": list(RATIO_BOUNDS),
            "chain_cover_peak_to_trough": amplitude,
            "chain_cover_peak_to_trough_floor": MIN_COVER_AMPLITUDE,
            "chain_cover_by_week": cover,
            "rows_by_route": by_route,
            "cadence_weeks": {route: cadence for route, _, cadence in ROUTE_CADENCE},
            "delivery_weeks": {
                route: delivery_weeks(cadence) for route, _, cadence in ROUTE_CADENCE
            },
        },
    }
    TARGET_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    routes = ", ".join(f"{name} {count:,}" for name, count in sorted(by_route.items()))
    print(f"  ok  {routes}")
    print(f"  ok  wrote {TARGET_CSV.name} ({TARGET_CSV.stat().st_size / 1024:.1f} KB)")
    print(f"  ok  wrote {TARGET_MANIFEST.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
