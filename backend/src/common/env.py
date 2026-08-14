from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from src.common.constants import AppPaths

load_dotenv(AppPaths.BACKEND_ROOT / ".env")

class AppConfig:
    AZURE_OPENAI_API_BASE: str = os.getenv("AZURE_OPENAI_API_BASE", "")
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", os.getenv("AZURE_OPENAI_API_BASE", ""))
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    AZURE_SQL_CONNECTIONSTRING: str = os.getenv("AZURE_SQL_CONNECTIONSTRING", "")
    # Workbook behind the Data Source page. Empty means the checked-in
    # resources/ copy; set it to point at a mounted volume instead, or at a
    # path that does not exist to switch the page off (it then returns 503).
    EXCEL_WORKBOOK_PATH: str = os.getenv("EXCEL_WORKBOOK_PATH", "")
    # Root log level. INFO keeps the startup lines and model failures; set
    # DEBUG to get per-request Azure OpenAI traffic (status, rate-limit
    # headroom) back, which is what the removed print() banners used to show.
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


config = AppConfig()