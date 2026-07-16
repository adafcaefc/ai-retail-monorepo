import asyncio
from openai import AsyncAzureOpenAI



from src.common.env import config
async def main():
    client = AsyncAzureOpenAI(
        azure_endpoint="https://ai-finance-forum-azoai.openai.azure.com/",
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version="2025-04-01-preview",
    )

    response = await client.chat.completions.create(
        model="gpt-5.6-terra",
        messages=[
            {
                "role": "user",
                "content": "Say hello."
            }
        ],
    )

    print(response)


asyncio.run(main())