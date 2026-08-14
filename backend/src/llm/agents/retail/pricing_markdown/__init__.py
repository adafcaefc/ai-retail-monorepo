"""Agent 5 · Pricing & Markdown — navigation only, nothing wired yet.

Mockup page `a5`: markdown candidates, depth, value at risk, recoverable value.
See `retail/common/placeholder.py` for what this state means and how to leave it.
"""

from __future__ import annotations

from src.llm.agents.retail.common.placeholder import navigation_module

DESCRIPTOR = navigation_module(
    agent_id="retail.pricing_markdown",
    display="Pricing & Markdown",
    description="Recover value from at-risk stock before it becomes a write-off.",
    prompt="Ask Pricing...",
    starter_prompts=(
        "What should we mark down first?",
        "How much value is recoverable at this depth?",
        "Where are we priced away from the market?",
    ),
)

__all__ = ["DESCRIPTOR"]
