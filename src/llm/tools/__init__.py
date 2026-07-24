from src.llm.tools.finance_data import LOCAL_FINANCE_TOOLS
from src.llm.tools.freeform_query import LOCAL_FREEFORM_QUERY_TOOLS
from src.llm.tools.monitoring_tools import LOCAL_MONITORING_TOOLS

LOCAL_TOOLS = {
    **LOCAL_FINANCE_TOOLS,
    **LOCAL_FREEFORM_QUERY_TOOLS,
    **LOCAL_MONITORING_TOOLS,
}

__all__ = [
    "LOCAL_FINANCE_TOOLS",
    "LOCAL_FREEFORM_QUERY_TOOLS",
    "LOCAL_MONITORING_TOOLS",
    "LOCAL_TOOLS",
]