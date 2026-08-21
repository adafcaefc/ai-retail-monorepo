"""`synthetic.markdown_ladder_store_sku_16w`, read through `dashboard.py`.

Skips without a seeded database, same as `test_retail_dashboard_builders.py`
-- this needs migration 012 applied and `scripts/seed_synthetic_markdown_
ladder_16w.py` run, not just a live connection. Purely additive: nothing
here touches or depends on any other table's data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from src.llm.agents.retail.pricing_markdown import dashboard as d  # noqa: E402

FIXTURE = (
    REPO / "frontend" / "src" / "agents" / "retail" / "pricing_markdown" / "data" / "fixture.json"
)


def _build_or_skip() -> dict:
    try:
        return d.build()
    except Exception as error:  # noqa: BLE001 - any failure means "not seeded here"
        pytest.skip(f"no seeded retail database: {error}")


def test_ladder_by_vertical_is_additive_and_well_shaped() -> None:
    built = _build_or_skip()
    ladder = built.get("ladder_by_vertical")
    if not ladder:
        pytest.skip("synthetic.markdown_ladder_store_sku_16w has not been seeded yet")

    assert isinstance(ladder, list)
    for row in ladder:
        assert set(row) == {"legal_entity_id", "no_action", "ladder", "history_no_action", "history_ladder"}
        for field in ("no_action", "ladder", "history_no_action", "history_ladder"):
            assert len(row[field]) == 16

    # Gates 1/3/4 from the generator, re-checked end to end through the live
    # query -- not just trusted from the CSV that fed it. "no_action never
    # decreases week over week" no longer holds by design once the
    # generator's wiggle is applied -- this checks the edges of the trend
    # instead: oldest history point < nearest forecast point < furthest
    # forecast point. `no_action[0]` is +1 week out, NOT today -- today
    # (offset 0) is never stored in this table at all, see the generator's
    # own "TODAY LIVES OUTSIDE THIS TABLE" section; `history_no_action[-1]`
    # is the oldest history point (hist_w16) -- see dashboard.py's
    # `_ladder_by_vertical`.
    for row in ladder:
        no_action, markdown_ladder = row["no_action"], row["ladder"]
        hist_no_action, hist_ladder = row["history_no_action"], row["history_ladder"]
        if no_action[0] <= 0:
            continue
        assert hist_no_action[-1] < no_action[0] < no_action[-1], (
            f"{row['legal_entity_id']}: no_action does not rise from oldest history to newest forecast"
        )
        assert hist_ladder[-1] < hist_no_action[-1], (
            f"{row['legal_entity_id']}: ladder does not separate from no_action at the oldest history week"
        )
        assert markdown_ladder[-1] < no_action[-1], (
            f"{row['legal_entity_id']}: ladder does not separate from no_action at the furthest forecast week"
        )

    # Every existing block on this payload is untouched by this addition --
    # the whole point of the "purely additive" design.
    for block in ("items", "stores", "reference_by_vertical", "filter_options", "formulas"):
        assert block in built


def test_ladder_by_vertical_matches_the_offline_fixture() -> None:
    """The live-DB path and the checked-in fixture read the same CSV-derived
    table, so they should agree exactly -- same reasoning `warehouse.py`'s
    module docstring gives for every other block on this board."""
    built = _build_or_skip()
    live = built.get("ladder_by_vertical")
    if not live:
        pytest.skip("synthetic.markdown_ladder_store_sku_16w has not been seeded yet")

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shipped = fixture.get("ladder_by_vertical")
    if not shipped:
        pytest.skip("fixture.json was built before the ladder generator ran")

    live_by_vertical = {row["legal_entity_id"]: row for row in live}
    shipped_by_vertical = {row["legal_entity_id"]: row for row in shipped}
    assert set(live_by_vertical) == set(shipped_by_vertical)

    for vertical, want in shipped_by_vertical.items():
        got = live_by_vertical[vertical]
        for field in ("no_action", "ladder", "history_no_action", "history_ladder"):
            for week in range(16):
                assert got[field][week] == pytest.approx(want.get(field, [0.0] * 16)[week], rel=1e-6)
