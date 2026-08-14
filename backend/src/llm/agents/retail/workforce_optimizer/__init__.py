"""Agent 7 · Workforce Optimizer — navigation only, nothing wired yet.

Mockup page `awf`: peak-hour and brand-event staffing against availability.
See `retail/common/placeholder.py` for what this state means and how to leave it.
"""

from __future__ import annotations

from src.llm.agents.retail.common.placeholder import navigation_module

DESCRIPTOR = navigation_module(
    agent_id="retail.workforce_optimizer",
    display="Workforce Optimizer",
    description="Staff peak hours and brand events from the coverage you already have.",
    prompt="Ask Workforce...",
    starter_prompts=(
        "Where is the biggest FTE gap?",
        "Which brand events are short of staff?",
        "How many FTE can we reallocate instead of hire?",
    ),
)

__all__ = ["DESCRIPTOR"]
