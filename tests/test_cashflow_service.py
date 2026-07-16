from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.cashflow.models import CashFlowSimulationRequest
from src.cashflow.router import router
from src.cashflow.service import get_baseline, simulate
from src.db.db import get_db_session
from src.db.models import (
    ApPayable,
    ArCollection,
    Assumption,
    Base,
    ImportBatch,
    WeeklyForecast,
)


class CashFlowDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            execution_options={
                "schema_translate_map": {
                    "audit": None,
                    "cashflow": None,
                }
            },
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self._seed_cashflow_data()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _seed_cashflow_data(self) -> None:
        older_batch = ImportBatch(
            id=1,
            agent_name="cashflow_agent",
            workbook_name="older.xlsx",
            workbook_version="v0.9",
            import_status="COMPLETED",
            imported_at=datetime(
                2026,
                7,
                1,
                tzinfo=timezone.utc,
            ),
        )
        latest_batch = ImportBatch(
            id=2,
            agent_name="cashflow_agent",
            workbook_name="cashflow-demo.xlsx",
            workbook_version="v1.0",
            import_status="COMPLETED",
            imported_at=datetime(
                2026,
                7,
                15,
                tzinfo=timezone.utc,
            ),
            completed_at=datetime(
                2026,
                7,
                15,
                tzinfo=timezone.utc,
            ),
        )

        assumptions = [
            Assumption(
                id=1,
                import_batch_id=2,
                assumption_group="POLICY_AND_LIQUIDITY",
                assumption_name="Minimum cash buffer (IDR mn)",
                numeric_value=Decimal("8000"),
            ),
            Assumption(
                id=2,
                import_batch_id=2,
                assumption_group="FX_ASSUMPTIONS",
                assumption_name="Spot USD/IDR",
                numeric_value=Decimal("17950"),
            ),
            Assumption(
                id=3,
                import_batch_id=2,
                assumption_group="FX_ASSUMPTIONS",
                assumption_name="13-week forward USD/IDR",
                numeric_value=Decimal("18120"),
            ),
            Assumption(
                id=4,
                import_batch_id=2,
                assumption_group="FX_ASSUMPTIONS",
                assumption_name=(
                    "Adverse rate  = spot x (1+adverse)"
                ),
                numeric_value=Decimal("18488.5"),
            ),
        ]

        customer_delay = ArCollection(
            id=1,
            import_batch_id=2,
            invoice_number="AR-012",
            customer_name="Customer A",
            original_week=5,
            expected_week=7,
            currency="USD",
            usd_amount=Decimal("1700000"),
            idr_value_mn=Decimal("8000"),
            notes="Illustrative delayed collection",
        )
        deferrable_payment = ApPayable(
            id=1,
            import_batch_id=2,
            bill_number="AP-015",
            vendor_name="Vendor A",
            payment_week=5,
            currency="USD",
            amount_idr_mn=Decimal("3000"),
            usd_amount=Decimal("5000000"),
            is_deferrable=True,
            notes="Illustrative deferrable payment",
        )

        weekly_forecasts = [
            WeeklyForecast(
                id=1,
                import_batch_id=2,
                week_number=5,
                opening_cash_idr_mn=Decimal("10000"),
                closing_cash_idr_mn=Decimal("6997.5"),
                minimum_buffer_idr_mn=Decimal("8000"),
                headroom_idr_mn=Decimal("-1002.5"),
                status="SHORTAGE",
            ),
            WeeklyForecast(
                id=2,
                import_batch_id=2,
                week_number=6,
                opening_cash_idr_mn=Decimal("6997.5"),
                closing_cash_idr_mn=Decimal("9012.5"),
                minimum_buffer_idr_mn=Decimal("8000"),
                headroom_idr_mn=Decimal("1012.5"),
                status="OK",
            ),
            WeeklyForecast(
                id=3,
                import_batch_id=2,
                week_number=7,
                opening_cash_idr_mn=Decimal("9012.5"),
                closing_cash_idr_mn=Decimal("21112.5"),
                minimum_buffer_idr_mn=Decimal("8000"),
                headroom_idr_mn=Decimal("13112.5"),
                status="OK",
            ),
        ]

        self.session.add_all(
            [
                older_batch,
                latest_batch,
                *assumptions,
                customer_delay,
                deferrable_payment,
                *weekly_forecasts,
            ]
        )
        self.session.commit()


class CashFlowBaselineTest(CashFlowDatabaseTestCase):
    def test_baseline_uses_latest_database_import(self) -> None:
        baseline = get_baseline(self.session)

        self.assertEqual(
            baseline.import_batch_id,
            2,
        )

        self.assertEqual(
            baseline.minimum_buffer_idr_mn,
            8000.0,
        )

        self.assertEqual(
            baseline.net_usd_exposure,
            3300000.0,
        )

        self.assertEqual(
            baseline.recommended_hedge_usd,
            2000000.0,
        )

        self.assertEqual(
            baseline.spot_rate_idr_per_usd,
            17950.0,
        )

        self.assertEqual(
            baseline.forward_rate_idr_per_usd,
            18120.0,
        )

        self.assertEqual(
            baseline.adverse_rate_idr_per_usd,
            18488.5,
        )

        weekly_positions = {
            position.week_number: position
            for position in baseline.weekly_positions
        }

        self.assertEqual(
            weekly_positions[5].closing_cash_idr_mn,
            6997.5,
        )

        self.assertEqual(
            weekly_positions[6].closing_cash_idr_mn,
            9012.5,
        )

        self.assertEqual(
            weekly_positions[7].closing_cash_idr_mn,
            21112.5,
        )

        self.assertEqual(
            baseline.customer_delay_driver.reference_number,
            "AR-012",
        )

        self.assertEqual(
            baseline.customer_delay_driver.amount_idr_mn,
            8000.0,
        )

        self.assertEqual(
            baseline.customer_delay_driver.original_week,
            5,
        )

        self.assertEqual(
            baseline.customer_delay_driver.expected_week,
            7,
        )

        self.assertEqual(
            baseline.deferrable_payment_driver.reference_number,
            "AP-015",
        )

        self.assertEqual(
            baseline.deferrable_payment_driver.amount_idr_mn,
            3000.0,
        )

        self.assertTrue(
            baseline.deferrable_payment_driver.is_deferrable
        )


class CashFlowRouterTest(CashFlowDatabaseTestCase):
    def setUp(self) -> None:
        super().setUp()

        app = FastAPI()
        app.include_router(router)

        def override_session():
            yield self.session

        app.dependency_overrides[
            get_db_session
        ] = override_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        super().tearDown()

    def test_cashflow_endpoints_use_orm_session(self) -> None:
        baseline_response = self.client.get(
            "/api/cashflow/baseline"
        )
        simulation_response = self.client.post(
            "/api/cashflow/simulate",
            json={
                "accelerate_collection_idr_mn": 2000,
                "hedge_usd": 2000000,
            },
        )

        self.assertEqual(baseline_response.status_code, 200)
        self.assertEqual(
            baseline_response.json()["import_batch_id"],
            2,
        )
        self.assertEqual(simulation_response.status_code, 200)
        self.assertEqual(
            simulation_response.json()["status"],
            "SAFE",
        )

    def test_cashflow_adaptive_card_endpoints(self) -> None:
        baseline_response = self.client.get(
            "/api/cashflow/adaptive-card"
        )
        simulation_response = self.client.post(
            "/api/cashflow/adaptive-card/simulate",
            json={
                "accelerate_collection_idr_mn": 2000,
                "hedge_usd": 2000000,
            },
        )

        self.assertEqual(baseline_response.status_code, 200)
        baseline_card = baseline_response.json()["adaptiveCard"]
        self.assertEqual(baseline_card["type"], "AdaptiveCard")
        self.assertEqual(baseline_card["version"], "1.5")
        self.assertEqual(baseline_card["body"][2]["type"], "Chart.Line")
        self.assertEqual(
            len(baseline_card["body"][2]["data"][0]["values"]),
            3,
        )
        baseline_action = (
            baseline_card["body"][3]["items"][-1]["actions"][0]
        )
        self.assertEqual(
            baseline_action["data"]["action"],
            "simulate_cashflow",
        )

        self.assertEqual(simulation_response.status_code, 200)
        simulation_payload = simulation_response.json()
        self.assertEqual(simulation_payload["data"]["status"], "SAFE")
        simulation_chart = simulation_payload["adaptiveCard"]["body"][1]
        self.assertEqual(simulation_chart["type"], "Chart.Line")
        self.assertEqual(len(simulation_chart["data"]), 3)


class CashFlowSimulationTest(CashFlowDatabaseTestCase):
    def test_base_case_remains_in_shortage(self) -> None:
        request = CashFlowSimulationRequest(
            accelerate_collection_idr_mn=0,
            defer_payment_idr_mn=0,
            credit_line_draw_idr_mn=0,
            hedge_usd=0,
        )

        result = simulate(request, self.session)

        self.assertEqual(
            result.status,
            "SHORTAGE",
        )

        self.assertEqual(
            result.week5_cash_idr_mn,
            6997.5,
        )

        self.assertEqual(
            result.weeks_below_buffer,
            1,
        )

    def test_recommended_scenario_is_safe(self) -> None:
        request = CashFlowSimulationRequest(
            accelerate_collection_idr_mn=2000,
            defer_payment_idr_mn=0,
            credit_line_draw_idr_mn=0,
            hedge_usd=2000000,
        )

        result = simulate(request, self.session)

        self.assertEqual(
            result.status,
            "SAFE",
        )

        self.assertEqual(
            result.week5_cash_idr_mn,
            8997.5,
        )

        self.assertEqual(
            result.week6_cash_idr_mn,
            9012.5,
        )

        self.assertEqual(
            result.week7_cash_idr_mn,
            19112.5,
        )

        self.assertEqual(
            result.week5_headroom_idr_mn,
            997.5,
        )

        self.assertEqual(
            result.week6_headroom_idr_mn,
            1012.5,
        )

        self.assertEqual(
            result.week7_headroom_idr_mn,
            11112.5,
        )

        self.assertEqual(
            result.weeks_below_buffer,
            0,
        )

        self.assertAlmostEqual(
            result.hedge_coverage_pct,
            60.61,
            places=2,
        )

        self.assertEqual(
            result.fx_downside_avoided_idr_mn,
            1077.0,
        )

        self.assertEqual(
            result.forward_premium_idr_mn,
            340.0,
        )

    def test_payment_deferral_creates_week6_risk(self) -> None:
        request = CashFlowSimulationRequest(
            accelerate_collection_idr_mn=5000,
            defer_payment_idr_mn=3000,
            credit_line_draw_idr_mn=0,
            hedge_usd=2000000,
        )

        result = simulate(request, self.session)

        self.assertEqual(
            result.status,
            "WEEK 6 RISK",
        )

        self.assertEqual(
            result.week5_cash_idr_mn,
            14997.5,
        )

        self.assertEqual(
            result.week6_cash_idr_mn,
            6012.5,
        )

        self.assertEqual(
            result.week7_cash_idr_mn,
            16112.5,
        )

        self.assertEqual(
            result.weeks_below_buffer,
            1,
        )

    def test_collection_cannot_exceed_customer_balance(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            CashFlowSimulationRequest(
                accelerate_collection_idr_mn=9000,
                defer_payment_idr_mn=0,
                credit_line_draw_idr_mn=0,
                hedge_usd=0,
            )

    def test_deferral_cannot_exceed_eligible_payment(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            CashFlowSimulationRequest(
                accelerate_collection_idr_mn=0,
                defer_payment_idr_mn=4000,
                credit_line_draw_idr_mn=0,
                hedge_usd=0,
            )

    def test_hedge_cannot_exceed_net_exposure(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            CashFlowSimulationRequest(
                accelerate_collection_idr_mn=0,
                defer_payment_idr_mn=0,
                credit_line_draw_idr_mn=0,
                hedge_usd=4000000,
            )


if __name__ == "__main__":
    unittest.main()