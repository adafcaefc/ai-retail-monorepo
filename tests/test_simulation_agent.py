# tests/test_simulation_update_pipeline.py

import asyncio
import json

from src.llm.simulation_pipeline import update_simulation_pipeline


async def main():
    payload = {
        "action": "recalculate_simulation",
        "source_agent": "Collections",
        "simulation_title": "Collections Recovery Scenario",
        "simulation_id": "collections_recovery",
        "calculation_instructions": (
            "Recovered Amount = Outstanding Balance * Collection Rate / 100. "
            "New Credit Balance = Current Credit Balance + Recovered Amount."
        ),
        "expected_outputs": [
            "Recovered Amount",
            "New Credit Balance",
        ],

        "Outstanding Balance": "1000",
        "Collection Rate": "20",
        "Current Credit Balance": "2500",
    }

    result = await update_simulation_pipeline(
        payload=payload,
        send_to_teams= True,
        wrap_in_adaptive_card_key=False,
    )

    print(result)

    if result.adaptive_card:
        print(json.dumps(result.adaptive_card, indent=2))


if __name__ == "__main__":
    asyncio.run(main())