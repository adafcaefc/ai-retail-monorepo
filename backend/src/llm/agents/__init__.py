"""Agent registry.

Discovers one `AgentDescriptor` per `agents/<folder>/<name>/__init__.py` and
derives everything the rest of the app needs from it: the chivon config file
list, the flat `LOCAL_TOOLS` map, and `get_agent()` lookups. Adding an agent is
adding a folder — nothing here needs editing.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from src.llm.agents.common.tools import COMMON_TOOLS
from src.llm.agents.descriptor import AgentDescriptor, MonitoringPass

_HERE = Path(__file__).resolve().parent
_RESERVED = {"common", "__pycache__"}


def _discover() -> dict[str, AgentDescriptor]:
    found: dict[str, AgentDescriptor] = {}
    for folder in sorted(
        p for p in _HERE.iterdir() if p.is_dir() and p.name not in _RESERVED
    ):
        for agent_dir in sorted(
            p for p in folder.iterdir()
            if p.is_dir() and p.name not in _RESERVED
        ):
            if not (agent_dir / "__init__.py").exists():
                continue
            module = importlib.import_module(
                f"src.llm.agents.{folder.name}.{agent_dir.name}"
            )
            descriptor = getattr(module, "DESCRIPTOR", None)
            if isinstance(descriptor, AgentDescriptor):
                found[descriptor.id] = descriptor
    return dict(sorted(found.items()))


AGENT_REGISTRY: dict[str, AgentDescriptor] = _discover()


def _config_files() -> list[Path]:
    # Common models/constants must merge before agents that reference them.
    common = sorted((_HERE / "common" / "config").glob("*.json"))
    domain = sorted(_HERE.glob("*/*/config/*.json"))
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
    "LOCAL_TOOLS",
    "AgentDescriptor",
    "MonitoringPass",
    "get_agent",
]
