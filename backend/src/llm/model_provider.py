from __future__ import annotations

import logging

import httpx
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.common.env import config

logger = logging.getLogger(__name__)


azure_endpoint = config.AZURE_OPENAI_ENDPOINT or config.AZURE_OPENAI_API_BASE
api_version = config.AZURE_OPENAI_API_VERSION
api_key = config.AZURE_OPENAI_API_KEY
deployment_name = config.AZURE_OPENAI_DEPLOYMENT


async def _on_response(response: httpx.Response) -> None:
    """Log the outcome of each Azure OpenAI call.

    A failed call is the single most useful line in the log -- a 401 means a
    dead key, a 429 carries the retry-after -- so those are warnings and are
    visible by default. Successful calls carry only rate-limit headroom, which
    is worth having but not worth a line per request, so they sit at DEBUG.

    There is no request hook. It printed an 80-character banner with the URL
    before every call, which is the same URL the response line already
    reports.
    """
    headers = response.headers
    detail = (
        f"{response.status_code} {response.request.method} "
        f"{response.request.url} "
        f"retry-after={headers.get('retry-after')} "
        f"rem-tokens={headers.get('x-ratelimit-remaining-tokens')} "
        f"rem-requests={headers.get('x-ratelimit-remaining-requests')}"
    )
    if response.is_success:
        logger.debug("azure openai %s", detail)
    else:
        logger.warning("azure openai call failed: %s", detail)


if not azure_endpoint:
    raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_BASE.")

if not api_version:
    raise RuntimeError("Missing AZURE_OPENAI_API_VERSION.")

if not api_key:
    raise RuntimeError("Missing AZURE_OPENAI_API_KEY.")

if not deployment_name:
    raise RuntimeError("Missing AZURE_OPENAI_DEPLOYMENT.")


normalized_endpoint = azure_endpoint.rstrip("/")

azure_chat_base_url = (
    f"{normalized_endpoint}/openai/deployments/{deployment_name}"
)


_http_client = httpx.AsyncClient(
    event_hooks={
        "response": [_on_response],
    }
)


client = AsyncOpenAI(
    api_key="unused",
    base_url=azure_chat_base_url,
    default_headers={
        "api-key": api_key,
    },
    default_query={
        "api-version": api_version,
    },
    http_client=_http_client,
)


# Which deployment this process is talking to, once at startup. Never the key.
logger.info(
    "azure openai configured: endpoint=%s deployment=%s api-version=%s",
    normalized_endpoint,
    deployment_name,
    api_version,
)


model = OpenAIChatModel(
    model_name=deployment_name,
    provider=OpenAIProvider(
        openai_client=client,
    ),
)