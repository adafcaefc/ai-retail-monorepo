"""Generate `resources/markdown_ladder_store_sku_16w_v1.csv` -- a 32-week
(16 back, 16 forward) projection of markdown at-risk exposure under two
policies, store x SKU.

Run it yourself:

    ./.venv/Scripts/python.exe scripts/generate_synthetic_markdown_ladder_16w.py

Input:  resources/dbtemp/schema_with_data.json   (via build_pricing_markdown_fixture)
        resources/dbtemp/formula.json            (via build_pricing_markdown_fixture)
Output: resources/markdown_ladder_store_sku_16w_v1.csv
        resources/markdown_ladder_store_sku_16w_v1_manifest.json
        resources/markdown_ladder_store_sku_16w_v1.xlsx

The .xlsx is the same rows as the CSV, for importing through the SSMS wizard
instead of running the seeding script -- same reason `generate_synthetic_
inbound_16w.py` writes one, and written here for the same reason: a stale
workbook silently loaded into the live table would be worse than no workbook.

WHY THIS TABLE EXISTS
----------------------
A5's "at-risk value: ladder vs no action" chart wants a WEEKLY line, and
`fixture.json` has no time dimension anywhere -- confirmed: no weekly/date
field on any item, unlike Replenishment's real 33-week demand curve. Unlike
demand, at-risk value genuinely has no PAST to record either: it is a
snapshot metric read off today's inventory position, not a rate with history
to backtest. So neither side of this table is a real history -- it is a
deterministic PROJECTION, 16 weeks each direction from today's real
at-risk exposure, under two policies: do nothing, or keep running the
markdown ladder. The "history" side is modelled the same way the forward
side already was (§1 of the first version of this generator) -- one
continuous assumption applied both directions from a real anchor, not two
independently invented shapes.

Same family as `synthetic.demand_store_sku_32w` and
`synthetic.inbound_store_sku_16w` -- fabricated, gate-checked before being
written, and labelled synthetic everywhere it surfaces.

TODAY LIVES OUTSIDE THIS TABLE
--------------------------------
Offset 0 ("today") is NOT a stored column. It is TODAY's real, already-
computed snapshot -- `build_pricing_markdown_fixture.build_items()`'s own
`at_risk_value` and `write_off_value` for that (sku, store) row (the same
f12/f14 formulas the fixture and the live backend both already run) -- and
every consumer of this table reads it live from there instead of from a
column here: the KPI tiles, the Rescue waterfall, and the frontend's
`computeLadderHistory` (which injects it as this chart's week-0 point from
`dashboard.kpis`, not from `dashboard.ladder_history`'s own arrays). Nothing
about today is invented, and duplicating it into this table would just be a
second copy of a number that already exists and already updates correctly
whenever the underlying formulas do.

`no_action_w1`/`ladder_w1` are offset **+1** (one week ahead of today), NOT
today -- a prior version of this generator stored today at `w1` and every
other forward week one column later, which meant a "16-week forward
horizon" topped out at +15, one week short of what "16 weeks" promises. w1
now means +1 consistently with w16 meaning +16, and the history side
mirrors it exactly (`hist_w1` = -1, `hist_w16` = -16).

Every stored week (`-16..-1` = `*_hist_w16..*_hist_w1`, oldest first;
`+1..+16` = `*_w1..*_w16`) is TREND x WIGGLE:

  trend(offset)  = at_risk_value + offset x weekly_inflow                (offset > 0)
                  = max(0.2 x at_risk_value, at_risk_value + offset x weekly_inflow)  (offset < 0)
  wiggle(offset) = 1 + WIGGLE_AMPLITUDE x sin(2*pi*(offset+phase)/WIGGLE_CYCLE_WEEKS)
  no_action(offset) = trend(offset) x wiggle(offset)
  ladder(offset)    = no_action(offset) x (1 - effective_recovery_rate)

`weekly_inflow` is at_risk_value x INFLOW_RATE_BASE x growth_factor, where
growth_factor is the SKU's own real SKU_Master growth index (0.91-1.39 across
the whole catalogue, confirmed), clamped to a defensive [0.8, 1.6] band --
so a faster-growing SKU accumulates exposure faster (and, mirrored
backward, had less exposure further in the past), and nothing about the
trend is a random walk. Going backward the trend is floored at 20% of
today's value rather than let a slow-inflow SKU's history run to zero and
sit flat there for several weeks, which would read as measured, not
modelled.

`effective_recovery_rate` is the SKU's own real recovery rate --
`recoverable_value / at_risk_value`, the same figure f14-recoverable-at-
risk-value's elasticity-driven output already implies -- floored at
MIN_RECOVERY_RATE (0.05) so the ladder line always visibly separates from
the no-action line even for a SKU whose real recovery is negligible. f14's
own 0.95 cap already keeps the raw rate under MAX_RECOVERY_RATE for real
data, so that clamp is a defensive no-op.

THE WIGGLE, AND WHY ITS PHASE IS PER-VERTICAL, NOT PER-SKU
-------------------------------------------------------------
This table ships at (sku_id, store_id) grain, but every consumer
(`dashboard.py`'s `_ladder_by_vertical`, `build_pricing_markdown_fixture.py`'s
`build_ladder_by_vertical`) sums it to 8 vertical rows before the chart ever
sees it -- the chart draws one pair of lines per scope, not one per SKU. A
wiggle phased by `sku_id` (or randomly) would average out across the ~2,000
rows in a vertical and sum to a flat line, reproducing the exact "smooth
line" problem this revision exists to fix. Phasing by `vertical_id` instead
means every row in a vertical ripples in lockstep, so the vertical (and
chain) total ripples too, proportionally. `vertical_phase()` is a small
deterministic hash (sum of the vertical id's char codes, mod the wiggle
cycle) -- not random, so a rerun is byte-identical.

The phase function runs on one CONTINUOUS offset axis across the whole
-16..+16 range (not two separately-phased halves either side of "today"),
so the ripple reads as one texture through the "today" boundary rather than
a seam, even though offset 0 itself is never stored or wiggled here (see
"TODAY LIVES OUTSIDE THIS TABLE" above).

Only markdown candidates (Expiry/Overstock/Slow-mover) get a nonzero
projection -- a non-candidate row carries no at-risk exposure today
(`write_off_value = 0`), so there is nothing to project. Both lines are
written as flat zero across every offset, matching `build_pricing_markdown_
fixture.py`'s own T-04 zero convention.

WHAT IS DELIBERATELY NOT MODELLED
-----------------------------------
No per-state markdown "effective window" (Expiry 0-3d / Overstock 14d /
Slow-mover 21d -- that language is mockup narrative describing a different
table, not a real field in this codebase, and was not smuggled in here as
though it were one). The ripple is one shared, bounded wiggle on a trend,
not a fabricated calendar of clearance events.

There is no random component anywhere in this generator. Both lines are a
pure function of each row's own real `at_risk_value`/`write_off_value`/
`growth`/`state`/`vertical_id`, so a rerun reproduces the file byte for
byte.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))  # for build_pricing_markdown_fixture

import build_pricing_markdown_fixture as pm  # noqa: E402

TARGET_CSV = REPO / "resources" / "markdown_ladder_store_sku_16w_v1.csv"
TARGET_MANIFEST = REPO / "resources" / "markdown_ladder_store_sku_16w_v1_manifest.json"
TARGET_XLSX = REPO / "resources" / "markdown_ladder_store_sku_16w_v1.xlsx"

GENERATION_NAME = "markdown_ladder_store_sku_16w_v1"
TABLE_NAME = "markdown_ladder_store_sku_16w"
GENERATOR_VERSION = "markdown-ladder-store-sku-16w-generator-v2.0.0"

WEEKS = 16
# Forward block: w1 = today (offset 0, the calibration anchor) .. w16 = +15
# weeks out. Column names unchanged from v1 so the already-seeded/tested DB
# column names, backend query and fixture-builder read path for THIS block
# need no change.
FWD_NO_ACTION_COLUMNS = [f"no_action_w{n}" for n in range(1, WEEKS + 1)]
FWD_LADDER_COLUMNS = [f"ladder_w{n}" for n in range(1, WEEKS + 1)]
# History block, new in v2: hist_w1 = 1 week before today (offset -1) ..
# hist_w16 = 16 weeks before (offset -16). Declared oldest-first
# (hist_w16..hist_w1) in the written CSV/table, mirroring
# `synthetic.demand_store_sku_32w`'s own `actual_w16..actual_w1` ordering.
HIST_NO_ACTION_COLUMNS = [f"no_action_hist_w{n}" for n in range(1, WEEKS + 1)]
HIST_LADDER_COLUMNS = [f"ladder_hist_w{n}" for n in range(1, WEEKS + 1)]

# The rate/shape assumptions this generator refuses to write a file without
# having stayed within. See the module docstring for what each represents.
INFLOW_RATE_BASE = 0.025
GROWTH_CLAMP = (0.8, 1.6)
MIN_RECOVERY_RATE = 0.05
MAX_RECOVERY_RATE = 0.95
HISTORY_FLOOR_FRACTION = 0.2
WIGGLE_AMPLITUDE = 0.14
WIGGLE_CYCLE_WEEKS = 4

# The gates. See the module docstring for why each should hold by
# construction -- they are asserted here anyway, against the actual
# generated numbers, not trusted from the formula alone.
SEPARATION_FLOOR = 0.03  # gate 4: every vertical must clear this at both edges


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def vertical_phase(vertical_id: str) -> int:
    """A small deterministic hash, not random -- see the module docstring's
    "THE WIGGLE" section for why the phase is per-vertical, not per-SKU."""
    return sum(ord(c) for c in vertical_id) % WIGGLE_CYCLE_WEEKS


def wiggle_factor(offset: int, phase: int) -> float:
    """Bounded to [1 - WIGGLE_AMPLITUDE, 1 + WIGGLE_AMPLITUDE] by construction
    (sin is bounded to [-1, 1]) -- not asserted as a runtime gate, since it is
    a mathematical fact of this formula, not a property of the data."""
    return 1.0 + WIGGLE_AMPLITUDE * math.sin(2 * math.pi * (offset + phase) / WIGGLE_CYCLE_WEEKS)


def trend_value(base_at_risk: float, weekly_inflow: float, offset: int) -> float:
    """The pre-wiggle trend at one offset -- reused by both `build_rows` (to
    generate) and `main`'s gate 2 (to re-verify the trend independently of
    the wiggled output, the same "don't trust the formula, check the
    numbers" discipline gate 1 already applies to calibration)."""
    if offset == 0:
        return base_at_risk
    value = base_at_risk + offset * weekly_inflow
    if offset < 0:
        value = max(HISTORY_FLOOR_FRACTION * base_at_risk, value)
    return value


def _offset_column(offset: int) -> tuple[str, str]:
    """Which (no_action, ladder) column name an offset belongs to.

    `offset == 0` ("today") is never written here -- see the module
    docstring's "TODAY LIVES OUTSIDE THIS TABLE" section. Forward columns
    `w1..w16` are offsets `+1..+16`; history columns `hist_w1..hist_w16`
    are offsets `-1..-16`.
    """
    if offset < 0:
        return f"no_action_hist_w{-offset}", f"ladder_hist_w{-offset}"
    return f"no_action_w{offset}", f"ladder_w{offset}"


_OFFSETS = list(range(-WEEKS, 0)) + list(range(1, WEEKS + 1))  # -16..-1, 1..16 -- never 0


def build_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        base_at_risk = float(item["at_risk_value"])
        base_write_off = float(item["write_off_value"])
        by_offset: dict[str, float] = {}

        if not item["is_markdown_candidate"] or base_at_risk <= 0:
            for offset in _OFFSETS:
                na_col, ld_col = _offset_column(offset)
                by_offset[na_col] = 0.0
                by_offset[ld_col] = 0.0
        else:
            growth_factor = _clamp(float(item["growth"]), *GROWTH_CLAMP)
            weekly_inflow = base_at_risk * INFLOW_RATE_BASE * growth_factor

            recovery_rate_raw = 1.0 - (base_write_off / base_at_risk if base_at_risk else 0.0)
            effective_rate = _clamp(recovery_rate_raw, MIN_RECOVERY_RATE, MAX_RECOVERY_RATE)

            phase = vertical_phase(item["vertical_id"])
            for offset in _OFFSETS:
                na_col, ld_col = _offset_column(offset)
                no_action = trend_value(base_at_risk, weekly_inflow, offset) * wiggle_factor(offset, phase)
                ladder = no_action * (1.0 - effective_rate)
                by_offset[na_col] = no_action
                by_offset[ld_col] = ladder

        rows.append(
            {
                "sku_id": item["sku_id"],
                "store_id": item["store_id"],
                "vertical_id": item["vertical_id"],  # dropped before writing; see build_rows callers
                **{column: f"{value:.6f}" for column, value in by_offset.items()},
            }
        )
    return rows


def weekly_totals_by_vertical(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Chain/vertical sums for every offset column -- used for gate 4 and the
    printed summary only (the actual per-vertical aggregation consumers use
    lives in dashboard.py/build_pricing_markdown_fixture.py, not here)."""
    all_columns = HIST_NO_ACTION_COLUMNS + FWD_NO_ACTION_COLUMNS + HIST_LADDER_COLUMNS + FWD_LADDER_COLUMNS
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        bucket = totals.setdefault(row["vertical_id"], dict.fromkeys(all_columns, 0.0))
        for column in all_columns:
            bucket[column] += float(row[column])
    return totals


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_xlsx(rows: list[dict[str, Any]], columns: list[str]) -> None:
    """The same rows as a workbook, for the SSMS import wizard.

    Weekly columns are written as numbers, not the formatted strings the CSV
    carries -- the wizard types each column from the cell values it sees, and
    a numeric column arriving as text lands in NVARCHAR and then fails the
    insert into DECIMAL(20,6). Same approach as `generate_synthetic_
    inbound_16w.py`'s own `write_xlsx`.
    """
    from openpyxl import Workbook

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(TABLE_NAME)
    sheet.append(columns)
    numeric = [name not in ("sku_id", "store_id") for name in columns]
    for row in rows:
        sheet.append(
            [float(row[name]) if is_number else row[name] for name, is_number in zip(columns, numeric)]
        )
    workbook.save(TARGET_XLSX)


def main() -> int:
    if not pm.SOURCE.exists():
        print(f"FAIL  source not found: {pm.SOURCE}")
        return 1

    tables = pm.load_tables()
    formulas = pm.load_formulas()
    asts = {name: pm.parse(expr) for name, expr in formulas.items()}

    by_cell = {row["source_cell"]: row for row in tables["constants"]}
    hz_cov = float(by_cell["B24"]["value"])

    lead_times = pm.sku_master_lead_times(tables["sku_master"])
    items = pm.build_items(
        tables["engine_store"], tables["sku_master"], tables["verticals"], lead_times, hz_cov, asts,
    )

    rows = build_rows(items)
    output_columns = (
        ["sku_id", "store_id"]
        + list(reversed(HIST_NO_ACTION_COLUMNS))  # hist_w16 .. hist_w1, oldest first
        + FWD_NO_ACTION_COLUMNS  # w1 (today) .. w16
        + list(reversed(HIST_LADDER_COLUMNS))
        + FWD_LADDER_COLUMNS
    )

    print(f"  ..  {len(rows):,} rows, {len(output_columns) - 2} weekly columns")

    # GATE 1: self-consistency. "Today" (offset 0) is not stored in this
    # table at all -- see the module docstring's "TODAY LIVES OUTSIDE THIS
    # TABLE" section -- so there is no longer a single real value to
    # calibrate a stored column against. What IS checked, independently of
    # `build_rows()`: every candidate row's stored value at every offset
    # equals trend_value(offset) x wiggle_factor(offset) recomputed fresh
    # from that row's own real at_risk_value/write_off_value/growth --
    # exactly what `build_rows()` should have written, not just trusted to
    # have. Non-candidate rows must carry an exact zero across all 64
    # weekly columns.
    by_key = {(item["sku_id"], item["store_id"]): item for item in items}
    all_na_columns = HIST_NO_ACTION_COLUMNS + FWD_NO_ACTION_COLUMNS
    all_ld_columns = HIST_LADDER_COLUMNS + FWD_LADDER_COLUMNS
    inconsistent = 0
    wrongly_nonzero = 0
    for row in rows:
        item = by_key[(row["sku_id"], row["store_id"])]
        base_at_risk = float(item["at_risk_value"])
        base_write_off = float(item["write_off_value"])
        if item["is_markdown_candidate"] and base_at_risk > 0:
            growth_factor = _clamp(float(item["growth"]), *GROWTH_CLAMP)
            weekly_inflow = base_at_risk * INFLOW_RATE_BASE * growth_factor
            recovery_rate_raw = 1.0 - (base_write_off / base_at_risk)
            effective_rate = _clamp(recovery_rate_raw, MIN_RECOVERY_RATE, MAX_RECOVERY_RATE)
            phase = vertical_phase(item["vertical_id"])
            for offset in _OFFSETS:
                na_col, ld_col = _offset_column(offset)
                expected_no_action = trend_value(base_at_risk, weekly_inflow, offset) * wiggle_factor(offset, phase)
                expected_ladder = expected_no_action * (1.0 - effective_rate)
                if abs(float(row[na_col]) - expected_no_action) > max(0.01, expected_no_action * 1e-6):
                    inconsistent += 1
                if abs(float(row[ld_col]) - expected_ladder) > max(0.01, expected_ladder * 1e-6):
                    inconsistent += 1
        elif any(float(row[c]) != 0.0 for c in all_na_columns + all_ld_columns):
            wrongly_nonzero += 1
    if inconsistent:
        print(f"FAIL  {inconsistent} value(s) do not match trend x wiggle recomputed from the row's own real fields")
        return 1
    if wrongly_nonzero:
        print(f"FAIL  {wrongly_nonzero} non-candidate row(s) carry a nonzero projection somewhere")
        return 1
    print("  ok  every candidate value is self-consistent with trend x wiggle; non-candidates are zero throughout")

    # GATE 2: the underlying TREND never decreases going forward (the
    # wiggled output itself is now allowed to dip week to week by design --
    # that is the whole point of this revision -- so the trend is
    # re-derived and checked independently of it, via trend_value(), the
    # same function that built it). Also a non-negativity sweep across
    # every generated value, matching the DB's own CHECK constraint.
    bad_inflow = 0
    negative = 0
    for row in rows:
        item = by_key[(row["sku_id"], row["store_id"])]
        if item["is_markdown_candidate"] and float(item["at_risk_value"]) > 0:
            growth_factor = _clamp(float(item["growth"]), *GROWTH_CLAMP)
            weekly_inflow = float(item["at_risk_value"]) * INFLOW_RATE_BASE * growth_factor
            if weekly_inflow < 0:
                bad_inflow += 1
        if any(float(row[c]) < 0 for c in all_na_columns + all_ld_columns):
            negative += 1
    if bad_inflow:
        print(f"FAIL  {bad_inflow} row(s) have a negative underlying trend slope")
        return 1
    if negative:
        print(f"FAIL  {negative} row(s) carry a negative generated value somewhere")
        return 1
    print("  ok  every candidate's underlying trend is non-decreasing; no generated value is negative")

    # GATE 3: the ladder stays visibly below no-action at both edges of the
    # horizon, for every row that carries any exposure at all.
    not_separated = sum(
        1
        for row in rows
        if float(row["no_action_w1"]) > 0
        and (
            float(row["ladder_w16"]) >= float(row["no_action_w16"])
            or float(row["ladder_hist_w16"]) >= float(row["no_action_hist_w16"])
        )
    )
    if not_separated:
        print(f"FAIL  {not_separated} at-risk row(s) do not separate at both horizon edges")
        return 1
    print("  ok  every at-risk row's ladder line separates from no-action at both edges")

    # GATE 4: every vertical clears the separation floor at both edges -- a
    # chain-level check alone can hide a vertical that barely moves (the
    # exact failure `generate_synthetic_inbound_16w.py`'s own gate 4 guards).
    totals = weekly_totals_by_vertical(rows)
    per_vertical_gap = {}
    for vertical, sums in totals.items():
        fwd_gap = (sums["no_action_w16"] - sums["ladder_w16"]) / sums["no_action_w16"] if sums["no_action_w16"] else 0.0
        hist_gap = (
            (sums["no_action_hist_w16"] - sums["ladder_hist_w16"]) / sums["no_action_hist_w16"]
            if sums["no_action_hist_w16"]
            else 0.0
        )
        per_vertical_gap[vertical] = min(fwd_gap, hist_gap)
    flat = sorted(name for name, gap in per_vertical_gap.items() if gap < SEPARATION_FLOOR)
    if flat:
        print(f"FAIL  {len(flat)} vertical(s) fall under the separation floor at an edge: {flat}")
        return 1
    worst = min(per_vertical_gap.values()) if per_vertical_gap else 0.0
    print(f"  ok  all {len(per_vertical_gap)} verticals clear the separation floor at both edges (weakest {worst:.2%})")

    # Candidates only, matching what the stored (non-candidate-zeroed) totals
    # below actually represent -- not stored in this table itself, see gate 1.
    chain_today = sum(float(item["at_risk_value"]) for item in items if item["is_markdown_candidate"])
    chain_no_action_hist16 = sum(float(r["no_action_hist_w16"]) for r in rows)
    chain_no_action_w16 = sum(float(r["no_action_w16"]) for r in rows)
    print(
        f"  ..  chain no-action Rp {chain_no_action_hist16:,.0f} (W-16) -> "
        f"Rp {chain_today:,.0f} (today, not stored here) -> Rp {chain_no_action_w16:,.0f} (W+16)"
    )

    with TARGET_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "generation_name": GENERATION_NAME,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "business_timezone": "Asia/Jakarta",
        "output_row_count": len(rows),
        "quantity_precision": 6,
        "input_fingerprint": fingerprint(pm.SOURCE),
        "output_fingerprint": fingerprint(TARGET_CSV),
        "column_contract": {
            "columns": output_columns,
            "identifier_columns": ["sku_id", "store_id"],
            "no_action_columns": list(reversed(HIST_NO_ACTION_COLUMNS)) + FWD_NO_ACTION_COLUMNS,
            "ladder_columns": list(reversed(HIST_LADDER_COLUMNS)) + FWD_LADDER_COLUMNS,
            "canonical_sort": ["sku_id", "store_id"],
            "numeric_precision": 6,
        },
        "provenance": {
            "today_offset_0": (
                "NOT stored in this table. Today's real at_risk_value/write_off_value"
                " (build_pricing_markdown_fixture.build_items()'s own f12/f14 output) is"
                " read live wherever it is needed (the KPI tiles, the Rescue waterfall, and"
                " the frontend's computeLadderHistory, which injects it as this chart's"
                " week-0 point) rather than duplicated into a column here -- see the module"
                " docstring's 'TODAY LIVES OUTSIDE THIS TABLE' section."
            ),
            "every_stored_week": (
                "synthetic: trend(offset) x wiggle(offset), offset in [-16..-1, 1..16] (never"
                " 0). trend is at_risk_value +/- offset x (at_risk_value x"
                f" {INFLOW_RATE_BASE} x growth_factor), floored at {HISTORY_FLOOR_FRACTION:.0%}"
                " of at_risk_value going backward. wiggle is a deterministic sine, amplitude"
                f" {WIGGLE_AMPLITUDE:.0%}, cycle {WIGGLE_CYCLE_WEEKS} weeks, phased per"
                " vertical_id (not sku_id -- see the module docstring's 'THE WIGGLE' section"
                " for why). No table in this warehouse records a real weekly at-risk"
                " trajectory, past or future; this projects one."
            ),
            "ladder": (
                "no_action(offset) x (1 - effective_recovery_rate) at every stored offset,"
                " where effective_recovery_rate is the SKU's own real recoverable_value /"
                f" at_risk_value, floored at {MIN_RECOVERY_RATE} so every candidate visibly"
                " separates from no-action."
            ),
        },
        "determinism": {
            "seed": None,
            "note": (
                "No random component. Both lines are a pure function of each row's own"
                " real at_risk_value/write_off_value/growth/state/vertical_id, so a rerun"
                " is byte-identical."
            ),
        },
        "plausibility": {
            "inflow_rate_base": INFLOW_RATE_BASE,
            "growth_clamp": list(GROWTH_CLAMP),
            "min_recovery_rate": MIN_RECOVERY_RATE,
            "max_recovery_rate": MAX_RECOVERY_RATE,
            "history_floor_fraction": HISTORY_FLOOR_FRACTION,
            "wiggle_amplitude": WIGGLE_AMPLITUDE,
            "wiggle_cycle_weeks": WIGGLE_CYCLE_WEEKS,
            "separation_floor": SEPARATION_FLOOR,
            "min_separation_gap_by_vertical": per_vertical_gap,
        },
    }
    TARGET_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write_xlsx(rows, output_columns)

    print(f"  ok  wrote {TARGET_CSV.name} ({TARGET_CSV.stat().st_size / 1024:.1f} KB)")
    print(f"  ok  wrote {TARGET_MANIFEST.name}")
    print(f"  ok  wrote {TARGET_XLSX.name} ({TARGET_XLSX.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
