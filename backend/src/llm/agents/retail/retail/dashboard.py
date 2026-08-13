"""Empty Retail dashboard payload."""

from __future__ import annotations

from typing import Any


def build(
    _legal_entity_id: str | None = None,
    _period: str | None = None,
    _category_group: str | None = None,
) -> dict[str, Any]:
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
