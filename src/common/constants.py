from pathlib import Path


class AppPaths:
    BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

    CONFIG_DIR = BACKEND_ROOT / "src" / "llm" / "config"

    COMMON_CONFIG_FILE = CONFIG_DIR / "common.json"

    FINANCE_CONFIG_FILE = CONFIG_DIR / "finance.json"
    CASHFLOW_CONFIG_FILE = CONFIG_DIR / "cashflow.json"
    COLLECTION_CONFIG_FILE = CONFIG_DIR / "collection.json"
    LEAKAGE_CONFIG_FILE = CONFIG_DIR / "leakage.json"
    RENDERER_CONFIG_FILE = CONFIG_DIR / "renderer.json"
    SIMULATOR_CONFIG_FILE = CONFIG_DIR / "simulator.json"

    AGENTS_CONFIG_FILES = [
        COMMON_CONFIG_FILE,
        FINANCE_CONFIG_FILE,
        CASHFLOW_CONFIG_FILE,
        COLLECTION_CONFIG_FILE,
        LEAKAGE_CONFIG_FILE,
        RENDERER_CONFIG_FILE,
        SIMULATOR_CONFIG_FILE
    ]