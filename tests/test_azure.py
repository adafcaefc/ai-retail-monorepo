from __future__ import annotations

import asyncio

from openai import AsyncAzureOpenAI

from src.common.env import config


async def main() -> int:
    if not config.AZURE_OPENAI_ENDPOINT or not config.AZURE_OPENAI_API_KEY:
        raise RuntimeError("Azure OpenAI endpoint and API key must be configured.")
    if not config.AZURE_OPENAI_DEPLOYMENT:
        raise RuntimeError("AZURE_OPENAI_DEPLOYMENT must be configured.")

    client = AsyncAzureOpenAI(
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
    )
    try:
        response = await client.chat.completions.create(
            model=config.AZURE_OPENAI_DEPLOYMENT,
            messages=[{"role": "user", "content": "Reply only with SMOKE_OK."}],
        )
    finally:
        await client.close()

    content = response.choices[0].message.content or ""
    print(content)
    return 0 if content.strip() else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))