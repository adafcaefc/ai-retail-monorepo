from __future__ import annotations

from src.common.env import config  # noqa: F401
from src.llm.agents import AGENT_CONFIG_FILES, LOCAL_TOOLS
from src.llm.chivon.chivon import Chivon, chivon
from src.llm.tool_events import wrap_tools


def load_chivon():
    from src.llm.model_provider import model

    config_files = AGENT_CONFIG_FILES
    types = Chivon.build_types_from_file(
        config_files
    )

    chivon.load_from_file(
        config_files,
        model,
        types["TextInput"],
        local_tools=wrap_tools(
            LOCAL_TOOLS
        ),
    )


def get_chivon():
    try:
        _ = chivon.agents

    except RuntimeError:
        load_chivon()

    return chivon
