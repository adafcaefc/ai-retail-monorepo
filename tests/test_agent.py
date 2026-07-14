import asyncio

from src.llm.chivon_impl import load_chivon
from src.llm.agents.chivon import chivon
from src.llm.pipeline import render_agent_response
import json

async def main():

    load_chivon()
    
    renderer_output = render_agent_response("finance_agent", {
            "user":
            "How many transactions are behind?"
        })

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

    # Save output for Teams testing
    with open(
        "tests/test_renderer_output.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            adaptive_card,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nSaved Adaptive Card to test_renderer_output.json")
    """
    response = await chivon.run_async(
        "leakage_agent",
        {
            "user":
            "How many transactions look fishy?"
        }
    )

    print(response.output)
    agent_output = response.output

    Component = chivon.type("Component")
    RendererOutput = chivon.type("RendererOutput")

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

    # Save output for Teams testing
    with open(
        "tests/test_renderer_output.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            adaptive_card,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\nSaved Adaptive Card to test_renderer_output.json")

    # Basic validation
    assert adaptive_card["type"] == "AdaptiveCard"
    assert "body" in adaptive_card
    assert isinstance(adaptive_card["body"], list)

    print("\nRenderer test passed.")
    """


if __name__ == "__main__":
    asyncio.run(main())