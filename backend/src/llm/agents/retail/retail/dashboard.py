"""Empty Retail dashboard payload.

The three Retail boards render from a checked-in fixture today
(`frontend/src/agents/retail/*/data/fixture.json`), built from the workbook by
`scripts/build_*_fixture.py`. This module is what the API returns until a
builder reads the same figures out of Postgres — a structurally valid empty
state, so a client that switches to the API early gets empty panels rather than
a parse error.
"""

from __future__ import annotations

from typing import Any

from src.llm.agents.common.dashboard_scope import DashboardScope

# Nothing is narrowed yet, so nothing is claimed. Every filter a request sends
# comes back in `ignored_filters`, which is the honest answer while this stub
# stands: the board asked for one store and got the whole chain's empty set.
SUPPORTED_FILTERS: frozenset[str] = frozenset()


def build(_scope: DashboardScope | None = None) -> dict[str, Any]:
    """Return the structural empty state for the dashboard API contract."""
    return {
        "agent": "retail",
        "default_view": "",
        "kpis": [],
        "views": {},
        "side": {},
        "filters": [],
        "simulator": None,
    }
