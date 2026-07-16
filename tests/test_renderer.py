from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from src.common.constants import AppPaths
from src.llm.adaptive_cards import (
    AdaptiveCardError,
    render_finance_agent_output,
    validate_adaptive_card,
)
from src.llm.agents.chivon import Chivon


def component(component_format: str, content: dict) -> dict[str, str]:
    return {
        "format": component_format,
        "content": json.dumps(content),
    }


class AdaptiveCardRendererTest(unittest.TestCase):
    def render(self, component_value: dict[str, str]) -> dict:
        return render_finance_agent_output(
            {
                "agent": "Cashflow",
                "components": [component_value],
            }
        )

    def test_renders_multi_series_line_chart_with_fallback(self) -> None:
        card = self.render(
            component(
                "chart",
                {
                    "title": "Closing cash vs buffer",
                    "chart_type": "line",
                    "data": [
                        {
                            "legend": "Closing cash",
                            "values": [
                                {"label": "W1", "value": 24000},
                                {"label": "W2", "value": 26000},
                            ],
                        },
                        {
                            "legend": "Minimum buffer",
                            "values": [
                                {"label": "W1", "value": 8000},
                                {"label": "W2", "value": 8000},
                            ],
                        },
                    ],
                },
            )
        )

        chart = card["body"][1]
        self.assertEqual(chart["type"], "Chart.Line")
        self.assertEqual(chart["data"][0]["values"][0], {"x": "W1", "y": 24000})
        self.assertEqual(chart["fallback"]["type"], "Container")
        self.assertEqual(card["msteams"]["width"], "Full")

    def test_maps_supported_chart_data_contracts(self) -> None:
        expectations = {
            "bar": ("Chart.VerticalBar", "x", "y"),
            "pie": ("Chart.Pie", "legend", "value"),
            "donut": ("Chart.Donut", "legend", "value"),
        }
        for chart_type, expected in expectations.items():
            with self.subTest(chart_type=chart_type):
                card = self.render(
                    component(
                        "chart",
                        {
                            "title": "Options",
                            "chart_type": chart_type,
                            "data": [{"label": "Option A", "value": 5000}],
                        },
                    )
                )
                chart = card["body"][1]
                self.assertEqual(chart["type"], expected[0])
                self.assertEqual(chart["data"][0][expected[1]], "Option A")
                self.assertEqual(chart["data"][0][expected[2]], 5000)

    def test_renders_native_table(self) -> None:
        card = self.render(
            component(
                "table",
                {
                    "title": "Before and after",
                    "columns": ["Item", "Before", "After"],
                    "rows": [["DSO", 57.4, 54.8]],
                },
            )
        )

        table = card["body"][1]["items"][1]
        self.assertEqual(table["type"], "Table")
        self.assertEqual(len(table["rows"]), 2)

    def test_simulation_carries_complete_callback_contract(self) -> None:
        card = self.render(
            component(
                "simulation",
                {
                    "title": "Collection offer",
                    "simulation_id": "collection_offer",
                    "action": "calculate_collection_scenario",
                    "submit_data": {"customer_name": "Customer A"},
                    "calculation_instructions": "Discount = cash * rate / 100",
                    "inputs": [
                        {
                            "id": "cash_to_collect_idr_mn",
                            "label": "Cash",
                            "min": 1,
                            "max": 10000,
                            "default": 5000,
                            "unit": "IDR mn",
                        }
                    ],
                    "outputs": [{"label": "Discount", "unit": "IDR mn"}],
                },
            )
        )

        action = card["body"][1]["items"][-1]["actions"][0]
        self.assertEqual(action["type"], "Action.Submit")
        self.assertEqual(action["data"]["action"], "calculate_collection_scenario")
        self.assertEqual(action["data"]["customer_name"], "Customer A")
        self.assertEqual(action["data"]["expected_outputs"], ["Discount"])
        self.assertIn("original_inputs", action["data"])

    def test_validation_rejects_malformed_chart(self) -> None:
        with self.assertRaises(AdaptiveCardError):
            validate_adaptive_card(
                {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": [
                        {
                            "type": "Chart.VerticalBar",
                            "data": [{"x": "Week 5", "y": "not-a-number"}],
                        }
                    ],
                }
            )

    def test_component_model_rejects_malformed_json_content(self) -> None:
        component_model = Chivon.build_types_from_file(
            AppPaths.AGENTS_CONFIG_FILES
        )["Component"]

        with self.assertRaises(ValidationError):
            component_model(
                format="text",
                content=(
                    '{"title":"Collections",'
                    '"content":"unescaped\nnewline"}'
                ),
            )


if __name__ == "__main__":
    unittest.main()