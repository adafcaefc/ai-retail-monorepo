# tests/test_renderer.py

import asyncio
import json

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon


async def main():
    # Load Chivon agents
    load_chivon()

    FinanceAgentOutput = chivon.type("FinanceAgentOutput")
    Component = chivon.type("Component")
    RendererOutput = chivon.type("RendererOutput")

    # Fake FinanceAgentOutput to test renderer directly
    agent_output = FinanceAgentOutput(
        components=[

            # NEXT ROUTE
            Component(
                format="next_route",
                content=json.dumps({
                    "title": "Next Agents to Consult",
                    "routes": [
                        {
                            "destination": "Cashflow",
                            "reason": "Validate whether pricing and hedge decisions affect near-term cash position."
                        },
                        {
                            "destination": "Collections",
                            "reason": "Check whether customer payment timing can support the margin recovery plan."
                        },
                        {
                            "destination": "Leakage",
                            "reason": "Evaluate margin leakage recovery opportunities."
                        }
                    ]
                })
            )
        ],
        agent= "Finance"
    )

    print("\n=== INPUT TO RENDERER ===")
    print(agent_output)

    renderer_response = await chivon.run_async(
        "renderer_agent",
        agent_output
    )

    renderer_output = renderer_response.output

    print("\n=== RAW RENDERER OUTPUT ===")
    print(renderer_output)

    if not isinstance(renderer_output, RendererOutput):
        raise TypeError(
            f"Expected RendererOutput, got {type(renderer_output)}"
        )

    print("\n=== CARD OUTPUT STRING ===")
    print(renderer_output.card_output)

    # Validate that card_output is valid JSON
    adaptive_card = json.loads(renderer_output.card_output)

    print("\n=== PARSED ADAPTIVE CARD ===")
    print(json.dumps(adaptive_card, indent=2))

    # Basic validation
    assert adaptive_card["type"] == "AdaptiveCard"
    assert "body" in adaptive_card
    assert isinstance(adaptive_card["body"], list)

    print("\nRenderer test passed.")


if __name__ == "__main__":
    asyncio.run(main())