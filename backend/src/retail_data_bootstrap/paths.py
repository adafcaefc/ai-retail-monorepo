from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from src.common.constants import AppPaths
from src.excel.workbook import DEFAULT_WORKBOOK_PATH

GENERATED_DIR = AppPaths.REPO_ROOT / "generated"
DEFAULT_INVENTORY_PATH = GENERATED_DIR / "workbook_inventory.json"
DEFAULT_DOCUMENTS_PATH = GENERATED_DIR / "retail_documents.jsonl"
DEFAULT_SAMPLE_PATH = GENERATED_DIR / "retail_documents_sample.jsonl"
DEFAULT_MIGRATION_PATH = AppPaths.REPO_ROOT / "sql" / "retail" / "001_create_retail_schema.sql"
DEFAULT_AI_MIGRATION_PATH = AppPaths.REPO_ROOT / "sql" / "ai" / "001_create_ai_vector_schema.sql"


def resolve_workbook_path(value: str | Path | None = None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    configured = os.getenv("EXCEL_WORKBOOK_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = AppPaths.REPO_ROOT / candidate
        return candidate.resolve()
    return DEFAULT_WORKBOOK_PATH.resolve()


def load_azure_sql_connection_string(env_file: Path | None = None) -> str:
    path = env_file or (AppPaths.BACKEND_ROOT / ".env")
    if path.is_file():
        load_dotenv(path, override=False)
    value = os.getenv("AZURE_SQL_CONNECTIONSTRING", "").strip()
    if not value:
        raise RuntimeError(
            "AZURE_SQL_CONNECTIONSTRING is not configured in the environment or backend/.env"
        )
    return value
