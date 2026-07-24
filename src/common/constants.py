from pathlib import Path


class AppPaths:
    BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

    CONFIG_DIR = BACKEND_ROOT / "src" / "llm" / "config"

    COMMON_CONFIG_FILE = CONFIG_DIR / "common.json"

    FINANCE_CONFIG_FILE = CONFIG_DIR / "finance.json"
    CASHFLOW_CONFIG_FILE = CONFIG_DIR / "cashflow.json"
    COLLECTION_CONFIG_FILE = CONFIG_DIR / "collection.json"
    LEAKAGE_CONFIG_FILE = CONFIG_DIR / "leakage.json"
    SIMULATOR_CONFIG_FILE = CONFIG_DIR / "simulator.json"
    SUBAGENT_CONFIG_FILE = CONFIG_DIR / "subagents.json"
    FINANCE_SUBAGENTS_CONFIG_FILE = CONFIG_DIR / "finance_subagents.json"
    CASHFLOW_SUBAGENTS_CONFIG_FILE = CONFIG_DIR / "cashflow_subagents.json"
    COLLECTION_SUBAGENTS_CONFIG_FILE = CONFIG_DIR / "collection_subagents.json"
    LEAKAGE_SUBAGENTS_CONFIG_FILE = CONFIG_DIR / "leakage_subagents.json"

    # Backward-compatible alias for the old typo'd name.
    SUBAGENT_CONFIC_FILE = SUBAGENT_CONFIG_FILE

    AGENTS_CONFIG_FILES = [
        COMMON_CONFIG_FILE,
        FINANCE_CONFIG_FILE,
        CASHFLOW_CONFIG_FILE,
        COLLECTION_CONFIG_FILE,
        LEAKAGE_CONFIG_FILE,
        SIMULATOR_CONFIG_FILE,
        SUBAGENT_CONFIG_FILE,
        FINANCE_SUBAGENTS_CONFIG_FILE,
        CASHFLOW_SUBAGENTS_CONFIG_FILE,
        COLLECTION_SUBAGENTS_CONFIG_FILE,
        LEAKAGE_SUBAGENTS_CONFIG_FILE,
    ]