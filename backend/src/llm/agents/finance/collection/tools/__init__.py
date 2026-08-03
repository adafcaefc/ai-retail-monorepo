from src.llm.agents.finance.collection.tools.collection_data import (
    TOOLS as _COLLECTION_DATA_TOOLS,
)
from src.llm.agents.finance.collection.tools.cross_agent import (
    TOOLS as _CROSS_AGENT_TOOLS,
)

TOOLS = {**_COLLECTION_DATA_TOOLS, **_CROSS_AGENT_TOOLS}