from __future__ import annotations

from src.common.constants import AppPaths
from src.common.env import config  # noqa: F401  (ensures .env is loaded into os.environ)
from src.llm.agents.chivon import Chivon, chivon
from src.llm.tools import LOCAL_FINANCE_TOOLS


def load_chivon():
    from src.llm.model_provider import model
    """
    mcp_path = AppPaths.BACKEND_ROOT / "mcpx" / "main.py"
    tools_server = MCPServerStdio(
        command=sys.executable,
        args=[str(mcp_path)],
        env=os.environ.copy(),
        # The tool subprocess cold-imports pydantic_ai + mcp before it can answer the
        # MCP init handshake, which can take well over the 5s default on a cold start.
        # Give it generous headroom so startup does not race the init deadline.
        timeout=30,
    )
    """
    config_files = AppPaths.AGENTS_CONFIG_FILES
    types = Chivon.build_types_from_file(config_files)
    chivon.load_from_file(
        config_files,
        model,
        types["TextInput"],
        #mcp_servers={"frasers_tools": tools_server},
        local_tools=LOCAL_FINANCE_TOOLS,
    )



def get_chivon():
    try:
        _ = chivon.agents
    except RuntimeError:
        load_chivon()

    return chivon
