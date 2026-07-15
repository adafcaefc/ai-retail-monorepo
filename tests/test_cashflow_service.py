from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.cashflow.models import CashFlowSimulationRequest
from src.cashflow.service import get_baseline, simulate


class CashFlowBaselineTest(unittest.TestCase):
    def test_baseline_uses_latest_database_import(self) -> None:
        baseline = get_baseline()

        self.assertGreater(
            baseline.import_batch_id,
            0,
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


class CashFlowSimulationTest(unittest.TestCase):
    def test_base_case_remains_in_shortage(self) -> None:
        request = CashFlowSimulationRequest(
            accelerate_collection_idr_mn=0,
            defer_payment_idr_mn=0,
            credit_line_draw_idr_mn=0,
            hedge_usd=0,
        )

        result = simulate(request)

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

        result = simulate(request)

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

        result = simulate(request)

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