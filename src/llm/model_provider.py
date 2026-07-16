from __future__ import annotations

from datetime import datetime

import httpx
from openai import AsyncAzureOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.common.env import config


azure_endpoint = config.AZURE_OPENAI_ENDPOINT or config.AZURE_OPENAI_API_BASE
api_version = config.AZURE_OPENAI_API_VERSION
api_key = config.AZURE_OPENAI_API_KEY
deployment_name = config.AZURE_OPENAI_DEPLOYMENT


def _hlog(msg: str) -> None:
    print(
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [http] {msg}",
        flush=True,
    )


async def _on_request(request: httpx.Request) -> None:
    print("=" * 80, flush=True)
    print("REQUEST URL:", request.url, flush=True)
    print("REQUEST METHOD:", request.method, flush=True)
    print("=" * 80, flush=True)


async def _on_response(response: httpx.Response) -> None:
    h = response.headers
    _hlog(
        f"<- {response.status_code} {response.request.url} "
        f"retry-after={h.get('retry-after')} "
        f"rem-tokens={h.get('x-ratelimit-remaining-tokens')} "
        f"rem-requests={h.get('x-ratelimit-remaining-requests')}"
    )


_http_client = httpx.AsyncClient(
    event_hooks={
        "request": [_on_request],
        "response": [_on_response],
    }
)

client = AsyncAzureOpenAI(
    azure_endpoint=azure_endpoint,
    azure_deployment=deployment_name,
    api_version=api_version,
    api_key=api_key,
    http_client=_http_client,
)

print("DEPLOYMENT =", deployment_name, flush=True)
print("ENDPOINT =", azure_endpoint, flush=True)
print("API VERSION =", api_version, flush=True)

model = OpenAIChatModel(
    model_name=deployment_name,
    provider=OpenAIProvider(
        openai_client=client,
    ),
)

print("MODEL =", model, flush=True)
print("MODEL VARS =", vars(model), flush=True)