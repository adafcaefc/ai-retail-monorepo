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

config = AppConfig()