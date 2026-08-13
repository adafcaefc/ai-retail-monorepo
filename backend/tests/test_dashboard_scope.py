"""The dashboard scope: what a request asks for, and what it is told it got."""

from __future__ import annotations

import pytest

from src.llm.agents import AGENT_REGISTRY
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.modules import ENABLED_MODULES


class TestNormalisation:
    def test_everything_defaults_to_no_filter(self) -> None:
        scope = DashboardScope()

        assert scope.applied() == ()
        assert scope.as_query() == {}

    @pytest.mark.parametrize("cleared", ["ALL", "", "  "])
    def test_the_dropdowns_clear_option_means_no_filter(self, cleared: str) -> None:
        """"ALL" is what the UI's own clear option round-trips as.

        Matching it against a real column would match nothing, which is the
        opposite of what the reader asked for — they cleared the filter.
        """
        scope = DashboardScope.from_query(legal_entity_id=cleared, store_id=cleared)

        assert scope.legal_entity_id is None
        assert scope.applied() == ()

    def test_a_real_value_survives(self) -> None:
        scope = DashboardScope.from_query(legal_entity_id="GRC", route="direct")

        assert scope.legal_entity_id == "GRC"
        assert scope.route == "direct"
        assert scope.applied() == ("legal_entity_id", "route")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("true", True), ("1", True), ("on", True), ("false", False), ("0", False),
         ("", False), (None, False), (True, True), (False, False)],
    )
    def test_booleans_arrive_as_text_and_must_not_all_be_true(
        self, raw: object, expected: bool
    ) -> None:
        """`reorder_only=false` is a non-empty string, and so is truthy.

        Left to Python's own truthiness this would filter the board to the
        reorder list while the checkbox showed unchecked.
        """
        assert DashboardScope.from_query(reorder_only=raw).reorder_only is expected

    def test_a_false_boolean_is_not_an_applied_filter(self) -> None:
        # `reorder_only=False` is the default, not a request to narrow.
        assert DashboardScope.from_query(reorder_only=False).applied() == ()
        assert DashboardScope.from_query(reorder_only=True).applied() == ("reorder_only",)


class TestUnknownFilters:
    def test_a_misspelt_filter_raises_rather_than_being_ignored(self) -> None:
        """The failure this whole module exists to prevent.

        A caller sending `store` when the field is `store_id` used to get a
        clean 200 carrying chain-wide figures under a per-store heading. There
        is no way to notice that from the client side.
        """
        with pytest.raises(ValueError, match="Unknown dashboard filter"):
            DashboardScope.from_query(store="ST-001")

    def test_the_error_names_both_the_mistake_and_the_alternatives(self) -> None:
        with pytest.raises(ValueError) as error:
            DashboardScope.from_query(entity="GRC", stores="ST-001")

        message = str(error.value)
        assert "entity, stores" in message
        assert "store_id" in message
        assert "legal_entity_id" in message


class TestIgnoredFilters:
    def test_an_agent_that_cannot_narrow_says_so(self) -> None:
        scope = DashboardScope.from_query(
            legal_entity_id="EYDS", period="2026-03-01", store_id="ST-001"
        )

        # Treasury's baseline is a position with no month and no store.
        assert scope.ignored_by(frozenset({"legal_entity_id"})) == (
            "period",
            "store_id",
        )

    def test_nothing_is_reported_when_everything_applied(self) -> None:
        scope = DashboardScope.from_query(legal_entity_id="EYDS")

        assert scope.ignored_by(frozenset({"legal_entity_id", "period"})) == ()

    def test_every_registered_agent_declares_only_real_fields(self) -> None:
        """A `supported_filters` typo would silently promise a filter forever.

        Nothing would fail: the name simply never matches an applied filter, so
        the agent claims to honour something it is never asked for and quietly
        ignores the one it is.
        """
        known = set(DashboardScope().__dataclass_fields__)

        for agent_id in ENABLED_MODULES:
            supported = AGENT_REGISTRY[agent_id].supported_filters
            assert supported <= known, f"{agent_id} declares unknown filters"
