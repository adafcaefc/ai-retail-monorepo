"""Agent descriptor: the single source of truth for one domain agent.

Each agent folder (`agents/<folder>/<name>/__init__.py`) exposes a
`DESCRIPTOR`. The registry (`agents/__init__.py`) loads the ones listed in
`agents/modules.py`, so adding an agent means adding a folder plus its id
there. The descriptor also carries the frontend presentation strings, so the
UI never has to restate them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class MonitoringPass:
    agent_name: str
    instructions: str


@dataclass(frozen=True)
class AgentDescriptor:
    # Public identity
    id: str                       # canonical id, e.g. "finance.treasury"
    folder: str                   # "finance"
    name: str                     # "treasury"
    display: str                  # "Treasury"

    # Frontend presentation (served by GET /api/html/agents)
    description: str              # one-line sidebar/board blurb
    prompt: str                   # composer placeholder
    starter_prompts: tuple[str, ...]

    # Chivon agent keys
    chat_agent: str               # "finance.treasury.chat"
    simulation_agent: str         # "finance.treasury.simulation"
    action_agent: str             # "finance.treasury.action"
    monitoring_passes: tuple[MonitoringPass, ...]

    # Data plumbing
    db_domain: str                # freeform-query table-scope key ("cashflow")
    snapshot_tool: str            # "get_cashflow_baseline"
    schema_tool: str              # "describe_cashflow_tables"
    import_agent_name: str        # audit.import_batches agent_name (unchanged)
    allowed_tables: tuple[str, ...]

    # Callables
    tools: dict[str, Callable]    # domain-specific tools (merged into LOCAL_TOOLS)
    build_dashboard: Callable[[], dict]

    # Backend capability
    # Dashboard-only modules may reuse the shared header and chat presentation,
    # but the frontend must not invoke chat, monitoring, actions, or data APIs.
    dashboard_only: bool = False


__all__ = ["AgentDescriptor", "MonitoringPass"]
