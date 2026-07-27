from pathlib import Path


class AppPaths:
    BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

    # Agent config files are discovered by the registry
    # (src.llm.agents.AGENT_CONFIG_FILES). Nothing to enumerate here.
