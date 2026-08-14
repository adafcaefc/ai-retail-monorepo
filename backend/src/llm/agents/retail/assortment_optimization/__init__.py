"""Agent 6 · Assortment Optimization — navigation only, nothing wired yet.

Mockup page `a6`: GMROI, tail share, delist and grow candidates, capital freed.
See `retail/common/placeholder.py` for what this state means and how to leave it.
"""

from __future__ import annotations

from src.llm.agents.retail.common.placeholder import navigation_module

DESCRIPTOR = navigation_module(
    agent_id="retail.assortment_optimization",
    display="Assortment Optimization",
    description="Decide what to delist and what to grow, and what capital that frees.",
    prompt="Ask Assortment...",
    starter_prompts=(
        "Which SKUs should we delist?",
        "How much capital would delisting the tail free?",
        "Which lines earn their shelf space?",
    ),
)

__all__ = ["DESCRIPTOR"]
