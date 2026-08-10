from pathlib import Path


class AppPaths:
    BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

    REPO_ROOT = BACKEND_ROOT.parent

    # Formula Manager's store. A JSON file rather than a table: these are
    # reference formulas edited by hand, not transactional data.
    FORMULA_STORE = REPO_ROOT / "resources" / "dbtemp" / "formula.json"

    # Agent config files are discovered by the registry
    # (src.llm.agents.AGENT_CONFIG_FILES). Nothing to enumerate here.
