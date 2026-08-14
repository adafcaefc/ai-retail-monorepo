"""Navigation-only Retail modules: the sidebar entry before the board exists.

Agents 4 through 9 of the mockup (`AI_360_Retail_Suite_v8.2_General_9Agents
20260806.html`) are named, ordered and reachable here, but nothing behind them
is built: no domain tools, no chat config, no monitoring passes, no Postgres
read. They exist so the suite's shape is visible and so the build order argued
in the roadmap has somewhere to land.

They are `dashboard_only=True` on purpose. That flag is the one switch that
keeps the backend from offering chat, monitoring, actions and data controls for
a module (`api/agents_html.py`, `frontend/src/App.jsx`,
`monitoring/MonitoringProvider.jsx`). A half-wired agent that answers questions
from no data is worse than one that says plainly it is not built yet — which is
exactly the state Agents 1-3 were in before their boards landed, recorded then
in `tests/test_retail_module.py` and inverted when they became real.

Filling one in means the reverse of this file: give it a folder with `tools/`,
`config/` and `dashboard.py`, then replace its `navigation_module(...)` call
with a full `AgentDescriptor`.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope
from src.llm.agents.descriptor import AgentDescriptor

# Nothing is narrowed, so nothing is claimed. Every filter a request sends comes
# back in `ignored_filters` — the honest answer while there are no rows to
# narrow. Same reasoning as `retail/retail/dashboard.py`.
SUPPORTED_FILTERS: frozenset[str] = frozenset()


def build_empty(agent: str) -> Any:
    """A structurally valid empty dashboard payload for `agent`.

    Returned by every module below, so a client that calls
    `GET /api/html/dashboard/{agent}` early gets empty panels rather than a
    parse error or a 500.
    """

    def build(_scope: DashboardScope | None = None) -> dict[str, Any]:
        return {
            "agent": agent,
            "default_view": "",
            "kpis": [],
            "views": {},
            "side": {},
            "filters": [],
            "simulator": None,
        }

    return build


def navigation_module(
    *,
    agent_id: str,
    display: str,
    description: str,
    prompt: str,
    starter_prompts: tuple[str, ...],
) -> AgentDescriptor:
    """One sidebar destination with nothing wired behind it yet.

    Every chivon key, tool map and data-plumbing name is left empty rather than
    pointed at a plausible-looking string. `populate_alerts` and
    `simulate_action` resolve those by name at runtime, so a guess here would
    surface later as a prefetch that silently returns None — the empty string
    fails loudly instead, and `dashboard_only` means nothing reaches for it.
    """
    folder, _, name = agent_id.partition(".")

    return AgentDescriptor(
        id=agent_id,
        folder=folder,
        name=name,
        display=display,
        description=description,
        prompt=prompt,
        starter_prompts=starter_prompts,
        chat_agent="",
        simulation_agent="",
        action_agent="",
        monitoring_passes=(),
        db_domain="",
        snapshot_tool="",
        schema_tool="",
        import_agent_name="",
        allowed_tables=(),
        tools={},
        build_dashboard=build_empty(agent_id),
        supported_filters=SUPPORTED_FILTERS,
        dashboard_only=True,
    )


__all__ = ["SUPPORTED_FILTERS", "build_empty", "navigation_module"]
