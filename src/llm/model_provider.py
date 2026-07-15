from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import httpx
from openai import AsyncAzureOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.common.env import config


azure_endpoint = config.AZURE_OPENAI_ENDPOINT or config.AZURE_OPENAI_API_BASE
api_version = config.AZURE_OPENAI_API_VERSION
api_key = config.AZURE_OPENAI_API_KEY
deployment_name = config.AZURE_OPENAI_DEPLOYMENT


def _hlog(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [http] {msg}", flush=True)


async def _on_request(request: httpx.Request) -> None:
    print("=" * 80)
    print("REQUEST URL:", request.url)
    print("REQUEST METHOD:", request.method)
    print("=" * 80)


async def _on_response(response: httpx.Response) -> None:
    h = response.headers
    _hlog(
        f"<- {response.status_code} {response.request.url} "
        f"retry-after={h.get('retry-after')} "
        f"rem-tokens={h.get('x-ratelimit-remaining-tokens')} "
        f"rem-requests={h.get('x-ratelimit-remaining-requests')}"
    )


_http_client = httpx.AsyncClient(event_hooks={"request": [_on_request], "response": [_on_response]})

client = AsyncAzureOpenAI(
    azure_endpoint=azure_endpoint,
    api_version=api_version,
    api_key=api_key,
    http_client=_http_client,
)

print("DEPLOYMENT =", deployment_name)
print("ENDPOINT =", azure_endpoint)

model = OpenAIChatModel(
    deployment_name,
    provider=OpenAIProvider(openai_client=client),
)