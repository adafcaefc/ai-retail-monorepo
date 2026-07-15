from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[2]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from src.db.db import get_session_factory
from src.db.models import (
    ApPayable,
    ArCollection,
    Assumption,
    FxScenario,
    ImportBatch,
    OtherOutflow,
    Recommendation,
    WeeklyForecast,
)


WORKBOOK_NAME = (
    "03B_Cash Flow Agent Demo Aug 2026 "
    "Data Engine v1.0 20260707.xlsx"
)

WORKBOOK_PATH = BACKEND_ROOT / "data" / WORKBOOK_NAME

WORKBOOK_VERSION = "v1.0-20260707"
AGENT_NAME = "cashflow_agent"

EXPECTED_SHEETS = [
    "02 Assumptions",
    "03 AR Collections",
    "04 AP USD Payables",
    "05 Other Outflows",
    "06 Cash Forecast 13W",
    "07 FX Scenarios",
    "08 Recommendation",
]


def as_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return None


def as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    if isinstance(value, Decimal):
        return value

    if isinstance(value, bool):
        return Decimal(int(value))

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    try:
        cleaned_value = str(value).replace(",", "")
        return Decimal(cleaned_value)
    except Exception:
        return None


def as_integer(value: Any) -> int | None:
    if value is None or value == "":
        return None

    return int(value)


def as_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def validate_workbook(workbook: Any) -> None:
    missing_sheets = [
        sheet_name
        for sheet_name in EXPECTED_SHEETS
        if sheet_name not in workbook.sheetnames
    ]

    if missing_sheets:
        raise RuntimeError(
            "Missing required worksheets: "
            + ", ".join(missing_sheets)
        )


def create_import_batch(
    session: Session,
) -> int:
    imported_by = session.scalar(
        select(func.current_user())
    )

    import_batch = ImportBatch(
        agent_name=AGENT_NAME,
        workbook_name=WORKBOOK_NAME,
        workbook_version=WORKBOOK_VERSION,
        workbook_path=str(WORKBOOK_PATH),
        import_status="STARTED",
        imported_by=imported_by,
        total_sheets=len(EXPECTED_SHEETS),
        total_rows=0,
        metadata_json={
            "source": "Excel Data Engine",
            "data_type": "illustrative_demo_data",
            "scope": "Cash Flow Intelligence Agent",
        },
    )

    session.add(import_batch)
    session.flush()

    if import_batch.id is None:
        raise RuntimeError("Failed to create import batch.")

    return int(import_batch.id)


def import_assumptions(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    row_groups = {
        5: "COMPANY_PROFILE",
        6: "COMPANY_PROFILE",
        7: "COMPANY_PROFILE",
        8: "COMPANY_PROFILE",
        11: "FORECAST_SETUP",
        12: "FORECAST_SETUP",
        13: "FORECAST_SETUP",
        16: "FX_ASSUMPTIONS",
        17: "FX_ASSUMPTIONS",
        18: "FX_ASSUMPTIONS",
        19: "FX_ASSUMPTIONS",
        20: "FX_ASSUMPTIONS",
        21: "FX_ASSUMPTIONS",
        24: "POLICY_AND_LIQUIDITY",
        25: "POLICY_AND_LIQUIDITY",
        26: "POLICY_AND_LIQUIDITY",
        27: "POLICY_AND_LIQUIDITY",
    }

    units = {
        11: "date",
        12: "weeks",
        13: "text",
        16: "IDR per USD",
        17: "IDR per USD",
        18: "percentage",
        19: "percentage",
        20: "IDR per USD",
        21: "IDR per USD",
        24: "IDR million",
        25: "IDR million",
    }

    records: list[Assumption] = []

    for row_number, assumption_group in row_groups.items():
        assumption_name = worksheet.cell(
            row=row_number,
            column=1,
        ).value

        value = worksheet.cell(
            row=row_number,
            column=2,
        ).value

        notes = worksheet.cell(
            row=row_number,
            column=4,
        ).value

        numeric_value = None
        text_value = None
        date_value = None

        if isinstance(value, datetime):
            date_value = value.date()
        elif isinstance(value, date):
            date_value = value
        elif isinstance(value, (int, float, Decimal)):
            numeric_value = as_decimal(value)
        else:
            text_value = as_text(value)

        records.append(
            Assumption(
                import_batch_id=import_batch_id,
                assumption_group=assumption_group,
                assumption_name=as_text(assumption_name),
                numeric_value=numeric_value,
                text_value=text_value,
                date_value=date_value,
                unit=units.get(row_number),
                notes=as_text(notes),
            )
        )

    session.add_all(records)

    return len(records)


def import_ar_collections(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    records: list[ArCollection] = []

    for row_number in range(5, 31):
        invoice_number = worksheet.cell(
            row=row_number,
            column=1,
        ).value

        if not invoice_number:
            continue

        records.append(
            ArCollection(
                import_batch_id=import_batch_id,
                invoice_number=as_text(invoice_number),
                customer_name=as_text(
                    worksheet.cell(row_number, 2).value
                ),
                customer_segment=as_text(
                    worksheet.cell(row_number, 3).value
                ),
                invoice_date=as_date(
                    worksheet.cell(row_number, 4).value
                ),
                payment_terms_days=as_integer(
                    worksheet.cell(row_number, 5).value
                ),
                due_date=as_date(
                    worksheet.cell(row_number, 6).value
                ),
                original_week=as_integer(
                    worksheet.cell(row_number, 7).value
                ),
                expected_week=as_integer(
                    worksheet.cell(row_number, 8).value
                ),
                currency=as_text(
                    worksheet.cell(row_number, 9).value
                ),
                amount_idr_mn=as_decimal(
                    worksheet.cell(row_number, 10).value
                ),
                usd_amount=as_decimal(
                    worksheet.cell(row_number, 11).value
                ),
                idr_value_mn=as_decimal(
                    worksheet.cell(row_number, 12).value
                ),
                delay_flag=as_text(
                    worksheet.cell(row_number, 13).value
                ),
                notes=as_text(
                    worksheet.cell(row_number, 14).value
                ),
            )
        )

    session.add_all(records)

    return len(records)


def import_ap_payables(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    records: list[ApPayable] = []

    for row_number in range(5, 28):
        bill_number = worksheet.cell(
            row=row_number,
            column=1,
        ).value

        if not bill_number:
            continue

        deferrable_value = as_text(
            worksheet.cell(row_number, 11).value
        )

        is_deferrable = (
            deferrable_value is not None
            and deferrable_value.lower() == "yes"
        )

        records.append(
            ApPayable(
                import_batch_id=import_batch_id,
                bill_number=as_text(bill_number),
                vendor_name=as_text(
                    worksheet.cell(row_number, 2).value
                ),
                category=as_text(
                    worksheet.cell(row_number, 3).value
                ),
                payment_terms_days=as_integer(
                    worksheet.cell(row_number, 4).value
                ),
                due_date=as_date(
                    worksheet.cell(row_number, 5).value
                ),
                payment_week=as_integer(
                    worksheet.cell(row_number, 6).value
                ),
                currency=as_text(
                    worksheet.cell(row_number, 7).value
                ),
                amount_idr_mn=as_decimal(
                    worksheet.cell(row_number, 8).value
                ),
                usd_amount=as_decimal(
                    worksheet.cell(row_number, 9).value
                ),
                idr_value_mn=as_decimal(
                    worksheet.cell(row_number, 10).value
                ),
                is_deferrable=is_deferrable,
                notes=as_text(
                    worksheet.cell(row_number, 12).value
                ),
            )
        )

    session.add_all(records)

    return len(records)


def import_other_outflows(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    records: list[OtherOutflow] = []

    for row_number in range(5, 10):
        category = as_text(
            worksheet.cell(row_number, 1).value
        )

        if not category:
            continue

        for week_number in range(1, 14):
            amount = worksheet.cell(
                row=row_number,
                column=week_number + 1,
            ).value

            records.append(
                OtherOutflow(
                    import_batch_id=import_batch_id,
                    category=category,
                    week_number=week_number,
                    amount_idr_mn=(
                        as_decimal(amount) or Decimal("0")
                    ),
                )
            )

    session.add_all(records)

    return len(records)


def import_weekly_forecast(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    records: list[WeeklyForecast] = []

    row_mapping = {
        "week_start": 5,
        "week_end": 6,
        "customer_collections": 8,
        "total_inflows": 9,
        "vendor_payments_idr": 11,
        "vendor_payments_usd": 12,
        "payroll": 13,
        "rent_utilities_opex": 14,
        "taxes": 15,
        "loan_repayment": 16,
        "total_outflows": 17,
        "net_cash_flow": 19,
        "opening_cash": 20,
        "closing_cash": 21,
        "minimum_buffer": 22,
        "headroom": 23,
        "status": 24,
    }

    for week_number in range(1, 14):
        column_number = week_number + 1

        records.append(
            WeeklyForecast(
                import_batch_id=import_batch_id,
                week_number=week_number,
                week_start=as_date(
                    worksheet.cell(
                        row_mapping["week_start"],
                        column_number,
                    ).value
                ),
                week_end=as_date(
                    worksheet.cell(
                        row_mapping["week_end"],
                        column_number,
                    ).value
                ),
                customer_collections_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["customer_collections"],
                        column_number,
                    ).value
                ),
                total_inflows_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["total_inflows"],
                        column_number,
                    ).value
                ),
                vendor_payments_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["vendor_payments_idr"],
                        column_number,
                    ).value
                ),
                vendor_payments_usd_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["vendor_payments_usd"],
                        column_number,
                    ).value
                ),
                payroll_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["payroll"],
                        column_number,
                    ).value
                ),
                rent_utilities_opex_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["rent_utilities_opex"],
                        column_number,
                    ).value
                ),
                taxes_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["taxes"],
                        column_number,
                    ).value
                ),
                loan_repayment_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["loan_repayment"],
                        column_number,
                    ).value
                ),
                total_outflows_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["total_outflows"],
                        column_number,
                    ).value
                ),
                net_cash_flow_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["net_cash_flow"],
                        column_number,
                    ).value
                ),
                opening_cash_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["opening_cash"],
                        column_number,
                    ).value
                ),
                closing_cash_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["closing_cash"],
                        column_number,
                    ).value
                ),
                minimum_buffer_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["minimum_buffer"],
                        column_number,
                    ).value
                ),
                headroom_idr_mn=as_decimal(
                    worksheet.cell(
                        row_mapping["headroom"],
                        column_number,
                    ).value
                ),
                status=as_text(
                    worksheet.cell(
                        row_mapping["status"],
                        column_number,
                    ).value
                ),
            ),
        )

    session.add_all(records)

    return len(records)


def import_fx_scenarios(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    records: list[FxScenario] = []

    net_usd_exposure = as_decimal(
        worksheet.cell(7, 2).value
    )

    for row_number in range(12, 16):
        records.append(
            FxScenario(
                import_batch_id=import_batch_id,
                scenario_name=as_text(
                    worksheet.cell(row_number, 1).value
                ),
                usd_exposure=net_usd_exposure,
                fx_rate_idr_per_usd=as_decimal(
                    worksheet.cell(row_number, 2).value
                ),
                movement_vs_spot=as_decimal(
                    worksheet.cell(row_number, 3).value
                ),
                fx_cash_impact_idr_mn=as_decimal(
                    worksheet.cell(row_number, 4).value
                ),
                notes=as_text(
                    worksheet.cell(row_number, 5).value
                ),
                is_recommended=False,
            )
        )

    for row_number in range(29, 33):
        scenario_name = as_text(
            worksheet.cell(row_number, 1).value
        )

        is_recommended = (
            scenario_name is not None
            and "RECOMMENDED" in scenario_name.upper()
        )

        records.append(
            FxScenario(
                import_batch_id=import_batch_id,
                scenario_name=scenario_name,
                action_description=as_text(
                    worksheet.cell(row_number, 2).value
                ),
                usd_exposure=net_usd_exposure,
                downside_avoided_idr_mn=as_decimal(
                    worksheet.cell(row_number, 3).value
                ),
                premium_idr_mn=as_decimal(
                    worksheet.cell(row_number, 4).value
                ),
                liquidity_effect=as_text(
                    worksheet.cell(row_number, 5).value
                ),
                confidence_label=as_text(
                    worksheet.cell(row_number, 6).value
                ),
                is_recommended=is_recommended,
            )
        )

    session.add_all(records)

    return len(records)


def import_recommendations(
    session: Session,
    worksheet: Any,
    import_batch_id: int,
) -> int:
    recommendation_rows = [
        (14, "LIQUIDITY"),
        (15, "LIQUIDITY"),
        (16, "LIQUIDITY"),
        (19, "FX"),
        (20, "FX"),
        (21, "GOVERNANCE"),
    ]

    records: list[Recommendation] = []

    for recommendation_order, item in enumerate(
        recommendation_rows,
        start=1,
    ):
        row_number, recommendation_type = item

        action_title = as_text(
            worksheet.cell(row_number, 1).value
        )

        action_description = as_text(
            worksheet.cell(row_number, 3).value
        )

        expected_impact = as_text(
            worksheet.cell(row_number, 5).value
        )

        if not action_title:
            continue

        if not action_description:
            action_description = action_title

        records.append(
            Recommendation(
                import_batch_id=import_batch_id,
                recommendation_type=recommendation_type,
                recommendation_order=recommendation_order,
                action_title=action_title,
                action_description=action_description,
                expected_impact=expected_impact,
                assumptions=[],
                risks=[],
                requires_approval=True,
                approval_route="CFO + Treasury Manager",
            )
        )

    session.add_all(records)

    return len(records)


def mark_batch_completed(
    session: Session,
    import_batch_id: int,
    total_rows: int,
) -> None:
    import_batch = session.get(ImportBatch, import_batch_id)

    if import_batch is None:
        raise RuntimeError(
            f"Import batch not found: {import_batch_id}"
        )

    import_batch.import_status = "COMPLETED"
    import_batch.completed_at = datetime.now(timezone.utc)
    import_batch.total_rows = total_rows


def record_failed_import(error_message: str) -> None:
    with get_session_factory().begin() as session:
        imported_by = session.scalar(
            select(func.current_user())
        )

        session.add(
            ImportBatch(
                agent_name=AGENT_NAME,
                workbook_name=WORKBOOK_NAME,
                workbook_version=WORKBOOK_VERSION,
                workbook_path=str(WORKBOOK_PATH),
                import_status="FAILED",
                imported_by=imported_by,
                total_sheets=len(EXPECTED_SHEETS),
                total_rows=0,
                error_message=error_message[:5000],
                metadata_json={
                    "source": "Excel Data Engine",
                    "data_type": "illustrative_demo_data",
                },
            )
        )


def main() -> None:
    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(
            f"Workbook not found: {WORKBOOK_PATH}"
        )

    print(f"Opening workbook: {WORKBOOK_PATH.name}")

    workbook = load_workbook(
        WORKBOOK_PATH,
        data_only=True,
        read_only=True,
    )

    validate_workbook(workbook)

    row_counts: dict[str, int] = {}

    try:
        with get_session_factory().begin() as session:
            import_batch_id = create_import_batch(session)

            print(
                f"Import batch created: {import_batch_id}"
            )

            row_counts["assumptions"] = import_assumptions(
                session,
                workbook["02 Assumptions"],
                import_batch_id,
            )

            row_counts["ar_collections"] = (
                import_ar_collections(
                    session,
                    workbook["03 AR Collections"],
                    import_batch_id,
                )
            )

            row_counts["ap_payables"] = import_ap_payables(
                session,
                workbook["04 AP USD Payables"],
                import_batch_id,
            )

            row_counts["other_outflows"] = (
                import_other_outflows(
                    session,
                    workbook["05 Other Outflows"],
                    import_batch_id,
                )
            )

            row_counts["weekly_forecast"] = (
                import_weekly_forecast(
                    session,
                    workbook["06 Cash Forecast 13W"],
                    import_batch_id,
                )
            )

            row_counts["fx_scenarios"] = (
                import_fx_scenarios(
                    session,
                    workbook["07 FX Scenarios"],
                    import_batch_id,
                )
            )

            row_counts["recommendations"] = (
                import_recommendations(
                    session,
                    workbook["08 Recommendation"],
                    import_batch_id,
                )
            )

            total_rows = sum(row_counts.values())

            mark_batch_completed(
                session,
                import_batch_id,
                total_rows,
            )

        print("")
        print("Cash Flow workbook import completed.")
        print(f"Import batch ID: {import_batch_id}")

        for table_name, row_count in row_counts.items():
            print(f"{table_name}: {row_count} rows")

        print(
            f"Total imported rows: {sum(row_counts.values())}"
        )

    except Exception as error:
        print("")
        print("Import failed.")
        print(f"Error: {error}")

        try:
            record_failed_import(str(error))
        except Exception as audit_error:
            print(
                "Failed to record import error: "
                f"{audit_error}"
            )

        raise

    finally:
        workbook.close()


if __name__ == "__main__":
    main()