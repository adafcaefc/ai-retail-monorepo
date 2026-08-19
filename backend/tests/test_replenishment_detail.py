"""Agent 3.1 · Replenishment Detail: the line arithmetic and its guard rails.

Database-free. `build_lines` is pure, so the reorder rule, the UOM conversion,
the tie-out checks and the eligibility rules can all be exercised against the
spec's own worked example (section 13, workbook row 6) without a seeded
warehouse. That example is the anchor: if these numbers stop reproducing it,
the board is no longer showing what the workbook shows.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.llm.agents.retail.replenishment_detail import dashboard as d


# Spec section 13, workbook row 6. Every field is the sheet's own value, so a
# change to `build_lines` that alters any derived figure fails against a
# published example rather than against a number this file invented.
GRC_001: dict[str, Any] = {
    "item_key": "GRC-001",
    "name": "Fruit 1",
    "vertical_id": "GRC",
    "category_id": "GRC-C01",
    "category_name": "Fruit",
    "qty_on_hand": 1151,
    "open_po_qty": 25,
    "demand_per_day": 496.869179208,
    "rop_qty": 1491,
    "max_qty": 3478,
    "is_reorder": True,
    "order_qty_sales": 2302,
    "order_qty_buy": 192,
    "buy_uom": "Crate",
    "pack_factor": 12,
    "unit_price_ta": 14300,
    "amount": 32947200,
    "best_price": 14300,
    "saving_vs_designated": 0,
    "lead_time_days": 2,
    "designated_short": "Vendor E",
    "best_short": "Vendor E",
}


def line(**overrides: Any) -> dict[str, Any]:
    """One built line, from the worked example with fields overridden."""
    return d.build_lines([{**GRC_001, **overrides}])[0]


class TestTheWorkedExample:
    """Spec section 13's calculation trace, step by step."""

    def test_position_is_reconstructed_from_its_components(self) -> None:
        # Position is not a stored column. 1,151 + 25 = 1,176.
        assert line()["position"] == 1176

    def test_reorder_holds_because_position_is_below_rop(self) -> None:
        built = line()
        assert built["position"] < built["rop"]
        assert built["is_reorder"] is True

    def test_the_raw_requirement_is_max_minus_position(self) -> None:
        # 3,478 - 1,176 = 2,302, which is what the sheet stores as order sales.
        built = line()
        assert built["required_qty_sales"] == 2302
        assert built["order_qty_sales"] == 2302

    def test_the_buy_quantity_is_a_ceiling_against_the_pack_factor(self) -> None:
        # CEILING(2,302 / 12) = 192 Crates, not 191.83.
        built = line()
        assert built["packs_required_exact"] == pytest.approx(2302 / 12)
        assert built["order_qty_buy"] == 192

    def test_ordered_units_exceed_the_requirement_by_the_uplift(self) -> None:
        # 192 x 12 = 2,304, which is two units above the 2,302 required.
        built = line()
        assert built["ordered_sales_units"] == 2304
        assert built["rounding_uplift"] == 2

    def test_amount_prices_the_rounded_quantity_at_the_sales_unit_price(self) -> None:
        # 2,304 x Rp14,300 = Rp32,947,200. Pricing the 192 Crates directly
        # would give Rp2,745,600 -- the twelvefold error the module warns about.
        built = line()
        assert built["amount"] == 32947200
        assert built["order_qty_buy"] * built["unit_price_ta"] != built["amount"]

    def test_no_saving_when_the_designated_vendor_is_already_best(self) -> None:
        built = line()
        assert built["saving_vs_designated"] == 0
        assert built["saving_pct"] == 0.0
        assert built["has_alternate_vendor"] is False

    def test_the_example_line_is_clean_and_actionable(self) -> None:
        built = line()
        assert built["exception_codes"] == []
        assert built["action_eligibility"] == "ELIGIBLE"


class TestTheReorderRuleIsStrict:
    """Spec section 6.2: `Position = ROP` does not trigger a reorder."""

    def test_position_equal_to_rop_is_not_a_reorder(self) -> None:
        # The sheet stores the flag; this asserts the boundary it was set at,
        # so a future move to deriving it here cannot quietly use `<=`.
        built = line(qty_on_hand=1466, open_po_qty=25, rop_qty=1491, is_reorder=False)

        assert built["position"] == built["rop"]
        assert built["is_reorder"] is False
        assert built["action_eligibility"] == "NO_ORDER"


class TestSavingIsPricedOnTheRoundedQuantity:
    """Spec section 6.7, and the error it is easiest to make."""

    def test_saving_uses_ordered_units_not_the_buy_count(self) -> None:
        # Best price Rp14,000 against a designated Rp14,300: a Rp300 delta over
        # 2,304 ordered sales units is Rp691,200. Over 192 Crates it would be
        # Rp57,600 -- the same twelvefold error, in the other column.
        built = line(best_price=14000, best_short="Vendor A", saving_vs_designated=691200)

        assert built["exception_codes"] == []
        assert built["has_alternate_vendor"] is True
        assert built["saving_pct"] == pytest.approx(691200 / 32947200 * 100)

    def test_a_saving_priced_on_buy_units_fails_tie_out(self) -> None:
        built = line(best_price=14000, best_short="Vendor A", saving_vs_designated=57600)

        assert "FORMULA_TIE_OUT_FAILED" in built["exception_codes"]
        assert built["action_eligibility"] == "BLOCKED"

    def test_saving_pct_is_guarded_when_there_is_no_amount(self) -> None:
        built = line(
            is_reorder=False,
            order_qty_sales=0,
            order_qty_buy=0,
            amount=0,
            saving_vs_designated=0,
        )

        assert built["saving_pct"] == 0.0


class TestExceptionCodes:
    """Spec section 14. Each rule, and the cases it must not fire on."""

    def test_missing_pack_factor_only_matters_when_there_is_an_order(self) -> None:
        assert "MISSING_PACK_FACTOR" in line(pack_factor=0)["exception_codes"]

        resting = line(
            pack_factor=0,
            is_reorder=False,
            order_qty_sales=0,
            order_qty_buy=0,
            amount=0,
        )
        assert "MISSING_PACK_FACTOR" not in resting["exception_codes"]

    def test_missing_buy_uom_is_flagged_for_blank_as_well_as_null(self) -> None:
        assert "MISSING_BUY_UOM" in line(buy_uom=None)["exception_codes"]
        assert "MISSING_BUY_UOM" in line(buy_uom="   ")["exception_codes"]

    def test_missing_vendor_survives_the_left_join(self) -> None:
        # The vendor join is a LEFT JOIN precisely so this row reaches the
        # board instead of vanishing from it.
        assert "MISSING_VENDOR" in line(designated_short=None)["exception_codes"]

    def test_missing_trade_agreement_price(self) -> None:
        built = line(unit_price_ta=0, amount=0)

        assert "MISSING_TA_PRICE" in built["exception_codes"]

    def test_max_below_rop_is_invalid(self) -> None:
        assert "INVALID_ROP_MAX" in line(max_qty=1000)["exception_codes"]
        assert "INVALID_ROP_MAX" in line(rop_qty=-1)["exception_codes"]

    def test_max_equal_to_rop_is_allowed(self) -> None:
        # Spec section 5: "Max must be greater than or equal to ROP".
        built = line(rop_qty=3478, max_qty=3478)

        assert "INVALID_ROP_MAX" not in built["exception_codes"]

    def test_negative_inventory_input(self) -> None:
        assert "NEGATIVE_INVENTORY_INPUT" in line(open_po_qty=-5)["exception_codes"]

    def test_a_stored_amount_that_does_not_reconcile(self) -> None:
        built = line(amount=99_999_999)

        assert "FORMULA_TIE_OUT_FAILED" in built["exception_codes"]

    def test_rounding_noise_does_not_trip_tie_out(self) -> None:
        # The workbook rounds currency to whole rupiah in places, so a one-
        # rupiah difference must not be reported as a broken calculation.
        built = line(amount=32947200 + d.TIE_OUT_TOLERANCE_IDR)

        assert "FORMULA_TIE_OUT_FAILED" not in built["exception_codes"]

    def test_every_code_the_module_publishes_is_reachable(self) -> None:
        """A code in the list that nothing can raise is a check nobody runs."""
        raised = set()
        for built in (
            line(pack_factor=0),
            line(buy_uom=None),
            line(designated_short=None),
            line(unit_price_ta=0, amount=0),
            line(max_qty=1000),
            line(open_po_qty=-5),
            line(amount=99_999_999),
        ):
            raised.update(built["exception_codes"])

        assert raised == set(d.EXCEPTION_CODES)


class TestActionEligibility:
    """Spec section 10.1, and the distinction that keeps the queue readable."""

    def test_a_line_with_nothing_to_buy_is_not_an_exception(self) -> None:
        built = line(
            is_reorder=False,
            order_qty_sales=0,
            order_qty_buy=0,
            amount=0,
            saving_vs_designated=0,
        )

        assert built["exception_codes"] == []
        assert built["action_eligibility"] == "NO_ORDER"

    def test_no_order_wins_over_a_data_problem(self) -> None:
        # A resting line with a missing vendor is still not something a planner
        # can act on today, and filing it under BLOCKED would inflate the queue
        # with lines that need no order either way.
        built = line(
            is_reorder=False,
            order_qty_sales=0,
            order_qty_buy=0,
            amount=0,
            designated_short=None,
        )

        assert built["exception_codes"] == ["MISSING_VENDOR"]
        assert built["action_eligibility"] == "NO_ORDER"

    def test_any_exception_blocks_an_otherwise_orderable_line(self) -> None:
        assert line(buy_uom=None)["action_eligibility"] == "BLOCKED"

    def test_a_reorder_line_that_converts_to_nothing_is_blocked(self) -> None:
        built = line(order_qty_buy=0, amount=0, saving_vs_designated=0)

        assert built["action_eligibility"] == "BLOCKED"


class TestTheModuleStandsOnItsOwn:
    def test_it_declares_only_the_filters_its_sql_applies(self) -> None:
        assert d.SUPPORTED_FILTERS == frozenset({"legal_entity_id", "category_group"})

    def test_it_does_not_read_the_chain_inventory_fact(self) -> None:
        """Its own sheet, its own query.

        `replenishment_proposal` IS the `Replenishment Detail` worksheet and
        carries all nineteen fields. Joining the chain fact would pull in
        columns nothing on this board renders.
        """
        assert "fact_inventory_chain_daily" not in d.LINES_SQL
        assert "fact_inventory_daily" not in d.LINES_SQL
        assert "replenishment_proposal" in d.LINES_SQL

    def test_the_scope_clause_placeholder_survives_formatting(self) -> None:
        # `LINES_SQL` is a formatted f-string with a doubled brace, so this
        # guards the one thing that silently breaks: a `{where}` that got
        # interpolated at definition time and can no longer take a scope.
        assert "{where}" in d.LINES_SQL
        assert ":day" in d.LINES_SQL.format(where=" AND i.vertical_id = :entity")
