"""Agent 9 · AI Explanation & Summary — navigation only, nothing wired yet.

Mockup page `a7`: the executive consolidation of Agents 1-8. It is last for a
reason — it has nothing to summarise until the eight below it report.
See `retail/common/placeholder.py` for what this state means and how to leave it.
"""

from __future__ import annotations

from src.llm.agents.retail.common.placeholder import navigation_module

DESCRIPTOR = navigation_module(
    agent_id="retail.ai_explanation_summary",
    display="AI Explanation & Summary",
    description="Consolidate what Agents 1-8 found into one board-ready account.",
    prompt="Ask Summary...",
    starter_prompts=(
        "Give me the executive summary.",
        "Where does the value actually come from?",
        "Do the agents' numbers reconcile?",
    ),
)

__all__ = ["DESCRIPTOR"]
