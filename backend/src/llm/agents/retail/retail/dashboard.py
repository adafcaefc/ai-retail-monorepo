"""Empty Retail dashboard payload."""

from __future__ import annotations

from typing import Any


def build() -> dict[str, Any]:
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
