"""Agent registry.

Loads one `AgentDescriptor` per id listed in `modules.ENABLED_MODULES`, from
`agents/<folder>/<name>/__init__.py`, and derives everything the rest of the
app needs from it: the chivon config file list, the flat `LOCAL_TOOLS` map,
and `get_agent()` lookups.

`ENABLED_MODULES` is the single source of truth — a folder that is not listed
is never imported, and its configs never reach chivon. Registry order follows
the constant, which is also the frontend sidebar order.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from src.llm.agents.common.tools import COMMON_TOOLS
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass
from src.llm.agents.modules import ENABLED_MODULES

_HERE = Path(__file__).resolve().parent
_RESERVED = {"common", "__pycache__"}


def _load(agent_id: str) -> AgentDescriptor:
    """Import one enabled module and return its descriptor.

    Every failure is loud: the list is hand-edited, so a typo must not
    degrade into a silently missing agent.
    """
    folder, _, name = agent_id.partition(".")

    if not folder or not name or "." in name:
        raise RuntimeError(
            f"Invalid module id {agent_id!r} in ENABLED_MODULES. "
            f"Expected the canonical form 'folder.agent', e.g. 'finance.treasury'."
        )

    if folder in _RESERVED or name in _RESERVED:
        raise RuntimeError(
            f"Invalid module id {agent_id!r} in ENABLED_MODULES: "
            f"{', '.join(sorted(_RESERVED))} are reserved names."
        )

    agent_dir = _HERE / folder / name
    if not (agent_dir / "__init__.py").exists():
        raise RuntimeError(
            f"Module {agent_id!r} is listed in ENABLED_MODULES but "
            f"{agent_dir}/__init__.py does not exist."
        )

    module = importlib.import_module(f"src.llm.agents.{folder}.{name}")
    descriptor = getattr(module, "DESCRIPTOR", None)

    if not isinstance(descriptor, AgentDescriptor):
        raise RuntimeError(
            f"Module {agent_id!r} does not expose a DESCRIPTOR of type "
            f"AgentDescriptor in {agent_dir}/__init__.py."
        )

    if descriptor.id != agent_id:
        raise RuntimeError(
            f"Module {agent_id!r} exposes a descriptor with id "
            f"{descriptor.id!r}. The folder path and the descriptor id must agree."
        )

    return descriptor


def _discover() -> dict[str, AgentDescriptor]:
    duplicates = sorted(
        {name for name in ENABLED_MODULES if ENABLED_MODULES.count(name) > 1}
    )
    if duplicates:
        raise RuntimeError(
            f"ENABLED_MODULES contains duplicate ids: {', '.join(duplicates)}."
        )

    # Insertion order = ENABLED_MODULES order = sidebar order.
    return {agent_id: _load(agent_id) for agent_id in ENABLED_MODULES}


AGENT_REGISTRY: dict[str, AgentDescriptor] = _discover()


def _config_files() -> list[Path]:
    # Common models/constants must merge before agents that reference them.
    common = sorted((_HERE / "common" / "config").glob("*.json"))
    domain = [
        path
        for descriptor in AGENT_REGISTRY.values()
        for path in sorted(
            (_HERE / descriptor.folder / descriptor.name / "config").glob("*.json")
        )
    ]
    return common + domain


AGENT_CONFIG_FILES: list[Path] = _config_files()


def _local_tools() -> dict:
    tools = dict(COMMON_TOOLS)
    for descriptor in AGENT_REGISTRY.values():
        tools.update(descriptor.tools)
    return tools


LOCAL_TOOLS: dict = _local_tools()


def get_agent(agent_id: str) -> AgentDescriptor:
    """Resolve a canonical agent id (e.g. 'finance.treasury'). No aliases."""
    descriptor = AGENT_REGISTRY.get(agent_id)
    if descriptor is None:
        raise ValueError(
            f"Unsupported agent {agent_id!r}. "
            f"Allowed: {', '.join(AGENT_REGISTRY)}."
        )
    return descriptor


__all__ = [
    "AGENT_REGISTRY",
    "AGENT_CONFIG_FILES",
    "ENABLED_MODULES",
    "LOCAL_TOOLS",
    "AgentDescriptor",
    "MonitoringPass",
    "get_agent",
]
