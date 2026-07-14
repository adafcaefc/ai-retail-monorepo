import asyncio

from src.llm.simulation_pipeline import recalculate_simulation


async def main():
    payload = {
        "action": "recalculate_simulation",
        "simulation_title": "Collections Recovery Scenario",
        "calculation_instructions": (
            "Recovered Amount = Outstanding Balance * Collection Rate / 100. "
            "New Credit Balance = Current Credit Balance + Recovered Amount."
        ),
        "expected_outputs": [
            "Recovered Amount",
            "New Credit Balance"
        ],

        "Outstanding Balance": "1000000000",
        "Collection Rate": "20",
        "Current Credit Balance": "250000000"
    }

    result = await recalculate_simulation(payload)

    print(result)


if __name__ == "__main__":
    asyncio.run(main())