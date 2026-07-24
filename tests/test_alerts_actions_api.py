from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.actions import repository
from src.actions.router import router
from src.db.db import get_db_session


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    return app


class AlertActionApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.alert = {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Margin drop",
            "subagent": "finance_monitoring_agent",
            "agent": "finance",
            "issue": "Gross margin fell to 18%.",
            "date_created": "2026-07-24T00:00:00+00:00",
        }
        self.action = {
            "id": "22222222-2222-2222-2222-222222222222",
            "action": "Restore SKU pricing",
            "agent": "finance",
            "routes": ["Commercial Lead"],
            "alert_id": self.alert["id"],
            "status": repository.ACTION_STATUS_PLANNED,
            "spec": "Raise prices on discounted SKUs by 2%.",
            "impact": "Gross Margin: 18.0% + 2.0% -> 20.0%",
            "simulation_summary": None,
            "created_at": "2026-07-24T00:00:00+00:00",
        }

    def test_list_alerts_and_actions_and_approve(self) -> None:
        with (
            patch(
                "src.actions.service.repository.get_alerts",
                return_value=[self.alert],
            ),
            patch(
                "src.actions.service.repository.get_alert",
                return_value=self.alert,
            ),
            patch(
                "src.actions.service.repository.get_actions",
                return_value=[self.action],
            ),
            patch(
                "src.actions.service.repository.get_action",
                return_value=self.action,
            ),
            patch(
                "src.actions.service.repository.update_action_status",
                return_value={
                    **self.action,
                    "status": repository.ACTION_STATUS_APPROVED,
                },
            ),
        ):
            client = TestClient(_build_app())

            alerts = client.get("/api/alerts")
            self.assertEqual(alerts.status_code, 200)
            self.assertEqual(alerts.json()["count"], 1)

            history = client.get("/api/actions?agent=finance")
            self.assertEqual(history.status_code, 200)
            self.assertEqual(history.json()["count"], 1)
            self.assertEqual(
                history.json()["items"][0]["status"],
                "planned",
            )

            actions = client.get(
                f"/api/alerts/{self.alert['id']}/actions"
            )
            self.assertEqual(actions.status_code, 200)
            self.assertEqual(actions.json()["count"], 1)
            self.assertEqual(
                actions.json()["items"][0]["status"],
                "planned",
            )

            approved = client.post(
                f"/api/actions/{self.action['id']}/approve"
            )
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["status"], "approved")

    def test_simulate_action_persists_summary(self) -> None:
        fake_output = MagicMock()
        fake_output.model_dump.return_value = {
            "summary": "Margin improves by 2pp",
            "rows_affected": 12,
            "metrics_json": (
                '{"SUM(margin)":{"before":18,"after":20,"delta":2}}'
            ),
        }
        fake_result = MagicMock()
        fake_result.output = fake_output

        fake_chivon = MagicMock()
        fake_chivon.run_async = AsyncMock(return_value=fake_result)

        with (
            patch(
                "src.actions.service.repository.get_action",
                return_value=self.action,
            ),
            patch(
                "src.actions.service.repository.update_action_simulation_summary",
                return_value={
                    **self.action,
                    "simulation_summary": {
                        "summary": "Margin improves by 2pp"
                    },
                },
            ) as update_summary,
            patch(
                "src.actions.service.get_chivon",
                return_value=fake_chivon,
            ),
        ):
            client = TestClient(_build_app())
            response = client.post(
                f"/api/actions/{self.action['id']}/simulate"
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIn("simulation", body)
            self.assertEqual(
                body["simulation"]["summary"],
                "Margin improves by 2pp",
            )
            update_summary.assert_called_once()
            fake_chivon.run_async.assert_awaited_once()


class PopulateAlertsTest(unittest.TestCase):
    def test_list_monitoring_agents_for_domain(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/api/monitoring-agents?agent=leakage")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["agent"], "leakage")
        names = [
            item["name"]
            for item in body["items"][0]["monitoring_agents"]
        ]
        self.assertEqual(
            names,
            [
                "leakage_fraud_monitoring_agent",
                "leakage_duplicate_payment_monitoring_agent",
                "leakage_overpayment_monitoring_agent",
                "leakage_controls_monitoring_agent",
            ],
        )
        self.assertEqual(
            body["items"][0]["monitoring_agents"][0]["order"],
            1,
        )

    def test_list_all_monitoring_agents(self) -> None:
        client = TestClient(_build_app())
        response = client.get("/api/monitoring-agents")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 4)
        agents = {item["agent"] for item in body["items"]}
        self.assertEqual(
            agents,
            {"finance", "cashflow", "collection", "leakage"},
        )

    def test_clear_alerts(self) -> None:
        with patch(
            "src.actions.service.repository.clear_alerts",
            return_value={"alerts_deleted": 3, "actions_deleted": 5},
        ) as clear:
            client = TestClient(_build_app())
            response = client.request(
                "DELETE",
                "/api/alerts",
                params={"agent": "finance"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["agent"], "finance")
            self.assertEqual(body["alerts_deleted"], 3)
            self.assertEqual(body["actions_deleted"], 5)
            clear.assert_called_once()

    def test_populate_runs_passes_sequentially_with_previous_alerts(self) -> None:
        first_output = MagicMock()
        first_output.model_dump.return_value = {
            "alerts": [
                {
                    "name": "Suspected fraud",
                    "issue": "Vendor bank change without callback.",
                    "subagent": "leakage_fraud_monitoring_agent",
                    "actions": [
                        {
                            "name": "Hold vendor payment",
                            "routes": ["A/P"],
                            "agent": "leakage",
                            "impact": "Cash leakage prevented",
                            "spec": "Hold payments for vendor with unverified bank change.",
                        }
                    ],
                }
            ]
        }
        second_output = MagicMock()
        second_output.model_dump.return_value = {
            "alerts": [
                {
                    "name": "none",
                    "issue": "no alert detected",
                    "subagent": "leakage_duplicate_payment_monitoring_agent",
                    "actions": [],
                }
            ]
        }
        third_output = MagicMock()
        third_output.model_dump.return_value = {
            "alerts": [
                {
                    "name": "Overbilling spike",
                    "issue": "Invoice exceeds PO by 12%.",
                    "subagent": "leakage_overpayment_monitoring_agent",
                    "actions": [],
                }
            ]
        }
        fourth_output = MagicMock()
        fourth_output.model_dump.return_value = {
            "alerts": [
                {
                    "name": "none",
                    "issue": "no alert detected",
                    "subagent": "leakage_controls_monitoring_agent",
                    "actions": [],
                }
            ]
        }

        results = [
            MagicMock(output=first_output),
            MagicMock(output=second_output),
            MagicMock(output=third_output),
            MagicMock(output=fourth_output),
        ]
        fake_chivon = MagicMock()
        fake_chivon.run_async = AsyncMock(side_effect=results)

        saved_alerts: list[str] = []

        def fake_save_alert(session, **kwargs):
            alert_id = f"alert-{len(saved_alerts) + 1}"
            saved_alerts.append(alert_id)
            return alert_id

        def fake_save_action(session, **kwargs):
            return f"action-{kwargs['alert_id']}"

        with (
            patch(
                "src.actions.service.repository.get_alerts",
                return_value=[
                    {
                        "name": "Existing leakage",
                        "issue": "Already known issue",
                        "subagent": "prior",
                    }
                ],
            ),
            patch(
                "src.actions.service.repository.save_alert",
                side_effect=fake_save_alert,
            ),
            patch(
                "src.actions.service.repository.save_action",
                side_effect=fake_save_action,
            ),
            patch(
                "src.actions.service.get_chivon",
                return_value=fake_chivon,
            ),
        ):
            client = TestClient(_build_app())
            response = client.post("/api/alerts/populate?agent=leakage")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["agent"], "leakage")
            self.assertEqual(body["monitoring_passes"], 4)
            self.assertEqual(body["created_count"], 2)
            self.assertEqual(fake_chivon.run_async.await_count, 4)

            # Second pass should see existing + first new alert.
            second_call = fake_chivon.run_async.await_args_list[1].args[1]
            previous = second_call["previous_alerts"]
            self.assertEqual(len(previous), 2)
            self.assertEqual(previous[0]["name"], "Existing leakage")
            self.assertEqual(previous[1]["name"], "Suspected fraud")

            # Third pass should see 3 priors (existing + 1 created; none skipped).
            third_call = fake_chivon.run_async.await_args_list[2].args[1]
            self.assertEqual(len(third_call["previous_alerts"]), 2)


class ActionStatusHelperTest(unittest.TestCase):
    def test_pending_maps_to_planned(self) -> None:
        self.assertEqual(
            repository._normalize_status("Pending"),
            "planned",
        )

    def test_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValueError):
            repository._normalize_status("done")


if __name__ == "__main__":
    unittest.main()
