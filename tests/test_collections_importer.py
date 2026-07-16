from __future__ import annotations

import unittest

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scripts.import_excel import import_collections
from src.db.db import get_engine
from src.db.models import (
    CollectionAssumption,
    CollectionDsoCashImpact,
    CollectionRecommendation,
    CollectionRiskScore,
    CollectionRiskTierExposure,
    CollectionWorklistItem,
    CustomerCreditAging,
    ImportBatch,
)


class CollectionsImporterTest(unittest.TestCase):
    def test_full_import_inside_rollback_transaction(
        self,
    ) -> None:
        engine = get_engine()
        connection = engine.connect()
        transaction = connection.begin()
        session = Session(
            bind=connection,
            expire_on_commit=False,
        )

        workbook = load_workbook(
            import_collections.WORKBOOK_PATH,
            data_only=True,
            read_only=True,
        )

        try:
            import_collections.validate_workbook(
                workbook
            )

            import_batch_id = (
                import_collections.create_import_batch(
                    session
                )
            )

            row_counts = {
                "assumptions": (
                    import_collections.import_assumptions(
                        session,
                        workbook["01 Assumptions"],
                        import_batch_id,
                    )
                ),
                "customer_credit_aging": (
                    import_collections
                    .import_customer_credit_aging(
                        session,
                        workbook[
                            "02 Customer Credit & Aging"
                        ],
                        import_batch_id,
                    )
                ),
                "risk_scores": (
                    import_collections.import_risk_scores(
                        session,
                        workbook["03 Risk Scoring"],
                        import_batch_id,
                    )
                ),
                "dso_cash_impact": (
                    import_collections
                    .import_dso_cash_impact(
                        session,
                        workbook[
                            "04 DSO & Cash Impact"
                        ],
                        import_batch_id,
                    )
                ),
                "risk_tier_exposure": (
                    import_collections
                    .import_risk_tier_exposure(
                        session,
                        workbook[
                            "04 DSO & Cash Impact"
                        ],
                        import_batch_id,
                    )
                ),
                "worklist": (
                    import_collections.import_worklist(
                        session,
                        workbook[
                            "05 Collections Worklist"
                        ],
                        import_batch_id,
                    )
                ),
                "recommendations": (
                    import_collections
                    .import_recommendations(
                        session,
                        workbook["06 Recommendation"],
                        import_batch_id,
                    )
                ),
            }

            total_rows = sum(row_counts.values())

            import_collections.mark_batch_completed(
                session,
                import_batch_id,
                total_rows,
            )

            session.flush()

            self.assertEqual(
                row_counts["assumptions"],
                18,
            )

            self.assertEqual(
                row_counts["customer_credit_aging"],
                12,
            )

            self.assertEqual(
                row_counts["risk_scores"],
                12,
            )

            self.assertEqual(
                row_counts["dso_cash_impact"],
                1,
            )

            self.assertEqual(
                row_counts["risk_tier_exposure"],
                3,
            )

            self.assertEqual(
                row_counts["worklist"],
                10,
            )

            self.assertEqual(
                row_counts["recommendations"],
                9,
            )

            self.assertEqual(
                total_rows,
                65,
            )

            import_batch = session.get(
                ImportBatch,
                import_batch_id,
            )

            self.assertIsNotNone(import_batch)

            if import_batch is None:
                self.fail(
                    "Collections import batch was not created."
                )

            self.assertEqual(
                import_batch.import_status,
                "COMPLETED",
            )

            self.assertEqual(
                import_batch.total_rows,
                65,
            )

            customer_count = session.scalar(
                select(func.count())
                .select_from(CustomerCreditAging)
                .where(
                    CustomerCreditAging.import_batch_id
                    == import_batch_id
                )
            )

            self.assertEqual(
                customer_count,
                12,
            )

            total_ar = session.scalar(
                select(
                    func.sum(
                        CustomerCreditAging.total_ar_idr_mn
                    )
                ).where(
                    CustomerCreditAging.import_batch_id
                    == import_batch_id
                )
            )

            self.assertEqual(
                total_ar,
                110000,
            )

            total_overdue = session.scalar(
                select(
                    func.sum(
                        CustomerCreditAging.overdue_idr_mn
                    )
                ).where(
                    CustomerCreditAging.import_batch_id
                    == import_batch_id
                )
            )

            self.assertEqual(
                total_overdue,
                37935,
            )

            high_risk_customer = session.scalars(
                select(CollectionRiskScore).where(
                    CollectionRiskScore.import_batch_id
                    == import_batch_id,
                    CollectionRiskScore.risk_tier
                    == "High",
                )
            ).one()

            self.assertEqual(
                high_risk_customer.customer_name,
                "CV Berkah Jaya",
            )

            self.assertEqual(
                float(high_risk_customer.risk_score),
                71.0,
            )

            dso_impact = session.scalars(
                select(CollectionDsoCashImpact).where(
                    CollectionDsoCashImpact.import_batch_id
                    == import_batch_id
                )
            ).one()

            self.assertAlmostEqual(
                float(dso_impact.current_dso_days),
                57.357143,
                places=6,
            )

            self.assertAlmostEqual(
                float(
                    dso_impact.cash_freed_at_target_idr_mn
                ),
                19863.01369863,
                places=6,
            )

            expected_recovery = session.scalar(
                select(
                    func.sum(
                        CollectionWorklistItem
                        .expected_recovery_idr_mn
                    )
                ).where(
                    CollectionWorklistItem.import_batch_id
                    == import_batch_id
                )
            )

            self.assertEqual(
                expected_recovery,
                32163.25,
            )

            model_counts = {
                "assumptions": session.scalar(
                    select(func.count())
                    .select_from(CollectionAssumption)
                    .where(
                        CollectionAssumption.import_batch_id
                        == import_batch_id
                    )
                ),
                "risk_tier_exposure": session.scalar(
                    select(func.count())
                    .select_from(
                        CollectionRiskTierExposure
                    )
                    .where(
                        CollectionRiskTierExposure
                        .import_batch_id
                        == import_batch_id
                    )
                ),
                "recommendations": session.scalar(
                    select(func.count())
                    .select_from(
                        CollectionRecommendation
                    )
                    .where(
                        CollectionRecommendation
                        .import_batch_id
                        == import_batch_id
                    )
                ),
            }

            self.assertEqual(
                model_counts["assumptions"],
                18,
            )

            self.assertEqual(
                model_counts["risk_tier_exposure"],
                3,
            )

            self.assertEqual(
                model_counts["recommendations"],
                9,
            )

        finally:
            workbook.close()
            session.close()

            if transaction.is_active:
                transaction.rollback()

            connection.close()


if __name__ == "__main__":
    unittest.main()