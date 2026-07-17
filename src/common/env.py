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
    DATABASE_URL: str = os.getenv("DATABASE_URL","")
    TEAMS_WEBHOOK_SECRET: str = os.getenv("TEAMS_WEBHOOK_SECRET", "")
    FINANCE_CHANNEL_ID: str = "19:2bccf45eb80844169856a8d97507a362%40thread.tacv2"
    TREASURY_CHANNEL_ID: str = "19:398337d296e2438fb6100d5e1f6daee0%40thread.tacv2"
    COLLECTIONS_CHANNEL_ID: str = "19:3NK8szVJxvxaZCsPcZNfaB71zDVScTgiejjsiub7EPo1%40thread.tacv2"
    LEAKAGE_CHANNEL_ID: str = "19:e6ad99014aae444bbc0c23f10e304f42%40thread.tacv2"


config = AppConfig()