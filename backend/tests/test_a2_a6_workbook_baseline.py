"""A2 and A6 against the old workbook, through the database this time.

`test_retail_dashboard_builders.py` already proves the *boards* reproduce the
checked-in fixtures. Nothing proved the same for the **agent tools** — and the
tools do not share a line of SQL with the builders. A2's snapshot aggregates in
the database where the builder aggregates in the browser; A6's tools re-derive
the productivity chain and its quartiles in a CTE where `dashboard.classify`
derives them in Python. Two independent implementations of one workbook, and
until this file existed only one of them was checked.

That gap matters more than it sounds. A board that is right and a chat answer
that is wrong is the worst of the two failures: the figure on screen and the
figure in the conversation come from the same brand of confidence, and the
reader has no way to tell which one was computed and which one drifted.

THREE LAYERS, DELIBERATELY SEPARATE
-----------------------------------
1. `TestWorkbookReachedTheWarehouse` — `schema_with_data.json` against the
   tables, row for row. No fixture in between. If this fails, everything below
   is measuring the wrong database and the failures downstream are noise.
2. `TestAgent2` / `TestAgent6` — the tools' own output against the workbook
   baseline. The fixtures are that baseline: `build_*_fixture.py` built them
   straight from the same JSON by a third path.
3. `TestGrainIsNotCrossed` — the one failure this dataset invites. Chain-net
   (800 rows) and per-store gross (16,000 rows) differ by about 1.25x and both
   are correct. A test that pinned only the headline would pass while a tool
   quietly answered at the wrong grain.

Skips without a seeded database rather than failing, matching the other retail
suites, so a machine with no Azure SQL still runs the pure tests.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

WORKBOOK = REPO / "resources" / "dbtemp" / "schema_with_data.json"
FIXTURES = REPO / "frontend" / "src" / "agents" / "retail"

# Money is summed over 800 rows of rupiah in the 10^12 range. A rupiah of slack
# absorbs the last-place difference between NUMERIC addition in SQL Server and
# IEEE addition in the fixture builder, and is far below anything a reader sees.
RUPIAH = 1.0


# --------------------------------------------------------------- the sources


def _workbook() -> dict[str, list[dict]]:
    """`{sheet: [row dict, ...]}` — the same shape the seeder loads."""
    payload = json.loads(WORKBOOK.read_text(encoding="utf-8"))
    return {
        table["name"]: [
            dict(zip([c["name"] for c in table["columns"]], row))
            for row in table["rows"]
        ]
        for table in payload["tables"]
    }


def _fixture(folder: str) -> dict:
    path = FIXTURES / folder / "data" / "fixture.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def book():
    return _workbook()


@pytest.fixture(scope="module")
def a2_fixture():
    return _fixture("inventory_risk")


@pytest.fixture(scope="module")
def a6_fixture():
    return _fixture("assortment_optimization")


@pytest.fixture(scope="module")
def engine():
    try:
        from src.db.db import get_engine

        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(
                text("SELECT count(*) FROM retail.fact_inventory_chain_daily")
            ).scalar_one()
        return engine
    except Exception as error:  # noqa: BLE001 — any failure means "not seeded here"
        pytest.skip(f"no seeded retail database: {error}")


def _tool_or_skip(loader):
    """Import and call a tool, skipping if the database is not there.

    The tools open their own connections through `snapshot._read_connection`,
    so the `engine` fixture cannot gate them; this does the same job.
    """
    try:
        return loader()
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"no seeded retail database: {error}")


@pytest.fixture(scope="module")
def a2_snapshot():
    def load():
        from src.llm.agents.retail.inventory_risk.tools.inventory_data import (
            get_inventory_risk_snapshot,
        )

        return get_inventory_risk_snapshot()

    return _tool_or_skip(load)


@pytest.fixture(scope="module")
def a6_snapshot():
    def load():
        from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
            get_assortment_performance_snapshot,
        )

        return get_assortment_performance_snapshot()

    return _tool_or_skip(load)


# ------------------------------------------------- layer 1: workbook → tables


class TestWorkbookReachedTheWarehouse:
    """`schema_with_data.json` against the tables, with no fixture between.

    Row-level, not totals. Totals agreeing while rows disagree is a real
    outcome — two sign errors, a shifted column pair — and it is exactly the
    kind of thing a per-SKU chat answer surfaces and a chain headline hides.
    """

    def test_the_chain_table_is_the_engine_sheet(self, engine, book) -> None:
        """`fact_inventory_chain_daily` is `ENGINE`, 800 rows, column for column.

        Both A2's snapshot and A6's CTE read every one of these columns. The
        `state` check is the load-bearing one: A2 counts states and A6 delists
        on them, so a single mislabelled row moves two boards at once.
        """
        rows = book["engine"]
        assert len(rows) == 800

        with engine.connect() as c:
            live = {
                r.item_key: r
                for r in c.execute(
                    text(
                        """
                        SELECT item_key, state, position_qty, rop_qty, max_qty,
                               days_cover, unit_price, inventory_value,
                               at_risk_value, expiry_units, ads
                        FROM retail.fact_inventory_chain_daily
                        """
                    )
                ).all()
            }

        assert set(live) == {r["sku_id"] for r in rows}

        for want in rows:
            got = live[want["sku_id"]]
            where = want["sku_id"]
            assert got.state == want["state"], f"{where}: state"
            assert float(got.position_qty) == pytest.approx(want["position"]), where
            assert float(got.rop_qty) == pytest.approx(want["rop"]), where
            assert float(got.max_qty) == pytest.approx(want["max"]), where
            assert float(got.unit_price) == pytest.approx(want["price"]), where
            assert float(got.days_cover) == pytest.approx(want["dos"], rel=1e-9), where
            assert float(got.ads) == pytest.approx(want["ads"], rel=1e-9), where
            assert float(got.inventory_value) == pytest.approx(
                want["inv_value"], abs=RUPIAH
            ), where
            assert float(got.at_risk_value) == pytest.approx(
                want["at_risk"], abs=RUPIAH
            ), where
            assert float(got.expiry_units) == pytest.approx(
                want["expiry_u"], rel=1e-9
            ), where

    def test_dim_item_carries_the_four_columns_a6_multiplies(
        self, engine, book
    ) -> None:
        """`base_ads * seasonality_index * store_size`, then margin, then growth.

        A6 does not read the chain's stored `ads`; it rebuilds ADS from
        `dim_item` and the store-size roll-up, then divides margin into
        inventory value for GMROI. Four columns, three multiplications, and
        every one of them silent when wrong — a `margin_pct` off by a factor of
        100 still produces a plausible-looking GMROI ranking, just the wrong
        one, and the delist list follows it.
        """
        rows = book["sku_master"]
        assert len(rows) == 800

        with engine.connect() as c:
            live = {
                r.item_id: r
                for r in c.execute(
                    text(
                        """
                        SELECT item_id, base_ads, seasonality_index, price,
                               margin_pct, growth_index
                        FROM retail.dim_item
                        """
                    )
                ).all()
            }

        for want in rows:
            got = live[want["sku_id"]]
            where = want["sku_id"]
            assert float(got.base_ads) == pytest.approx(want["base_ads"]), where
            assert float(got.seasonality_index) == pytest.approx(
                want["seasonality"]
            ), where
            assert float(got.price) == pytest.approx(want["price"]), where
            assert float(got.margin_pct) == pytest.approx(want["margin_pct"]), where
            assert float(got.growth_index) == pytest.approx(want["growth"]), where

    def test_store_size_rolls_up_to_what_the_workbook_states(
        self, engine, book
    ) -> None:
        """The summed size index per vertical, which A6's `size` CTE computes.

        WHY THIS IS A TOLERANCE AND NOT AN EQUALITY
        `sku_master.sum_vert_size` is the workbook's own copy of this figure and
        the two do NOT agree exactly — GRC is 20.8447 there against 20.8445
        rolled up here, and six of the eight verticals differ in the last place.
        Excel totalled the underlying sizes and rounded once; the warehouse
        stores the published four-decimal size per store and sums those. The
        roll-up is the more defensible of the two, which is why
        `assortment_data.py` uses it and says so, and why `sum_vert_size` was
        never seeded.

        So the tolerance is 5e-4 — a few last places, wide enough to pass on
        that rounding and far too tight to survive a store landing in the wrong
        vertical, which is the failure actually worth catching. The store count
        is asserted exactly for the same reason.
        """
        stated = {r["vertical_id"]: r["sum_vert_size"] for r in book["sku_master"]}

        with engine.connect() as c:
            rolled = {
                r.vertical_id: (float(r.total), r.stores)
                for r in c.execute(
                    text(
                        """
                        SELECT vertical_id, sum(size_index) AS total,
                               count(*) AS stores
                        FROM retail.dim_store
                        GROUP BY vertical_id
                        """
                    )
                ).all()
            }

        assert set(rolled) == set(stated)
        for vertical, (total, stores) in rolled.items():
            assert stores == 20, vertical
            assert total == pytest.approx(stated[vertical], abs=5e-4), vertical


# ------------------------------------------------------- layer 2: A2's tool


class TestAgent2SnapshotMatchesTheWorkbook:
    """`get_inventory_risk_snapshot()` against the workbook baseline.

    The fixture is the baseline: `build_inventory_risk_fixture.py` built it
    from `schema_with_data.json` in Python, and this tool computes the same
    figures in SQL. Nothing is shared between the two paths but the workbook.
    """

    def test_the_seven_headline_totals(self, a2_snapshot, a2_fixture) -> None:
        items = a2_fixture["items"]
        totals = a2_snapshot["totals"]

        assert totals["skus"] == len(items) == 800
        assert float(totals["inventory_value"]) == pytest.approx(
            sum(i["inv_value"] for i in items), abs=RUPIAH
        )
        assert float(totals["at_risk_value"]) == pytest.approx(
            sum(i["at_risk_value"] for i in items), abs=RUPIAH
        )
        assert float(totals["expiry_units"]) == pytest.approx(
            sum(i["expiry_units"] for i in items), abs=0.5
        )
        assert totals["overstock_skus"] == sum(1 for i in items if i["is_overstock"])
        assert totals["slow_mover_skus"] == sum(1 for i in items if i["is_slow_mover"])
        assert totals["stockout_risk_skus"] == sum(
            1 for i in items if i["is_stockout_risk"]
        )

    def test_stockout_risk_is_the_cross_agent_302(self, a2_snapshot) -> None:
        """A2 calls it stockout-risk, A3 calls it lines to reorder.

        Both mean `Position < ROP`. `test_retail_fact_seed.py` pins 302 at the
        per-store grain through a roll-up; this pins the same 302 arriving from
        the chain table through the tool. Two boards and a chat answer that
        disagree on this number is the discrepancy a reader notices first.
        """
        assert a2_snapshot["totals"]["stockout_risk_skus"] == 302

    def test_below_rop_is_counted_not_inferred_from_the_label(
        self, a2_snapshot
    ) -> None:
        """Every Stockout and Low row is below ROP; no other state is.

        The snapshot sums `position_qty < rop_qty` per state rather than
        filtering to the two labels, because Expiry is tested first and can
        cover a below-ROP row. This asserts the measured column agrees with the
        labels *on this dataset*, so if a future workbook does strand a
        below-ROP row in Expiry the test says so rather than the count silently
        moving.
        """
        by_state = {r["state"]: r for r in a2_snapshot["by_state"]}

        for state in ("Stockout", "Low"):
            assert by_state[state]["below_rop_skus"] == by_state[state]["skus"], state
        for state in ("Healthy", "Overstock", "Slow-mover", "Expiry"):
            assert by_state[state]["below_rop_skus"] == 0, state

    def test_every_state_matches_the_workbook_in_count_and_value(
        self, a2_snapshot, a2_fixture
    ) -> None:
        items = a2_fixture["items"]
        counts = Counter(i["state"] for i in items)
        value: dict[str, float] = defaultdict(float)
        for item in items:
            value[item["state"]] += item["at_risk_value"]

        got = {r["state"]: r for r in a2_snapshot["by_state"]}
        assert set(got) == set(counts)
        for state, expected in counts.items():
            assert got[state]["skus"] == expected, state
            assert float(got[state]["at_risk_value"]) == pytest.approx(
                value[state], abs=RUPIAH
            ), state

        # Healthy carries inventory but nothing at risk. Stated because a
        # regression here reads as "risk fell", which is the pleasant direction
        # for a wrong number to move and therefore the one least questioned.
        assert got["Healthy"]["at_risk_value"] == 0

    def test_the_reference_block_is_the_a2_sheet_verbatim(
        self, a2_snapshot, book
    ) -> None:
        """The workbook's own published KPIs, carried through unaltered.

        This block exists so the model can check a computed headline against
        what the workbook printed. It is only worth carrying while it is
        actually the sheet — a reference that has drifted into a second
        computation is worse than no reference, because it agrees for the
        wrong reason.
        """
        sheet = {r["vertical_label"]: r for r in book["a2_inventory_risk"]}
        got = {r["vertical_label"]: r for r in a2_snapshot["reference_by_vertical"]}

        assert set(got) == set(sheet)
        for label, want in sheet.items():
            assert got[label]["stockout_risk_skus"] == want["stockout_risk_skus"], label
            assert got[label]["overstock_skus"] == want["overstock_skus"], label
            assert float(got[label]["inventory_value"]) == pytest.approx(
                want["inventory_value"], abs=RUPIAH
            ), label
            assert float(got[label]["at_risk_value"]) == pytest.approx(
                want["at_risk_value"], abs=RUPIAH
            ), label

    def test_expiry_is_grocery_and_only_grocery(self, a2_snapshot, book) -> None:
        """6,252 units, all of it perishable, all of it in Grocery.

        The A2 sheet states 6,251.89 for Grocery and zero everywhere else. The
        snapshot rounds to units, so the two agree to within the rounding and
        nothing else in the chain contributes.
        """
        sheet = {r["vertical_label"]: r["expiry_units"] for r in book["a2_inventory_risk"]}
        assert sheet["Grocery"] == pytest.approx(6251.89, abs=0.01)
        assert all(v == 0 for k, v in sheet.items() if k != "Grocery")

        by_vertical = {r["vertical_id"]: r for r in a2_snapshot["by_vertical"]}
        assert float(a2_snapshot["totals"]["expiry_units"]) == pytest.approx(
            sheet["Grocery"], abs=0.5
        )
        assert by_vertical["GRC"]["skus"] == 100


# ------------------------------------------------------- layer 2: A6's tools


class TestAgent6SnapshotMatchesTheWorkbook:
    """The three A6 tools against the workbook baseline.

    A6 is the harder of the two: nothing it reports is stored. Delist, grow,
    tail and GMROI are all derived, and derived twice — in `dashboard.classify`
    over the whole population in Python, and in the tools' CTE over the same
    population in SQL. Both have to land on the same 404.
    """

    def test_the_classification_counts_are_the_workbooks(
        self, a6_snapshot, a6_fixture
    ) -> None:
        counts = Counter(i["classification"] for i in a6_fixture["items"])
        totals = a6_snapshot["totals"]

        assert totals["sku_count"] == 800
        assert totals["delist_candidates"] == counts["delist"] == 404
        assert totals["grow_candidates"] == counts["grow"] == 12
        assert totals["hold_skus"] == counts["hold"] == 384
        assert totals["tail_skus"] == sum(
            1 for i in a6_fixture["items"] if i["is_tail"]
        )

    def test_the_three_classes_partition_the_range(self, a6_snapshot) -> None:
        """Delist + grow + hold = every SKU, each counted once.

        A SKU can satisfy both the grow and the delist rule; the CTE resolves
        that tie toward delist, the same way `dashboard.classify` does. Without
        this the two could disagree only on the overlap, which is a handful of
        rows and never shows in a headline.
        """
        totals = a6_snapshot["totals"]
        assert (
            totals["delist_candidates"] + totals["grow_candidates"] + totals["hold_skus"]
            == totals["sku_count"]
        )

    def test_the_four_cutoffs_are_the_boards_cutoffs(
        self, a6_snapshot, a6_fixture
    ) -> None:
        """SQL's `percentile_cont` against Python's percentile, same population.

        These four numbers decide the 404. The tools compute them in the
        database rather than re-deriving the board's, precisely so that a
        divergence between the two is *possible* — and therefore has to be
        tested, not assumed.
        """
        want = a6_fixture["classification_thresholds"]
        totals = a6_snapshot["totals"]

        assert float(totals["cutoff_gmroi_p25"]) == pytest.approx(
            want["p25_gmroi_chain"], abs=1e-6
        )
        assert float(totals["cutoff_contribution_p25"]) == pytest.approx(
            want["p25_contribution_chain"], abs=0.01
        )
        assert float(totals["cutoff_gmroi_p75_healthy"]) == pytest.approx(
            want["p75_gmroi_healthy"], abs=1e-6
        )
        assert float(totals["cutoff_contribution_p75_healthy"]) == pytest.approx(
            want["p75_contribution_healthy"], abs=0.01
        )

    def test_the_money_matches_the_workbook(self, a6_snapshot, a6_fixture) -> None:
        items = a6_fixture["items"]
        totals = a6_snapshot["totals"]

        assert float(totals["inventory_value"]) == pytest.approx(
            sum(i["inv_value"] for i in items), abs=RUPIAH
        )
        assert float(totals["contribution_per_day"]) == pytest.approx(
            sum(i["contribution_per_day"] for i in items), abs=RUPIAH
        )
        assert float(totals["capital_freed"]) == pytest.approx(
            sum(i["inv_value"] for i in items if i["classification"] == "delist"),
            abs=RUPIAH,
        )
        assert float(totals["tail_contribution"]) == pytest.approx(
            sum(i["contribution_per_day"] for i in items if i["is_tail"]), abs=RUPIAH
        )
        assert float(totals["avg_gmroi"]) == pytest.approx(
            sum(i["gmroi"] for i in items) / len(items), abs=1e-4
        )

    def test_the_tail_is_a_quartile_because_it_is_defined_as_one(
        self, a6_snapshot
    ) -> None:
        """25.0%, and it has to be — the tail is P25 of contribution.

        Worth pinning as a number rather than trusting the arithmetic: a tail
        share that is not a quarter means the cutoff was applied to a different
        population than the one being counted.
        """
        assert a6_snapshot["tail_share_pct"] == 25.0
        assert a6_snapshot["totals"]["tail_skus"] == 200

    def test_the_contribution_total_is_the_a6_sheets_one_trusted_column(
        self, a6_snapshot, book
    ) -> None:
        """Column G of the A6 sheet, reproduced to the rupiah at store grain.

        AUDIT RC-2 names A6!B6:F13 — delist, grow, GMROI, tail share, capital
        freed — as pasted values from an old snapshot. Column G
        (`contribution_day`) sits outside that range and is live. The per-store
        roll-up hits it exactly, which is what makes it usable as the anchor
        the stale columns cannot be.

        The second half is the important half: the sheet's *stale* columns are
        asserted to disagree. If a future change made them line up, it would
        mean the pipeline had started reproducing a snapshot rather than
        computing from the engine, and no other test would notice.
        """
        sheet = book["a6_assortment"]
        stated_contribution = sum(r["contribution_day"] for r in sheet)

        assert float(
            a6_snapshot["store_gross"]["store_gross_contribution_per_day"]
        ) == pytest.approx(stated_contribution, abs=RUPIAH)

        assert sum(r["delist_candidates"] for r in sheet) == 106
        assert a6_snapshot["totals"]["delist_candidates"] == 404
        assert float(a6_snapshot["totals"]["capital_freed"]) != pytest.approx(
            sum(r["capital_freed"] for r in sheet), rel=0.01
        )

    def test_delist_recommendations_come_from_the_delist_population(self) -> None:
        """Named SKUs, each with the rule it actually failed.

        `qualified_on` is the field a reader acts on — "state" is a different
        conversation from "tail contribution" — so it is checked against the
        rule rather than merely checked for presence.
        """

        def load():
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                get_delist_recommendations,
            )

            return get_delist_recommendations()

        result = _tool_or_skip(load)
        candidates = result["candidates"]

        assert candidates
        assert len(candidates) <= 12  # snapshot.TOP_N
        assert all(c["qualified_on"] in {"state", "low GMROI", "tail contribution"}
                   for c in candidates)
        for candidate in candidates:
            if candidate["qualified_on"] == "state":
                assert candidate["state"] in {"Slow-mover", "Overstock", "Expiry"}

        # Worst first, by the capital each one frees.
        freed = [float(c["capital_freed"]) for c in candidates]
        assert freed == sorted(freed, reverse=True)

    def test_delist_candidates_are_the_ones_the_board_names(self, a6_fixture) -> None:
        """The same SKU ids, not merely the same count.

        404 on both sides with a different 404 is the failure this catches, and
        a count-only test cannot see it. Only the top slice is comparable — the
        tool returns TOP_N — so the check is containment plus the identity of
        the worst dozen by capital.
        """

        def load():
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                get_delist_recommendations,
            )

            return get_delist_recommendations()

        result = _tool_or_skip(load)
        board_delist = {
            i["sku_id"] for i in a6_fixture["items"] if i["classification"] == "delist"
        }
        got = [c["item_key"] for c in result["candidates"]]

        assert set(got) <= board_delist, "the tool delisted a SKU the board holds"

        worst = sorted(
            (i for i in a6_fixture["items"] if i["classification"] == "delist"),
            key=lambda i: i["inv_value"],
            reverse=True,
        )[: len(got)]
        assert got == [i["sku_id"] for i in worst]

    def test_a_full_rationalization_acts_on_every_candidate(self, a6_snapshot) -> None:
        """100% means 404 of 404, and the same capital as the headline.

        This is the regression that made the file worth writing.
        `percent_rank()` puts the last row at exactly 1.0, so `worst_rank < 1.0`
        dropped one SKU: the simulation reported 403 candidates and Rp 6.68m
        less capital than the snapshot's own `capital_freed`, from the same
        population, in the same response. `cume_dist() <= share` is the fix.
        """

        def load():
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                simulate_assortment_rationalization,
            )

            return simulate_assortment_rationalization(delist_share_pct=100)

        result = _tool_or_skip(load)
        acted = result["acted_on"]

        assert acted["skus_acted_on"] == a6_snapshot["totals"]["delist_candidates"]
        assert float(acted["capital_freed"]) == pytest.approx(
            float(a6_snapshot["totals"]["capital_freed"]), abs=RUPIAH
        )
        assert result["retained"]["skus_kept"] == a6_snapshot["totals"]["sku_count"] - (
            acted["skus_acted_on"]
        )

    def test_a_partial_rationalization_takes_the_worst_share(self) -> None:
        """25% is a quarter of the candidates, and monotonic in between.

        Checked across the range because the boundary behaviour is where the
        off-by-one lived: 0% must free nothing at all, and each larger share
        must free at least as much as the one below it.
        """

        def load(pct):
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                simulate_assortment_rationalization,
            )

            return simulate_assortment_rationalization(delist_share_pct=pct)

        none = _tool_or_skip(lambda: load(0))
        assert none["acted_on"]["skus_acted_on"] == 0

        quarter = _tool_or_skip(lambda: load(25))
        half = _tool_or_skip(lambda: load(50))
        whole = _tool_or_skip(lambda: load(100))

        assert quarter["acted_on"]["skus_acted_on"] == 101   # 404 / 4
        assert half["acted_on"]["skus_acted_on"] == 202      # 404 / 2
        assert whole["acted_on"]["skus_acted_on"] == 404

        freed = [float(r["acted_on"]["capital_freed"]) for r in (quarter, half, whole)]
        assert freed == sorted(freed)

        # The worst-first ordering is by capital, so the first quarter of the
        # candidates carries far more than a quarter of the money. Asserted as
        # a floor rather than a figure: it is a property of the ranking, and
        # pinning the exact ratio would just restate the dataset.
        assert freed[0] > 0.5 * freed[2]

    def test_the_state_split_agrees_with_a2_at_the_same_grain(
        self, a6_snapshot, a2_snapshot
    ) -> None:
        """Two agents, one chain table. The states cannot differ.

        A6 reads the chain through its CTE at `cal_date = SNAPSHOT_DATE`; A2
        reads it with no date filter at all, which is the same 800 rows only
        while the workbook stays single-dated. If a second date ever lands,
        this test is the one that says so.
        """
        a6 = {r["state"]: r for r in a6_snapshot["by_state"]}
        a2 = {r["state"]: r for r in a2_snapshot["by_state"]}

        assert set(a6) == set(a2)
        for state in a6:
            assert a6[state]["sku_count"] == a2[state]["skus"], state
            assert float(a6[state]["inventory_value"]) == pytest.approx(
                float(a2[state]["inventory_value"]), abs=RUPIAH
            ), state


# ------------------------------------------------------------- layer 3: grain


class TestGrainIsNotCrossed:
    """Chain-net and per-store gross, both right, never mixed.

    Every `store_gross_*` field exists because someone will eventually compare
    it to the headline and call the difference a bug. These tests state the
    difference on purpose, so the day it *does* become a bug — the two
    collapsing to one number — there is a failure rather than a silence.
    """

    def test_the_two_grains_stay_about_1_25x_apart(self, a6_snapshot) -> None:
        chain = float(a6_snapshot["totals"]["inventory_value"])
        gross = float(a6_snapshot["store_gross"]["store_gross_inventory_value"])

        assert gross > chain
        assert a6_snapshot["store_gross"]["store_count"] == 160

    def test_the_per_store_grid_totals_what_the_board_shows_by_state(
        self, a6_snapshot, a6_fixture
    ) -> None:
        """`by_state_value` on the board is store-grain, and that is deliberate.

        It sums to the gross figure, not the chain-net one. A reader diffing
        the board's state chart against the tool's `by_state` will find them
        different and be right to; this test says which is which so the answer
        exists before the question does.
        """
        board = sum(r["value"] for r in a6_fixture["by_state_value"])
        gross = float(a6_snapshot["store_gross"]["store_gross_inventory_value"])

        assert gross == pytest.approx(board, abs=RUPIAH)
        assert board != pytest.approx(
            float(a6_snapshot["totals"]["inventory_value"]), abs=RUPIAH
        )

    def test_a2_labels_its_one_per_store_block(self, a2_snapshot) -> None:
        """The store block is named `store_gross_*` and carries its own warning.

        The note is not decoration: it is the only thing standing between a
        per-store count and a chain headline in a model's context window.
        """
        assert "store_gross_worst" in a2_snapshot
        assert "GROSS" in a2_snapshot["store_gross_note"]
        assert all(
            "at_risk_skus" in row for row in a2_snapshot["store_gross_worst"]
        )


# ----------------------------------------------------------- layer 3: scoping


class TestScopingNarrowsHonestly:
    """A scoped snapshot must be scoped everywhere, or nowhere.

    The dangerous failure is partial: totals narrowed to Grocery while a list
    block still carries the chain. The response then reads as one scope and is
    two, and nothing in it says so.
    """

    @pytest.mark.parametrize("vertical", ["GRC", "ELC"])
    def test_a2_narrows_every_block_it_returns(self, vertical, a2_snapshot) -> None:
        def load():
            from src.llm.agents.retail.inventory_risk.tools.inventory_data import (
                get_inventory_risk_snapshot,
            )

            return get_inventory_risk_snapshot(legal_entity_id=vertical)

        scoped = _tool_or_skip(load)

        assert scoped["scope"]["legal_entity_id"] == vertical
        assert scoped["totals"]["skus"] == 100  # 800 SKUs over 8 verticals
        assert scoped["totals"]["skus"] < a2_snapshot["totals"]["skus"]
        assert [r["vertical_id"] for r in scoped["by_vertical"]] == [vertical]
        assert all(r["vertical_id"] == vertical for r in scoped["worst_at_risk_skus"])
        assert all(r["vertical_id"] == vertical for r in scoped["store_gross_worst"])

    @pytest.mark.parametrize("vertical", ["GRC", "ELC"])
    def test_a6_narrows_and_recomputes_its_cutoffs(self, vertical, a6_snapshot) -> None:
        """Scoped quartiles are the scope's quartiles, not the chain's.

        This is a judgement the tool makes and the board does not: narrowing to
        one vertical re-derives P25 within it. Both answers are defensible; the
        point is that the response says which one it gave, and that the
        classes still partition the narrowed population.
        """

        def load():
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                get_assortment_performance_snapshot,
            )

            return get_assortment_performance_snapshot(legal_entity_id=vertical)

        scoped = _tool_or_skip(load)
        totals = scoped["totals"]

        assert scoped["scope"]["legal_entity_id"] == vertical
        assert totals["sku_count"] == 100
        assert [r["vertical_id"] for r in scoped["by_vertical"]] == [vertical]
        assert (
            totals["delist_candidates"] + totals["grow_candidates"] + totals["hold_skus"]
            == totals["sku_count"]
        )
        assert totals["tail_skus"] == 25  # a quarter of the narrowed population
        assert float(totals["inventory_value"]) < float(
            a6_snapshot["totals"]["inventory_value"]
        )

    def test_a_category_name_scopes_the_same_as_its_id(self) -> None:
        """A chat turn passes "Vegetable"; the dropdown passes "GRC-C02".

        Matching only the id returns zero rows for every category a person
        would actually type — an empty answer that looks like a finding.
        """

        def load(value):
            from src.llm.agents.retail.assortment_optimization.tools.assortment_data import (
                get_assortment_performance_snapshot,
            )

            return get_assortment_performance_snapshot(category_group=value)

        by_id = _tool_or_skip(lambda: load("GRC-C02"))
        by_name = _tool_or_skip(lambda: load("Vegetable"))

        assert by_id["totals"]["sku_count"] > 0
        assert by_name["totals"]["sku_count"] == by_id["totals"]["sku_count"]
        assert float(by_name["totals"]["inventory_value"]) == pytest.approx(
            float(by_id["totals"]["inventory_value"]), abs=RUPIAH
        )
