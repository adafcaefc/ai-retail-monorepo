"""Retail modules: agent wiring, dashboards, and the filters they apply."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.api.agents_html import list_agents
from src.llm.agents import AGENT_REGISTRY, LOCAL_TOOLS
from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.common.tools.freeform_query import DOMAIN_ALLOWED_TABLES
from src.llm.agents.modules import ENABLED_MODULES


# The mockup's retail destinations that are switched on, in sidebar order, each
# flagged with whether anything is wired behind it. Eight of the mockup's nine:
# A9 is hidden (docs/DISABLED_FEATURES.md) and sits commented out below rather
# than deleted, so bringing it back is one uncomment here and one in
# modules.py. Built and navigation-only are two contiguous blocks again now
# that A5 has caught up with A6, but the flag stays per entry rather than a
# prefix slice: they came apart once already, and order has to stay the agent's
# own number because that is what the sidebar shows and what every spec refers
# to. `modules.py` carries the same note beside the same list.
RETAIL_DESTINATIONS = (
    ("retail.demand_forecasting", "Demand Forecasting", "Ask Demand...", True),
    ("retail.inventory_risk", "Inventory Risk", "Ask Inventory...", True),
    ("retail.replenishment", "Replenishment", "Ask Replenishment...", True),
    (
        "retail.replenishment_detail",
        "Replenishment Detail",
        "Ask Replenishment Detail...",
        True,
    ),
    (
        "retail.promotion_effectiveness",
        "Promotion Effectiveness",
        "Ask Promotion...",
        True,
    ),
    ("retail.pricing_markdown", "Pricing & Markdown", "Ask Pricing...", True),
    (
        "retail.assortment_optimization",
        "Assortment Optimization",
        "Ask Assortment...",
        True,
    ),
    ("retail.workforce_optimizer", "Workforce Optimizer", "Ask Workforce...", False),
    (
        "retail.vendor_brand_performance",
        "Vendor & Brand Performance",
        "Ask Vendor...",
        False,
    ),
    # Hidden -- see docs/DISABLED_FEATURES.md to re-enable.
    # (
    #     "retail.ai_explanation_summary",
    #     "AI Explanation & Summary",
    #     "Ask Summary...",
    #     False,
    # ),
)

# Both keep the sidebar's order; only the filter differs. Derived rather than
# retyped, so a module cannot read as built in one list and a placeholder in
# the other.
RETAIL_MODULES = tuple(d[:3] for d in RETAIL_DESTINATIONS if d[3])
PLACEHOLDER_MODULES = tuple(d[:3] for d in RETAIL_DESTINATIONS if not d[3])

# Three specialists per board. Fewer than Finance's four, so the concerns the
# fourth would have carried are folded into a sibling and named in its
# `instructions` -- seasonality into trend, capital concentration into
# overstock, approval tiers into sourcing.
PASSES_PER_MODULE = 3


def test_retail_folder_carries_every_destination_in_order() -> None:
    """Seven built, two navigation-only, in the mockup's sidebar order.

    This asserted exactly three modules while Agents 4-9 did not exist. They
    are now reachable, which is the point of the change rather than a
    loosening of the check: the list below is the mockup's own order, so a
    module added out of sequence fails here.
    """
    retail = [item for item in ENABLED_MODULES if item.startswith("retail.")]

    assert retail == [item[0] for item in RETAIL_DESTINATIONS]
    assert "retail.retail" not in ENABLED_MODULES


def test_retail_modules_are_fully_wired_agents() -> None:
    """These were navigation scaffolds; they are now chat + monitoring agents.

    This test previously asserted the opposite -- `dashboard_only is True`,
    no chat agent, no passes, no tools. That was an accurate record of a
    deliberate half-built state, and inverting it is the point of the change,
    not a workaround for it.
    """
    for agent_id, display, prompt in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        assert descriptor.folder == "retail"
        assert descriptor.display == display
        assert descriptor.prompt == prompt
        assert descriptor.starter_prompts, f"{agent_id} has no starter prompts"

        # The one flag that turns on chat, alerts and the subagent panel in
        # the frontend (`App.jsx`, `MonitoringProvider.jsx`).
        assert descriptor.dashboard_only is False
        assert descriptor.chat_agent == f"{agent_id}.chat"
        assert descriptor.simulation_agent == f"{agent_id}.simulation"
        assert descriptor.action_agent == f"{agent_id}.action"


def test_each_retail_module_has_three_monitoring_specialists() -> None:
    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        passes = descriptor.monitoring_passes

        assert len(passes) == PASSES_PER_MODULE, (
            f"{agent_id} declares {len(passes)} passes"
        )
        for monitoring_pass in passes:
            assert monitoring_pass.agent_name.startswith(f"{agent_id}.monitoring."), (
                f"{monitoring_pass.agent_name} is not namespaced under {agent_id}"
            )
            # An empty instruction is a pass that will hunt for nothing in
            # particular, which is worse than no pass at all.
            assert monitoring_pass.instructions.strip()

    names = [
        monitoring_pass.agent_name
        for agent_id, _, _ in RETAIL_MODULES
        for monitoring_pass in AGENT_REGISTRY[agent_id].monitoring_passes
    ]
    assert len(names) == len(set(names)) == len(RETAIL_MODULES) * PASSES_PER_MODULE


def test_each_retail_module_resolves_its_data_plumbing() -> None:
    """Every name the descriptor points at must exist.

    `populate_alerts` and `simulate_action` look these up by string. A typo
    here is not a startup error -- it is a prefetch that silently returns
    None, and a monitoring pass that runs against no snapshot at all.
    """
    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        assert descriptor.db_domain in DOMAIN_ALLOWED_TABLES, (
            f"{agent_id} has db_domain {descriptor.db_domain!r}, which "
            f"simulate_impact cannot resolve an allow-list from"
        )
        assert descriptor.snapshot_tool in LOCAL_TOOLS
        assert descriptor.schema_tool in LOCAL_TOOLS
        assert descriptor.allowed_tables
        assert descriptor.tools

        # The allow-list on the descriptor and the one the domain resolves to
        # must be the same tuple, or the agent is told it may read tables its
        # query tool will refuse.
        assert tuple(descriptor.allowed_tables) == tuple(
            DOMAIN_ALLOWED_TABLES[descriptor.db_domain]
        )


def test_retail_agents_can_emit_a_schema_valid_action() -> None:
    """`ActionSpec.agent` is a Literal, so an unlisted domain fails validation.

    Without this the failure surfaces as a monitoring run that produces
    nothing, one retry later, with the schema error buried in a pass error.
    """
    from src.llm.chivon.loader import get_chivon

    choices = get_chivon().type("ActionSpec").model_fields["agent"].annotation
    allowed = set(getattr(choices, "__args__", ()))

    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        assert descriptor.db_domain in allowed, (
            f"{descriptor.db_domain} is missing from the ActionSpec.agent "
            f"choices in common/config/subagents.json"
        )


def test_every_declared_chivon_agent_exists() -> None:
    """Catches a typo'd config key, which is otherwise a runtime 500."""
    from src.llm.chivon.loader import get_chivon

    loaded = set(get_chivon().agents)

    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        declared = [
            descriptor.chat_agent,
            descriptor.simulation_agent,
            descriptor.action_agent,
            *(item.agent_name for item in descriptor.monitoring_passes),
        ]
        missing = [name for name in declared if name not in loaded]
        assert not missing, f"{agent_id} declares unloaded agents: {missing}"


def test_each_retail_module_has_its_own_builder() -> None:
    """All three used to share one stub that returned an empty payload.

    They now read Postgres, each from its own module. Asserted because the
    shared stub is still on disk (`retail/retail/dashboard.py`) and pointing a
    descriptor back at it would silently empty a board.
    """
    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]
        module = descriptor.build_dashboard.__module__

        assert module.endswith(f"{agent_id.split('.')[1]}.dashboard"), (
            f"{agent_id} builds from {module}"
        )


def test_retail_dashboards_declare_the_filters_they_apply() -> None:
    """Each dashboard declares only the filters its SQL actually applies.

    The board narrows by the others itself, over the rows it is handed — but an
    API caller that is not the board gets told, which is the whole point of
    `ignored_filters`. A filter that appears to work and does nothing is worse
    than one that refuses.
    """
    scope = DashboardScope(legal_entity_id="GRC", store_id="ST-001", reorder_only=True)

    for agent_id, _, _ in RETAIL_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        expected = {"legal_entity_id", "category_group"}
        if agent_id in ("retail.demand_forecasting", "retail.pricing_markdown"):
            expected.add("store_id")

        assert descriptor.supported_filters == frozenset(expected)
        expected_ignored = (
            ("reorder_only",)
            if agent_id in ("retail.demand_forecasting", "retail.pricing_markdown")
            else ("store_id", "reorder_only")
        )
        assert scope.ignored_by(descriptor.supported_filters) == expected_ignored


def test_placeholder_modules_are_navigation_only() -> None:
    """Named and reachable; nothing behind them, and nothing pretending to be.

    Every chivon key and plumbing name is empty rather than a plausible
    string, because `populate_alerts` and `simulate_action` resolve those by
    name at runtime — a guess would surface as a prefetch returning None
    instead of a loud failure. `dashboard_only` is what stops anything
    reaching for them in the first place.
    """
    for agent_id, display, prompt in PLACEHOLDER_MODULES:
        descriptor = AGENT_REGISTRY[agent_id]

        assert descriptor.folder == "retail"
        assert descriptor.display == display
        assert descriptor.prompt == prompt
        assert descriptor.starter_prompts, f"{agent_id} has no starter prompts"

        assert descriptor.dashboard_only is True
        assert descriptor.chat_agent == ""
        assert descriptor.simulation_agent == ""
        assert descriptor.action_agent == ""
        assert descriptor.monitoring_passes == ()
        assert descriptor.db_domain == ""
        assert descriptor.snapshot_tool == ""
        assert descriptor.schema_tool == ""
        assert descriptor.allowed_tables == ()
        assert descriptor.tools == {}
        assert descriptor.supported_filters == frozenset()


def test_placeholder_dashboards_return_a_valid_empty_payload() -> None:
    """A client that calls the dashboard route early gets empty panels.

    Not a 500 and not a parse error — the same contract the built boards
    answer, with nothing in it.
    """
    for agent_id, _, _ in PLACEHOLDER_MODULES:
        payload = AGENT_REGISTRY[agent_id].build_dashboard(DashboardScope())

        assert payload["agent"] == agent_id
        assert payload["kpis"] == []
        assert payload["views"] == {}
        assert payload["filters"] == []
        assert payload["simulator"] is None


def test_placeholder_modules_declare_no_chivon_agents() -> None:
    """The two carry no config JSON, so they must not name one either.

    `test_every_declared_chivon_agent_exists` catches the reverse for the
    built modules; this is the same guard from the empty side.
    """
    for agent_id, _, _ in PLACEHOLDER_MODULES:
        folder, _, name = agent_id.partition(".")
        config_dir = (
            Path(__file__).resolve().parents[1]
            / "src" / "llm" / "agents" / folder / name / "config"
        )

        assert not config_dir.exists(), f"{agent_id} has a config folder"


def test_agents_api_exposes_every_retail_destination() -> None:
    payload = asyncio.run(list_agents())
    retail = [item for item in payload["items"] if item["folder"] == "retail"]

    assert [item["id"] for item in retail] == [
        item[0] for item in RETAIL_DESTINATIONS
    ]
    assert [item["display"] for item in retail] == [
        item[1] for item in RETAIL_DESTINATIONS
    ]
    # This flag is what the frontend reads to show chat, the Alerts panel and
    # the Subagents control: on for the built boards, off for the ones with
    # nothing to answer with. Zipped rather than sliced, because the built
    # modules are no longer a prefix of the sidebar -- a slice would still pass
    # while pairing the wrong module with the wrong flag.
    for item, (agent_id, _, _, is_built) in zip(retail, RETAIL_DESTINATIONS):
        assert item["dashboard_only"] is not is_built, (
            f"{agent_id}: dashboard_only={item['dashboard_only']} "
            f"but built={is_built}"
        )
    assert all(item["id"] != "retail.retail" for item in payload["items"])
