# tests/test_full_pipeline.py

import asyncio

from src.llm.pipeline import render_agent_response

message_history = [
    {
        "sender": "user",
        "text": "Can you help me review our collections position?"
    },
    {
        "sender": "chatbot",
        "text": "Yes. Please provide any available AR, collections, or credit information."
    },
    {
        "sender": "user",
        "text": "Total overdue receivables are currently USD 1.0 billion."
    },
    {
        "sender": "chatbot",
        "text": "Understood. Outstanding overdue balance recorded as USD 1 billion."
    },
    {
        "sender": "user",
        "text": (
            "The CFO is primarily interested in understanding recovery "
            "scenarios rather than historical collections performance."
        )
    },
    {
        "sender": "chatbot",
        "text": (
            "Understood. Future-looking collection scenarios can be "
            "evaluated using the provided balances."
        )
    },
    {
        "sender": "user",
        "text": "Assume our current credit balance is USD 250 million."
    },
    {
        "sender": "chatbot",
        "text": "Noted. Current credit balance is USD 250 million."
    },
    {
        "sender": "user",
        "text": (
            "No additional operational data is required. "
            "We only want scenario analysis using the balances already provided."
        )
    },
    {
        "sender": "chatbot",
        "text": (
            "Understood. Hypothetical scenario modelling is permitted "
            "using the supplied figures."
        )
    },
    {
        "sender": "user",
        "text": (
            "Please visualize recovery scenarios if we collect "
            "different percentages of the overdue receivables."
        )
    },
    {
        "sender": "chatbot",
        "text": (
            "I can generate charts showing the impact of different "
            "collection rates on cash position and credit balance."
        )
    },
    {
        "sender": "user",
        "text": (
            "Use only the supplied values and do not request aging data, "
            "customer-level balances, payment history, or DSO metrics."
        )
    },
    {
        "sender": "chatbot",
        "text": (
            "Understood. Future chart requests should be generated "
            "directly from the provided assumptions."
        )
    },
    {
        "sender": "user",
        "text": (
            "Create a simulation where I can change the percent we can recover from late payments and how it affects our credit balance."
        )
    }
]


async def main():
    result = await render_agent_response(
        agent_name="collection_agent",
        messages_input={
            "lines": message_history
        },
    )

    print(result)


if __name__ == "__main__":
    asyncio.run(main())