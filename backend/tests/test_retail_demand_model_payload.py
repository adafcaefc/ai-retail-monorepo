"""The demand model the Retail boards need in every payload, without a database.

WHY THIS FILE EXISTS
`test_retail_dashboard_builders.py` already compares the API payload against
each board's fixture block for block, which covers exactly this. It also
`pytest.skip`s the moment no seeded retail database is reachable — and on a
checkout with no database, that is every one of its assertions.

That is how the gap this file guards actually shipped. Inventory Risk's
projection was taught to burn a shaped daily curve, the fixture builder was
taught to carry the shape, the frontend was given a flat fallback for providers
that ship none — and the API path was left shipping none. Every test stayed
green: the frontend suite pins `MODE === "test"` to the fixture, and the
builder comparison skipped. The board drew a straight line where a measured
week should have been, and nothing said so.

Everything asserted here is a pure function. No connection, no fixtures, no
skip — so these run on any checkout, which is the whole point.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.agents.retail.common.warehouse import (  # noqa: E402
    DOW_PROFILE,
    DOW_SUM,
    MONTH_INDEX,
    MONTH_LABELS,
    constants,
    seasonal_indices,
)


class TestConstants:
    """What every board receives before it spends a single day of demand."""

    def test_carries_the_week_shape_and_not_only_its_total(self) -> None:
        """The regression this file is named for.

        A payload with `dow_sum` alone lets a board assume a flat week, which
        is precisely the assumption Inventory Risk's projection was changed to
        stop making. The shape has to travel with the total.
        """
        payload = constants()

        assert "dow_profile" in payload, (
            "constants() must ship dow_profile; without it the browser falls "
            "back to a flat week and the projection draws a straight line"
        )
        assert len(payload["dow_profile"]) == 7
        assert payload["dow_sum"] == DOW_SUM
        assert payload["month_index"] == MONTH_INDEX

    def test_the_seven_factors_reproduce_the_workbook_week(self) -> None:
        """`Constants` B7 is measured; the seven factors only allocate it.

        f08 multiplies a daily rate by 7.45 to get a week. If these stop
        summing to that, a daily view no longer rolls up to the weekly figure
        the sheet publishes, and the two boards begin disagreeing with the
        workbook rather than with each other — which is harder to notice.
        """
        assert sum(DOW_PROFILE) == DOW_SUM

    def test_is_json_safe(self) -> None:
        """A tuple survives Python and dies at the response boundary."""
        assert isinstance(constants()["dow_profile"], list)


class TestSeasonalIndices:
    """Twelve classical indices, and what happens when there is nothing to index."""

    def test_indexes_each_month_against_the_series_mean(self) -> None:
        # A flat year indexes to 100 everywhere by definition.
        assert seasonal_indices(dict.fromkeys(range(12), 500.0)) == [100.0] * 12

        # One month at double the rest lifts only that month, and lifts it by
        # the ratio to the mean rather than to its neighbours.
        months = dict.fromkeys(range(12), 100.0)
        months[6] = 200.0
        indices = seasonal_indices(months)
        assert indices[6] == max(indices)
        # Classical indices average to 100 by construction. Not exactly here:
        # each is rounded to four places before it lands in the payload, so the
        # mean carries that rounding rather than the definition's zero.
        assert abs(sum(indices) / 12 - 100.0) < 1e-3

    def test_falls_back_flat_rather_than_dividing_by_zero(self) -> None:
        """An empty or all-zero series is a missing profile, not a crash.

        The board can honestly draw no seasonality; it cannot honestly draw a
        NaN, and it must not raise on the way to the response.
        """
        assert seasonal_indices({}) == [100.0] * 12
        assert seasonal_indices(dict.fromkeys(range(12), 0.0)) == [100.0] * 12

    def test_labels_cover_a_year_and_the_current_month_is_one_of_them(self) -> None:
        assert len(MONTH_LABELS) == 12
        assert 0 <= MONTH_INDEX < 12
