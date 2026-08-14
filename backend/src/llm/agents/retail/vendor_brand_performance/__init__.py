"""Agent 8 · Vendor & Brand Performance — navigation only, nothing wired yet.

Mockup page `avb`: vendor scorecard, OTIF, fill, funding, brand contribution.
See `retail/common/placeholder.py` for what this state means and how to leave it.
"""

from __future__ import annotations

from src.llm.agents.retail.common.placeholder import navigation_module

DESCRIPTOR = navigation_module(
    agent_id="retail.vendor_brand_performance",
    display="Vendor & Brand Performance",
    description="Score vendors on what they deliver, and brands on what they contribute.",
    prompt="Ask Vendor...",
    starter_prompts=(
        "Which vendors underperform on OTIF and fill?",
        "Which brands carry the contribution?",
        "Where is our vendor concentration risk?",
    ),
)

__all__ = ["DESCRIPTOR"]
