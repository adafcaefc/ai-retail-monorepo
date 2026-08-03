from src.llm.agents.finance.treasury.tools.treasury_data import (
    TOOLS as _TREASURY_DATA_TOOLS,
)
from src.llm.agents.finance.treasury.tools.cross_agent import (
    TOOLS as _CROSS_AGENT_TOOLS,
)

TOOLS = {**_TREASURY_DATA_TOOLS, **_CROSS_AGENT_TOOLS}

__all__ = ["TOOLS"]
