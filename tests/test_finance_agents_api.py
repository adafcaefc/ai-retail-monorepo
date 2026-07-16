from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.finance_agents import router
from src.common.env import config
from src.db.db import get_db_session


COLLECTION_RESULT = {
    "import_batch_id": 11,
    "customer_id": "C001",
    "customer_name": "PT Anugerah Prima (Customer A)",
    "cash_collected_idr_mn": 5000.0,
    "discount_pct": 1.0,
    "discount_cost_idr_mn": 50.0,
    "customer_overdue_before_idr_mn": 10000.0,
    "customer_overdue_after_idr_mn": 5000.0,
    "total_ar_before_idr_mn": 110000.0,
    "total_ar_after_idr_mn": 105000.0,
    "dso_before_days": 57.36,
    "dso_after_days": 54.75,
    "dso_change_days": -2.61,
    "assumption": "Customer acceptance requires verification.",
}


class FinanceAgentApiTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.include_router(router)

        def override_session():
            yield object()

        app.dependency_overrides[get_db_session] = override_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()

    @patch(
        "src.api.finance_agents.calculate_collection_scenario",
        return_value=COLLECTION_RESULT,
    )
    def test_collection_submit_returns_exact_card(self, calculate) -> None:
        response = self.client.post(
            "/api/finance-agents/simulations/recalculate",
            json={
                "action": "calculate_collection_scenario",
                "source_agent": "Collections",
                "customer_name": "Customer A",
                "cash_to_collect_idr_mn": "5000",
                "discount_pct": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["sourceAgent"], "collection_agent")
        self.assertEqual(payload["adaptiveCard"]["body"][1]["type"], "Chart.VerticalBar")
        table = payload["adaptiveCard"]["body"][2]["items"][1]
        self.assertEqual(table["type"], "Table")
        calculate.assert_called_once_with(
            customer_name="Customer A",
            cash_to_collect_idr_mn=5000.0,
            discount_pct=1.0,
        )

    @patch(
        "src.api.finance_agents.calculate_collection_scenario",
        return_value=COLLECTION_RESULT,
    )
    def test_collection_submit_accepts_power_automate_envelopes(
        self,
        calculate,
    ) -> None:
        submitted_data = {
            "action": "calculate_collection_scenario",
            "source_agent": "Collections",
            "customer_name": "Customer A",
            "cash_to_collect_idr_mn": "5000",
            "discount_pct": "1",
        }
        payloads = (
            {"data": submitted_data, "messageId": "teams-message"},
            {
                "body": {
                    "data": submitted_data,
                    "responder": {"displayName": "CFO"},
                },
                "statusCode": 200,
            },
            {
                "body": json.dumps(
                    {"data": submitted_data},
                ),
            },
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/finance-agents/simulations/recalculate",
                    json=payload,
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["success"])

        self.assertEqual(calculate.call_count, len(payloads))

    @patch("src.api.finance_agents.cashflow_cards.build_cashflow_simulation_card")
    @patch("src.api.finance_agents.cashflow_service.simulate")
    @patch("src.api.finance_agents.cashflow_service.get_baseline")
    def test_cashflow_submit_coerces_card_input_strings(
        self,
        get_baseline,
        simulate,
        build_card,
    ) -> None:
        get_baseline.return_value = object()
        simulate.return_value = object()
        build_card.return_value = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [{"type": "TextBlock", "text": "Updated"}],
        }

        response = self.client.post(
            "/api/finance-agents/simulations/recalculate",
            json={
                "action": "simulate_cashflow",
                "source_agent": "Cashflow",
                "accelerate_collection_idr_mn": "2000",
                "defer_payment_idr_mn": "0",
                "credit_line_draw_idr_mn": "0",
                "hedge_usd": "2000000",
            },
        )

        self.assertTrue(response.json()["success"])
        request = simulate.call_args.args[0]
        self.assertEqual(request.accelerate_collection_idr_mn, 2000.0)
        self.assertEqual(request.hedge_usd, 2000000.0)

    def test_rejects_unsupported_action(self) -> None:
        response = self.client.post(
            "/api/finance-agents/simulations/recalculate",
            json={
                "action": "drop_database",
                "source_agent": "Cashflow",
            },
        )

        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("Unsupported simulation action", payload["error"])

    @patch.object(config, "TEAMS_WEBHOOK_SECRET", "expected-secret")
    def test_webhook_secret_is_enforced_when_configured(self) -> None:
        missing_secret = self.client.post(
            "/api/finance-agents/simulations/recalculate",
            json={"action": "unknown", "source_agent": "unknown"},
        )
        valid_secret = self.client.post(
            "/api/finance-agents/simulations/recalculate",
            headers={"X-Teams-Webhook-Secret": "expected-secret"},
            json={"action": "unknown", "source_agent": "unknown"},
        )

        self.assertEqual(missing_secret.status_code, 401)
        self.assertEqual(valid_secret.status_code, 200)


if __name__ == "__main__":
    unittest.main()