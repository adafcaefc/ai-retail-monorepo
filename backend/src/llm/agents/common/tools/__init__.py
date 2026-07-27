"""Common tools shared across every domain agent."""

from src.llm.agents.common.tools.alert_actions import (
    COMMON_ALERT_ACTION_TOOLS,
)
from src.llm.agents.common.tools.freeform_query import (
    LOCAL_FREEFORM_QUERY_TOOLS,
)
from src.llm.agents.common.tools.monitoring_tools import (
    LOCAL_MONITORING_TOOLS,
)

# Tools every agent may reference: freeform SELECT/describe helpers, the
# monitoring/simulation/execution primitives, and the cross-agent alert
# action plan tools.
COMMON_TOOLS = {
    **LOCAL_FREEFORM_QUERY_TOOLS,
    **LOCAL_MONITORING_TOOLS,
    **COMMON_ALERT_ACTION_TOOLS,
}

__all__ = [
    "COMMON_TOOLS",
    "COMMON_ALERT_ACTION_TOOLS",
    "LOCAL_FREEFORM_QUERY_TOOLS",
    "LOCAL_MONITORING_TOOLS",
]
