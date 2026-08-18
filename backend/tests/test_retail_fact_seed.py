"""The fact seed: its mapping, and whether what landed matches the boards.

Two halves, on purpose.

The mapping tests are pure — workbook rows in, table rows out — and run
everywhere. They cover the part most likely to be wrong: column names, and the
coercions where a plausible-looking mistake is silent (`"NO"` is a non-empty
string, and therefore true, to Python).

The reconciliation tests need a seeded database and skip without one. They are
the guard that matters most for the phase after this: three dashboard builders
will read these tables, and their answers can only be trusted while the tables
still agree with the fixtures the boards were verified against.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[2]


def _load_seeder():
    """Import the seeder by path — `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "seed_retail_facts", REPO / "scripts" / "seed_retail_facts_from_json.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seeder = _load_seeder()


@pytest.fixture(scope="module")
def tables():
    return seeder.load_tables()


# ------------------------------------------------------------------ coercions


class TestCoercions:
    @pytest.mark.parametrize("value", ["Y", "YES", "yes", "True", "1", True])
    def test_truthy_spellings(self, value) -> None:
        assert seeder.as_bool(value) is True

    @pytest.mark.parametrize("value", ["N", "NO", "no", "False", "0", "", None, False])
    def test_falsy_spellings(self, value) -> None:
        """`NO` is the one that matters.

        The workbook writes `reorder` as YES/NO. A truthiness check would make
        every one of the 800 rows a reorder, and the board would open on the
        whole assortment while claiming to show what needs ordering.
        """
        assert seeder.as_bool(value) is False

    def test_dates_parse_and_stay_open_ended_when_blank(self) -> None:
        assert seeder.as_date("2025-01-01") == date(2025, 1, 1)
        assert seeder.as_date("2026-12-31") == date(2026, 12, 31)
        # Blank means "no end stated", not 1970.
        assert seeder.as_date("") is None
        assert seeder.as_date(None) is None


# -------------------------------------------------------------------- mapping


class TestMapping:
    def test_inventory_carries_every_engine_row(self, tables) -> None:
        rows = seeder.build_inventory(tables)

        assert len(rows) == 16_000
        assert {r["cal_date"] for r in rows} == {seeder.SNAPSHOT_DATE}
        # `max_qty` is the column this schema was missing; without it no
        # purchase-order figure is derivable from the database at all.
        assert all(r["max_qty"] is not None for r in rows)

    def test_inventory_is_stockout_is_the_state_not_the_risk_zone(self, tables) -> None:
        """A2 counts risk as `Position < ROP`, which is Stockout *and* Low.

        This column is narrower on purpose, and the difference is the point: a
        builder needing the risk zone has `position_qty` and `rop_qty` to
        compute it from, whereas a column named `is_stockout` that quietly
        meant something wider would be read wrongly by whoever comes next.
        """
        rows = seeder.build_inventory(tables)
        flagged = {r["state"] for r in rows if r["is_stockout"]}

        assert flagged == {"Stockout"}
        assert any(r["state"] == "Low" and not r["is_stockout"] for r in rows)

    def test_trade_agreements_resolve_vendors_by_account(self, tables) -> None:
        rows = seeder.build_trade_agreements(tables)
        accounts = {r["vendor_account"] for r in tables["vendors"]}

        assert len(rows) == 2_400
        assert {r["vendor_account"] for r in rows} <= accounts
        assert any(r["is_designated"] for r in rows)
        assert all(isinstance(r["valid_from"], date) for r in rows)

    def test_replenishment_translates_vendor_labels_into_keys(self, tables) -> None:
        """`replenishment_detail` names vendors, every other table keys them.

        The workbook writes "Vendor E" where the schema declares a foreign key
        to `dim_vendor (vendor_account)`, whose values are "V0005". Seeding the
        label verbatim fails all 800 rows; re-declaring the column as free text
        would put two spellings of one vendor in the database.
        """
        rows = seeder.build_replenishment(tables)
        accounts = {r["vendor_account"] for r in tables["vendors"]}

        assert len(rows) == 800
        assert {r["designated_vendor"] for r in rows} <= accounts
        assert {r["best_price_vendor"] for r in rows} <= accounts
        # And the labels really were different, so the test is not vacuous.
        labels = {r["designated_vendor"] for r in tables["replenishment_detail"]}
        assert not labels & accounts

    def test_reorder_count_survives_the_yes_no_coercion(self, tables) -> None:
        rows = seeder.build_replenishment(tables)

        # The same count the boards agree on, and not all 800. It read 438 for
        # a while, when `ROP` was taking its lead time from the designated
        # Trade Agreement row rather than the static `SKU_Master.Lead (d)`.
        # That revision was withdrawn -- the workbook is not being changed --
        # so the lead term is the master column again and the count is back to
        # what the database has held all along.
        assert sum(1 for r in rows if r["is_reorder"]) == 302

    def test_assortment_is_the_item_store_pairs_that_exist(self, tables) -> None:
        rows = seeder.build_assortment(tables)

        # 800 SKUs ranged in 20 stores each, out of a possible 128,000.
        assert len(rows) == 16_000
        assert len({(r["item_key"], r["store_key"]) for r in rows}) == 16_000


# ------------------------------------------------------- database reconciliation


def _engine_or_skip():
    sys.path.insert(0, str(REPO / "backend"))
    try:
        from src.db.db import get_engine

        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(
                text("SELECT count(*) FROM retail.fact_inventory_daily")
            ).scalar_one()
        return engine
    except Exception as error:  # noqa: BLE001 - any failure means "not seeded here"
        pytest.skip(f"no seeded retail database: {error}")


@pytest.fixture(scope="module")
def engine():
    return _engine_or_skip()


@pytest.fixture(scope="module")
def a3_fixture():
    path = REPO / "frontend/src/agents/retail/replenishment/data/fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def a2_fixture():
    path = REPO / "frontend/src/agents/retail/inventory_risk/data/fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestReconciliation:
    """Two code paths, one workbook. They have to land on the same figures.

    The fixtures were built straight from `schema_with_data.json` by the
    `build_*_fixture.py` scripts; the database was seeded from the same JSON by
    a different path. Agreement means nothing was lost or reshaped on the way
    in — and disagreement, once the builders exist, would show on screen as two
    boards contradicting each other.
    """

    def test_row_counts(self, engine) -> None:
        with engine.connect() as c:
            counts = {
                name: c.execute(text(f"SELECT count(*) FROM retail.{name}")).scalar_one()
                for name in (
                    "fact_inventory_daily",
                    "trade_agreement",
                    "replenishment_proposal",
                    "fact_sales_daily",
                )
            }

        assert counts["fact_inventory_daily"] == 16_000
        assert counts["trade_agreement"] == 2_400
        assert counts["replenishment_proposal"] == 800
        # Deliberately empty: the workbook has no history, and inventing one
        # would put fabricated rows in the table that later holds real D365
        # data, with nothing separating them.
        assert counts["fact_sales_daily"] == 0

    def test_replenishment_totals_match_the_board(self, engine, a3_fixture) -> None:
        lines = a3_fixture["lines"]
        with engine.connect() as c:
            row = c.execute(
                text(
                    """
                    -- `count(*) FILTER (WHERE ...)` is Postgres-only and this
                    -- runs against Azure SQL; is_reorder is a bit there, so it
                    -- also needs an explicit = 1 rather than a bare predicate.
                    SELECT sum(CASE WHEN is_reorder = 1 THEN 1 ELSE 0 END) AS reorder,
                           coalesce(sum(order_qty_sales), 0)  AS units,
                           coalesce(sum(amount), 0)           AS cost,
                           coalesce(sum(saving_vs_designated), 0) AS saving
                    FROM retail.replenishment_proposal
                    """
                )
            ).one()

        assert row.reorder == sum(1 for line in lines if line["is_reorder"])
        assert float(row.units) == pytest.approx(
            sum(line["order_qty_sales"] for line in lines), abs=0.5
        )
        assert float(row.cost) == pytest.approx(
            sum(line["order_value_cost"] for line in lines), abs=1.0
        )
        assert float(row.saving) == pytest.approx(
            sum(line["saving_vs_designated"] for line in lines), abs=1.0
        )

    def test_the_chain_net_roll_up_finds_the_same_at_risk_skus(
        self, engine, a2_fixture
    ) -> None:
        """The cross-agent invariant, now through the database.

        A2 calls them stockout-risk, A3 calls them lines to reorder, and both
        mean `Position < ROP` summed across every store. The same number either
        way, or the two boards will disagree the moment they read from here.

        302 on both sides now. The note that used to sit here explained why
        the database lagged the workbook at 302 against 438; the workbook
        revision was withdrawn, so the two agree again and there is nothing
        left to reconcile across.
        """
        with engine.connect() as c:
            at_risk = c.execute(
                text(
                    """
                    SELECT count(*) FROM (
                      SELECT item_key
                      FROM retail.fact_inventory_daily
                      GROUP BY item_key
                      HAVING sum(position_qty) < sum(rop_qty)
                    ) t
                    """
                )
            ).scalar_one()

        assert at_risk == sum(1 for item in a2_fixture["items"] if item["is_stockout_risk"])
        assert at_risk == 302

    def test_every_foreign_key_resolves(self, engine) -> None:
        with engine.connect() as c:
            orphans = c.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM retail.replenishment_proposal p
                         LEFT JOIN retail.dim_vendor v
                           ON v.vendor_account = p.designated_vendor
                        WHERE v.vendor_account IS NULL) AS designated,
                      (SELECT count(*) FROM retail.replenishment_proposal p
                         LEFT JOIN retail.dim_vendor v
                           ON v.vendor_account = p.best_price_vendor
                        WHERE v.vendor_account IS NULL) AS best,
                      (SELECT count(*) FROM retail.fact_inventory_daily
                        WHERE max_qty IS NULL) AS no_max
                    """
                )
            ).one()

        assert orphans.designated == 0
        assert orphans.best == 0
        assert orphans.no_max == 0

    def test_the_seed_is_safe_to_run_twice(self, engine) -> None:
        """Upsert, not append. A second run must not double the tables.

        Asserted rather than assumed because the failure is quiet: a doubled
        `fact_inventory_daily` still answers every query, just with every
        figure twice its true size.
        """
        with engine.connect() as c:
            distinct, total = c.execute(
                text(
                    """
                    SELECT
                        (SELECT count(*) FROM (
                            SELECT DISTINCT item_key, store_key, cal_date
                            FROM retail.fact_inventory_daily
                        ) AS d),
                        (SELECT count(*) FROM retail.fact_inventory_daily)
                    """
                )
            ).one()

        assert distinct == total
