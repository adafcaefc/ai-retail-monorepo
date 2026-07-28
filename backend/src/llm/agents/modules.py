"""The enabled modules, in sidebar order.

Single source of truth for both sides of the app: the registry
(`src.llm.agents`) discovers exactly these, `GET /api/html/agents` serves
them, and the frontend sidebar is built from that response.

Adding a module: create `agents/<folder>/<name>/` with a `DESCRIPTOR`, then
add its canonical id here. Removing one: delete the id (the folder may stay).
"""

from __future__ import annotations

ENABLED_MODULES: tuple[str, ...] = (
    "finance.finance",
    "finance.leakage",
    "finance.collection",
    "finance.treasury",
)

__all__ = ["ENABLED_MODULES"]
