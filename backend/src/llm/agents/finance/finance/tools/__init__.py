from src.llm.agents.finance.finance.tools.performance_data import (
    TOOLS as _PERFORMANCE_TOOLS,
)
from src.llm.agents.finance.finance.tools.cross_agent import (
    TOOLS as _CROSS_AGENT_TOOLS,
)

TOOLS = {**_PERFORMANCE_TOOLS, **_CROSS_AGENT_TOOLS}

__all__ = ["TOOLS"]