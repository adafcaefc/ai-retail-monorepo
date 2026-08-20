"""Reads the Retail boards share: dimensions, filter options, and the rules.

WHAT THE BACKEND RETURNS, AND WHY IT IS NOT A FINISHED DASHBOARD
---------------------------------------------------------------
These builders return rows, not totals. The aggregation that turns 800 items
into KPI tiles, state charts and a risk register stays in
`frontend/src/agents/retail/*/data/selectors.js`, which has a test suite behind
it and is the only implementation of it anywhere.

Porting that to Python would create a second implementation of the same
arithmetic, which then has to be kept in step with the first forever. This
project spent its whole first phase removing exactly that duplication for
business rules — they live once, in `retail.formula`, read by both languages
and by the agents. Aggregation deserves the same treatment.

The consequence is worth stating plainly: because both paths run the same
selectors over the same rows, moving a board from its fixture to this API
cannot change a number on screen. `test_retail_dashboard_builders.py` asserts
that by comparing this payload to the checked-in fixture field by field.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.db.db import get_engine
from src.llm.agents.common.dashboard_scope import DashboardScope

SCHEMA = "retail"

# The workbook's own snapshot day. Written by `seed_retail_facts_from_json.py`;
# read here so a board never silently mixes two loads.
SNAPSHOT_DATE = "2026-07-01"

SOURCE_WORKBOOK = "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"

# Severity order, worst first. Shared because A2 ranks by it and A1 and A3 both
# describe rows with it.
STATE_ORDER: tuple[str, ...] = (
    "Stockout",
    "Low",
    "Expiry",
    "Overstock",
    "Slow-mover",
    "Healthy",
)

# Which agent owns a row, by state. NOT a stand-in for "below the reorder
# point" -- it used to be, because `f07` tested Stockout and Low before Expiry,
# so every below-ROP row landed in one of them. Expiry is now tested first, so
# 199 of the 16,000 store rows are perishable stock that is both below ROP and
# past its shelf life, and they read "Expiry". Routing them to markdown instead
# of replenishment is the point: reordering stock that is already spoiling is
# the behaviour the priority change set out to stop.
#
# Anything that needs "below the reorder point" must compare position to ROP
# directly (`position_qty < rop_qty`), which is measured rather than labelled
# and survives a future reordering of the state chain.
REPLENISH_STATES = frozenset({"Stockout", "Low"})

# What the route can actually narrow in SQL. The remaining scope fields are
# applied by the selectors over the rows returned here, so an API caller that
# is not the board sees them reported in `ignored_filters` — which is the truth
# for that caller.
SUPPORTED_FILTERS: frozenset[str] = frozenset({"legal_entity_id", "category_group"})


def _catalogue() -> dict[str, str]:
    """The whole catalogue, keyed by id — the same rules the browser evaluates.

    Reads `retail.formula`, which is also what the Formula Manager writes and
    what the agents' formula tools quote. It used to read
    `resources/dbtemp/formula.json` directly, and that was fine while the
    Formula Manager was the only other reader — but once an agent could cite a
    rule, a file the API had rewritten in another process meant the board and
    the agent could disagree about what a formula says. One store, one answer.

    Deliberately not cached. The old `lru_cache(maxsize=1)` was correct for a
    file that could not change within a process; a table the Formula Manager
    edits can, and a board still drawing last hour's rule after someone fixed
    it is the bug this move was meant to end. A 22-row read on a warmed pool is
    not what makes a dashboard request slow.
    """
    from src.formulas import repository

    return {entry["id"]: entry["expression"] for entry in repository.load()}


def formulas(wanted: tuple[str, ...]) -> dict[str, str]:
    """The expressions one agent's engine needs, and no others.

    Sent as data rather than evaluated here, because the What-If engine runs in
    the browser — a lever drag re-evaluates 800 rows and a round trip per frame
    would make the control unusable. Narrowed per agent so a board carries the
    rules it runs and nothing else.

    A missing id raises rather than being skipped: the browser would fail on it
    anyway, and failing here names the formula instead of the symptom.
    """
    catalogue = _catalogue()
    missing = [name for name in wanted if name not in catalogue]
    if missing:
        raise ValueError(
            f"retail.formula is missing {', '.join(missing)}. "
            "Seed it: python scripts/import_formulas_to_db.py"
        )
    return {name: catalogue[name] for name in wanted}


def _rows(connection: Any, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    return [dict(row) for row in connection.execute(text(sql), params or {}).mappings()]


def _scope_clause(
    scope: DashboardScope,
    entity_col: str,
    category_col: str | None,
    store_col: str | None = None,
):
    """The WHERE fragment and parameters for the columns a query really has.

    ``store_id`` is optional because the chain fact tables deliberately do not
    have a store key.  Callers must pass the real store dimension column when
    the query is store-grain; omitting it means no pretend predicate is added
    to a chain-level query.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if scope.legal_entity_id:
        clauses.append(f"{entity_col} = :legal_entity_id")
        params["legal_entity_id"] = scope.legal_entity_id
    if scope.category_group and category_col:
        clauses.append(f"{category_col} = :category_group")
        params["category_group"] = scope.category_group
    if scope.store_id and store_col:
        clauses.append(f"{store_col} = :store_id")
        params["store_id"] = scope.store_id
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def filter_options(connection: Any) -> dict[str, list]:
    """Every dropdown's full list.

    Deliberately not narrowed by the scope: the selectors narrow categories and
    stores to the chosen vertical themselves, and a dropdown that only offers
    what is already selected cannot be used to change the selection.
    """
    verticals = _rows(
        connection,
        f"""
        SELECT vertical_id, name, dashboard_label
        FROM {SCHEMA}.dim_vertical
        -- The workbook's own order, not alphabetical: Grocery has been the
        -- first entry on these boards since before there was a database.
        ORDER BY sort_order, vertical_id
        """,
    )
    categories = _rows(
        connection,
        f"""
        SELECT DISTINCT category_id, category_name, vertical_id
        FROM {SCHEMA}.dim_item
        WHERE category_id IS NOT NULL
        ORDER BY category_id
        """,
    )
    stores = _rows(
        connection,
        f"""
        SELECT store_id, name, vertical_id, cluster
        FROM {SCHEMA}.dim_store
        ORDER BY store_id
        """,
    )

    return {
        "legal_entities": [
            {
                "value": row["vertical_id"],
                "label": f"{row['vertical_id']} · {row['name']}",
                "dashboard_label": row["dashboard_label"],
            }
            for row in verticals
        ],
        "categories": [
            {
                "value": row["category_id"],
                # id first, like legal_entities/stores above: category_name
                # is not unique across verticals (e.g. DGT-C01 and OMN-C01
                # are both "Electronics"), so the bare name alone is not
                # enough to tell two dropdown entries apart.
                "label": f"{row['category_id']} · {row['category_name']}",
                "legal_entity_id": row["vertical_id"],
            }
            for row in categories
        ],
        "stores": [
            {
                "value": row["store_id"],
                "label": f"{row['store_id']} · {row['name']}",
                "legal_entity_id": row["vertical_id"],
                "cluster": row["cluster"],
            }
            for row in stores
        ],
        "states": list(STATE_ORDER),
    }


def chain_store_size(connection: Any) -> dict[str, float]:
    """Each vertical's total store-size index.

    Summed from `dim_store` rather than read from the vertical's own
    `sum_store_size`, which the workbook rounds to four places — enough drift
    to move `f01` off the figures every board reconciles against.
    """
    rows = _rows(
        connection,
        f"""
        SELECT vertical_id, sum(size_index) AS total
        FROM {SCHEMA}.dim_store
        GROUP BY vertical_id
        """,
    )
    return {row["vertical_id"]: float(row["total"]) for row in rows}


def arch_horizon_factor(
    ads: float, base_ads: float, seasonality: float, store_size: float
) -> float:
    """Recover f01's archetype/horizon factor from the row it was applied to.

    The warehouse stores the finished `ads` and the three inputs beside it, but
    not the factor between them, so it is divided back out. At the workbook's
    own lever setting f01 reduces to

        ads = base_ads x seasonality x arch_horizon_factor x store_size

    because the promo branch returns 1 when `Constants` B17 is zero. The
    division is therefore exact, not a fit.

    A zero denominator means the row carries no usable inputs; 1.0 keeps it
    arithmetically neutral rather than emitting a NaN that would spread through
    every KPI the moment a lever moved.

    Lives here rather than on one board because two boards now need it: Agent 2
    reads `dim_item.arch_horizon_factor` and falls back to this, and Agent 3
    does the same. A second copy of a numeric recovery rule is the shape of bug
    this package keeps paying for.
    """
    denominator = base_ads * seasonality * store_size
    return ads / denominator if denominator else 1.0


# The synthetic demand table's 32 week columns, in the order they unpivot to a
# timeline: actuals oldest first (w16 is 16 weeks back, w1 the most recent
# actual week), then forecasts nearest first (w1 is next week). A week index
# rides along (-16..-1, +1..+16) because "W-3" and "W+3" are labels the chart
# derives, while ordering needs a number.
_DEMAND_32W_COLUMNS: tuple[tuple[int, str, str], ...] = tuple(
    [(index, "actual", f"actual_w{-index}") for index in range(-16, 0)]
    + [(index, "forecast", f"forecast_w{index}") for index in range(1, 17)]
)


def demand_weekly_32w(
    connection: Any, scope: DashboardScope | None = None
) -> dict[str, dict[str, list[float]]]:
    """Per-SKU chain demand curve: 16 actual weeks, then 16 forecast weeks.

    Reads `synthetic.demand_store_sku_32w` (store x SKU, weeks pivoted wide)
    and collapses the stores, because every grain this package serves is
    chain-net -- the same argument `fact_inventory_chain_daily` makes. Returns
    ``{sku_id: {"actual": [...16 oldest first...], "forecast": [...16 nearest
    first...]}}``, ready to ride on an order line.

    The table is calibrated against the workbook rather than independent of
    it: the chain's first forecast week reproduces ``SUM(ads) x dow_sum`` to
    five significant figures, so the curve and the board's own ADS state one
    demand level, not two. The fixture builder checks that identity on every
    rebuild; this function only reads.

    Scope joins `dim_item`, so the two filters SQL applies (`legal_entity_id`,
    `category_group`) narrow the curve exactly as they narrow the lines.

    A missing table returns ``{}`` rather than raising: the boards treat the
    curve as additive -- they drew demand as a flat ADS rate before this table
    existed and still can, so an unseeded environment degrades to that
    presentation instead of losing the whole dashboard to a 503.
    """
    exists = connection.execute(
        text("SELECT OBJECT_ID(N'synthetic.demand_store_sku_32w', N'U')")
    ).scalar()
    if exists is None:
        return {}

    scope = scope or DashboardScope()
    where, params = _scope_clause(scope, "i.vertical_id", "i.category_id")
    values = ",\n                ".join(
        f"({index}, '{kind}', t.{column})"
        for index, kind, column in _DEMAND_32W_COLUMNS
    )

    rows = _rows(
        connection,
        f"""
        SELECT t.sku_id, w.week_index, w.kind, sum(w.units) AS units
        FROM synthetic.demand_store_sku_32w t
        JOIN {SCHEMA}.dim_item i ON i.item_id = t.sku_id
        CROSS APPLY (VALUES
                {values}
        ) w (week_index, kind, units)
        WHERE 1 = 1{where}
        GROUP BY t.sku_id, w.week_index, w.kind
        ORDER BY t.sku_id, w.week_index
        """,
        params,
    )

    curves: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        curve = curves.setdefault(row["sku_id"], {"actual": [], "forecast": []})
        curve[row["kind"]].append(float(row["units"]))
    return curves


# Day-of-week demand profile, Monday first.
#
# THE CANONICAL COPY. The workbook stores only their sum -- `Constants` B7 =
# 7.45, which is what f08 multiplies a daily rate by. These seven allocate that
# total across the week and sum to exactly it, so any daily view rolls back up
# to the weekly figure the sheet publishes. A modelled allocation of a measured
# total, and every payload that ships it says so.
#
# Both retail dashboards and both fixture builders read this name. It lived in
# four files before, which is the shape of bug this package keeps paying for:
# one rule with several homes, correct until somebody edits three of them.
DOW_PROFILE = (0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25)

MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# The month the workbook says it is (`Constants` B6), zero-based.
MONTH_INDEX = 6

# The sum the seven factors above must reproduce (`Constants` B7).
DOW_SUM = 7.45

# The cover f06 adds on top of lead and safety days (`Constants` B24, held there
# as `hzCov = MAX(2, Horizon/2)`). Read as a stored value, not recomputed from
# `Constants` B23: that cell is referenced by no formula in the workbook, so
# driving hzCov off a horizon the reader can change would move every Max level
# away from the sheet it is supposed to reconcile against.
#
# Deliberately NOT returned by `constants()` below: only Agents 2 and 3
# evaluate f06, and only their fixtures carry `hz_cov`. A board layers its own
# constants onto the shared set at the point it builds its payload -- the same
# way Agent 1 adds `interval_z` -- so a value two boards need does not silently
# widen the contract of the four that do not.
HORIZON_COVERAGE = 4.0


def constants() -> dict[str, Any]:
    """Model parameters, from the catalogue's own reference rather than a table.

    `dow_sum` and `month_index` are inputs to `f08` and `f01`. They are not
    facts about a day, so they do not belong in a fact table — a second home
    for one number is how two numbers appear.

    `dow_profile` rides along because every board that spends a day's demand
    needs the shape, not just the total: Inventory Risk burns stock against it
    and Demand Forecasting draws it. A board that receives the sum alone can
    only assume a flat week, which is exactly the assumption both boards had
    to stop making.
    """
    return {
        "dow_sum": DOW_SUM,
        "month_index": MONTH_INDEX,
        "dow_profile": list(DOW_PROFILE),
    }


def seasonal_indices(
    gmv_by_month: dict[int, float], node: tuple | None = None
) -> list[float]:
    """Twelve classical indices: month GMV over the series mean, times 100.

    Evaluates `fc01-seasonal-index` from the catalogue rather than doing the
    arithmetic here -- this is the rule the "Seasonality index" KPI tile
    reads too (`demand_forecasting/data/selectors.js`'s `computeKpis`), and a
    Formula Manager edit to `fc01` should reach both without either being
    retyped. `fc01` sits in a separate `fc`-prefixed id space from the
    workbook's own `f01`-`fNN` because it is not a transcription of any
    workbook cell -- see `resources/custom_formulas.json`.

    `node` lets a caller looping over several verticals (`seasonality()`
    below) parse `fc01` once and pass the AST in, rather than every vertical
    re-parsing the same three-token expression. Left optional so this
    function still works stood alone.
    """
    from src.formulas.expression import evaluate, parse

    if node is None:
        node = parse(formulas(("fc01-seasonal-index",))["fc01-seasonal-index"])

    values = [gmv_by_month.get(month, 0.0) for month in range(12)]
    mean = sum(values) / len(values) if values else 0.0
    if not mean:
        return [100.0] * 12
    return [
        evaluate(node, {"month_gmv": value, "series_mean": mean})
        for value in values
    ]


def seasonality(connection: Any) -> dict[str, Any]:
    """The seasonal block, identical for every board that ships it.

    One query and one shape, so Inventory Risk's projection and Demand
    Forecasting's outlook cannot disagree about what next month looks like.

    `avg(gmv)` over both years is a no-op on this dataset -- the workbook's
    series repeats one year twice -- but it is written as an average so a real
    second year would be handled rather than silently halved.
    """
    from src.formulas.expression import parse

    rows = _rows(
        connection,
        f"""
        SELECT vertical_id, month_index, avg(gmv) AS gmv
        FROM {SCHEMA}.fact_gmv_monthly
        GROUP BY vertical_id, month_index
        ORDER BY vertical_id, month_index
        """,
    )

    by_vertical: dict[str, dict[int, float]] = {}
    for row in rows:
        by_vertical.setdefault(row["vertical_id"], {})[int(row["month_index"])] = (
            float(row["gmv"]) if row["gmv"] is not None else 0.0
        )

    node = parse(formulas(("fc01-seasonal-index",))["fc01-seasonal-index"])

    return {
        "month_labels": list(MONTH_LABELS),
        "current_month_index": MONTH_INDEX,
        "by_legal_entity": {
            vertical_id: seasonal_indices(months, node)
            for vertical_id, months in sorted(by_vertical.items())
        },
    }


def agent_reference(connection: Any, agent_id: str) -> list[dict[str, Any]]:
    """One agent's own KPI sheet, per vertical — the reconciliation anchors.

    Stored long-format so agents 4 to 9 join in without a schema change, and
    pivoted back here to the wide shape the sheet states them in.

    Ordered by `vertical_id`, which is alphabetical and deliberately NOT the
    `sort_order` the item lists follow. The reference block is a table nobody
    scrolls in the UI; the fixture builders sorted it by id, and matching that
    is what keeps the two paths byte-comparable.

    Whole values come back whole. Long format has one `DOUBLE PRECISION`
    column, so every metric would otherwise arrive as a float and a card would
    read "46.0 SKUs". Rather than list which metrics are counts per agent, the
    rule is simply that a value the workbook stored whole stays whole — which
    is true of `stockout_risk_skus` and of `inventory_value` alike, and stays
    true for agents 4 to 9 without anybody maintaining a list.
    """
    rows = _rows(
        connection,
        f"""
        SELECT r.vertical_id, r.metric, r.value, v.dashboard_label
        FROM {SCHEMA}.agent_kpi_reference r
        JOIN {SCHEMA}.dim_vertical v ON v.vertical_id = r.vertical_id
        WHERE r.agent_id = :agent
        ORDER BY r.vertical_id, r.metric
        """,
        {"agent": agent_id},
    )

    by_vertical: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_vertical.setdefault(
            row["vertical_id"],
            {
                "legal_entity_id": row["vertical_id"],
                "vertical_label": row["dashboard_label"],
            },
        )
        value = row["value"]
        entry[row["metric"]] = (
            int(value) if value is not None and float(value).is_integer() else value
        )

    return list(by_vertical.values())


def envelope(agent: str, note: str) -> dict[str, Any]:
    """The metadata every Retail payload carries.

    `is_mock` stays true. The rows are real workbook figures, but they are one
    demonstration snapshot, not a live ERP position, and the boards say so on
    screen. It flips when D365 is the source, not when Postgres is.
    """
    return {
        "schema_version": 1,
        "agent": agent,
        "generated_at": f"{SNAPSHOT_DATE}T00:00:00+00:00",
        "is_mock": True,
        "note": note,
        "source_workbook": SOURCE_WORKBOOK,
    }


__all__ = [
    "HORIZON_COVERAGE",
    "REPLENISH_STATES",
    "SCHEMA",
    "SNAPSHOT_DATE",
    "STATE_ORDER",
    "SUPPORTED_FILTERS",
    "arch_horizon_factor",
    "chain_store_size",
    "constants",
    "demand_weekly_32w",
    "envelope",
    "filter_options",
    "formulas",
    "get_engine",
    "_rows",
    "_scope_clause",
]
