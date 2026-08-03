"""Prove the `newdata` import is correct, using the dataset's own acceptance suite.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/verify_new_dataset.py

Two independent checks, neither of them ours:

  RECONCILIATION  the 14 checks on sheet 90_Reconciliation, re-expressed as SQL.
                  They are Excel formulas in the workbook and cannot be ported
                  mechanically, so each one is rewritten and its source formula
                  is quoted beside it to be argued with.

  KPIs            the 25 values on sheet 50_Agent_KPIs, each of which ships its
                  own derivation. Every derivable one is recomputed from the
                  facts and compared with the value the workbook states.

A failure here means the dataset or the import is wrong, not the application.
Run this before anything is built on top of `newdata`.

Exit code is 0 when every check passes, 1 otherwise. POLICY rows never fail:
they are stated constants (a board buffer, a target DSO) with no fact to derive
them from, so they are printed for a human to accept rather than computed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402

SALES = "newdata.fact_sales"
OPEX = "newdata.fact_opex"
AR = "newdata.fact_ar_invoices"
AP = "newdata.fact_ap_invoices"
WEEKLY = "newdata.fact_cashflow_weekly"
LINES = "newdata.fact_cashflow_lines"
BRIDGE = "newdata.finance_ebitda_bridge"

# The reporting window. The workbook's own formulas use month_index >= 202510,
# which is the twelve months to Sep 2026 — not the August the old dataset used.
LAST_12M = "month_index >= 202510"

# (number, label, formula quoted from the sheet, SQL A, SQL B, tolerance)
RECONCILIATION = [
    (
        1,
        "Total net revenue ties to gross less discount",
        "SUM(N) vs SUM(L)-SUM(M)",
        f"SELECT SUM(net_revenue_idr_mn) FROM {SALES}",
        f"SELECT SUM(gross_revenue_idr_mn) - SUM(discount_idr_mn) FROM {SALES}",
        1.0,
    ),
    (
        2,
        "Gross margin ties to revenue less COGS",
        "SUM(P) vs SUM(N)-SUM(O)",
        f"SELECT SUM(gross_margin_idr_mn) FROM {SALES}",
        f"SELECT SUM(net_revenue_idr_mn) - SUM(cogs_idr_mn) FROM {SALES}",
        1.0,
    ),
    (
        3,
        "EBITDA from the ledger equals EBITDA from the bridge",
        "SUMIFS(P, month_index>=202510) - SUMIFS(opex H) vs bridge steps + budget",
        f"""
        SELECT (SELECT SUM(gross_margin_idr_mn) FROM {SALES} WHERE {LAST_12M})
             - (SELECT SUM(actual_idr_mn) FROM {OPEX} WHERE {LAST_12M})
        """,
        f"""
        SELECT (SELECT SUM(value_idr_mn) FROM {BRIDGE} WHERE type = 'step')
             + (SELECT value_idr_mn FROM {BRIDGE} WHERE step = 'Budget EBITDA')
        """,
        1.0,
    ),
    (
        4,
        "Opex variance ties to actual less budget",
        "SUM(J) vs SUM(H)-SUM(I)",
        f"SELECT SUM(variance_idr_mn) FROM {OPEX}",
        f"SELECT SUM(actual_idr_mn) - SUM(budget_idr_mn) FROM {OPEX}",
        1.0,
    ),
    (
        5,
        "Open AR equals the sum of the ageing buckets",
        "SUMIF(status=Open) vs sum of the five bucket SUMIFs",
        f"SELECT SUM(invoice_amount_idr_mn) FROM {AR} WHERE status = 'Open'",
        f"""
        SELECT SUM(invoice_amount_idr_mn) FROM {AR}
        WHERE aging_bucket IN
            ('Current', '1-30 days', '31-60 days', '61-90 days', '90+ days')
        """,
        1.0,
    ),
    (
        6,
        "DSO denominator equals the Finance revenue base",
        "SUMIFS(N, month_index>=202510) vs 365 x daily credit sales",
        f"SELECT SUM(net_revenue_idr_mn) FROM {SALES} WHERE {LAST_12M}",
        """
        SELECT 365 * value FROM newdata.agent_kpis
        WHERE metric = 'Daily credit sales'
        """,
        5.0,
    ),
    (
        7,
        "Expected recovery equals invoice value times the tier rate",
        "SUMIF(status=Open, P) vs SUMPRODUCT(K, Q)",
        f"""
        SELECT SUM(expected_recovery_idr_mn) FROM {AR} WHERE status = 'Open'
        """,
        f"""
        SELECT SUM(invoice_amount_idr_mn * expected_recovery_pct) FROM {AR}
        """,
        1.0,
    ),
    (
        8,
        "Overdue AR equals open AR less the current bucket",
        "SUMIFS(status=Open, dpd>0) vs open AR - current bucket",
        f"""
        SELECT SUM(invoice_amount_idr_mn) FROM {AR}
        WHERE status = 'Open' AND days_past_due > 0
        """,
        f"""
        SELECT (SELECT SUM(invoice_amount_idr_mn) FROM {AR} WHERE status = 'Open')
             - (SELECT SUM(invoice_amount_idr_mn) FROM {AR}
                WHERE aging_bucket = 'Current')
        """,
        1.0,
    ),
    (
        9,
        "Leakage at risk equals the sum of the case amounts",
        "SUM(T) vs blocked + recoverable + lost",
        f"SELECT SUM(leakage_amount_idr_mn) FROM {AP}",
        f"""
        SELECT SUM(leakage_amount_idr_mn) FROM {AP}
        WHERE leakage_status IN
            ('Blocked before payment', 'Paid - recoverable',
             'Lost - not recoverable')
        """,
        1.0,
    ),
    (
        10,
        "Leakage categories sum to the same total",
        "SUM(T) vs the five leakage_type SUMIFs",
        f"SELECT SUM(leakage_amount_idr_mn) FROM {AP}",
        f"""
        SELECT SUM(leakage_amount_idr_mn) FROM {AP}
        WHERE leakage_type IN
            ('Bank-change fraud', 'Duplicate payment', 'Overbilling (3-way)',
             'Lost discount', 'Split / threshold')
        """,
        1.0,
    ),
    (
        11,
        "Weekly net movement equals inflows plus outflows",
        "SUM(E) vs SUM(C)+SUM(D)",
        f"SELECT SUM(net_movement_idr_mn) FROM {WEEKLY}",
        f"SELECT SUM(inflows_idr_mn) + SUM(outflows_idr_mn) FROM {WEEKLY}",
        1.0,
    ),
    (
        12,
        "Week 13 closing cash equals opening plus all movements",
        "INDEX(F,13) vs INDEX(B,1) + SUM(E)",
        f"""
        SELECT closing_cash_idr_mn FROM {WEEKLY}
        ORDER BY _row_order DESC LIMIT 1
        """,
        f"""
        SELECT (SELECT opening_cash_idr_mn FROM {WEEKLY}
                ORDER BY _row_order LIMIT 1)
             + (SELECT SUM(net_movement_idr_mn) FROM {WEEKLY})
        """,
        1.0,
    ),
    (
        13,
        "Headroom equals closing cash less the buffer",
        "SUM(H) vs SUM(F)-SUM(G)",
        f"SELECT SUM(headroom_idr_mn) FROM {WEEKLY}",
        f"SELECT SUM(closing_cash_idr_mn) - SUM(min_buffer_idr_mn) FROM {WEEKLY}",
        1.0,
    ),
    (
        14,
        "Treasury AR receipts trace to the Collection AR book",
        "SUMIF(cash_line='AR collection - existing book') vs open expected recovery",
        f"""
        SELECT SUM(amount_idr_mn) FROM {LINES}
        WHERE cash_line = 'AR collection - existing book'
        """,
        f"""
        SELECT SUM(expected_recovery_idr_mn) FROM {AR} WHERE status = 'Open'
        """,
        1.0,
    ),
]

# Each entry recomputes one row of 50_Agent_KPIs from the facts. `None` marks a
# stated policy constant with no fact behind it — printed, never failed.
KPI_DERIVATIONS: dict[str, str | None] = {
    "Net revenue (last 12m)":
        f"SELECT SUM(net_revenue_idr_mn) FROM {SALES} WHERE {LAST_12M}",
    "Gross margin %":
        f"""
        SELECT SUM(gross_margin_idr_mn) / SUM(net_revenue_idr_mn)
        FROM {SALES} WHERE {LAST_12M}
        """,
    "Operating expenses":
        f"SELECT SUM(actual_idr_mn) FROM {OPEX} WHERE {LAST_12M}",
    "Opex / revenue":
        f"""
        SELECT (SELECT SUM(actual_idr_mn) FROM {OPEX} WHERE {LAST_12M})
             / (SELECT SUM(net_revenue_idr_mn) FROM {SALES} WHERE {LAST_12M})
        """,
    "EBITDA":
        f"""
        SELECT (SELECT SUM(gross_margin_idr_mn) FROM {SALES} WHERE {LAST_12M})
             - (SELECT SUM(actual_idr_mn) FROM {OPEX} WHERE {LAST_12M})
        """,
    "EBITDA %":
        f"""
        SELECT ((SELECT SUM(gross_margin_idr_mn) FROM {SALES} WHERE {LAST_12M})
              - (SELECT SUM(actual_idr_mn) FROM {OPEX} WHERE {LAST_12M}))
             / (SELECT SUM(net_revenue_idr_mn) FROM {SALES} WHERE {LAST_12M})
        """,
    "EBITDA % budget": None,
    "Total open AR":
        f"SELECT SUM(invoice_amount_idr_mn) FROM {AR} WHERE status = 'Open'",
    "Overdue AR":
        f"""
        SELECT SUM(invoice_amount_idr_mn) FROM {AR}
        WHERE status = 'Open' AND days_past_due > 0
        """,
    "Overdue % of AR":
        f"""
        SELECT (SELECT SUM(invoice_amount_idr_mn) FROM {AR}
                WHERE status = 'Open' AND days_past_due > 0)
             / (SELECT SUM(invoice_amount_idr_mn) FROM {AR} WHERE status = 'Open')
        """,
    "Daily credit sales":
        f"""
        SELECT SUM(net_revenue_idr_mn) / 365 FROM {SALES} WHERE {LAST_12M}
        """,
    "DSO":
        f"""
        SELECT (SELECT SUM(invoice_amount_idr_mn) FROM {AR} WHERE status = 'Open')
             / ((SELECT SUM(net_revenue_idr_mn) FROM {SALES} WHERE {LAST_12M}) / 365)
        """,
    "Target DSO": None,
    "Cash freed at target DSO": None,
    "At risk this cycle":
        f"SELECT SUM(leakage_amount_idr_mn) FROM {AP}",
    "Blocked before payment":
        f"""
        SELECT SUM(leakage_amount_idr_mn) FROM {AP}
        WHERE leakage_status = 'Blocked before payment'
        """,
    "Paid - recoverable":
        f"""
        SELECT SUM(leakage_amount_idr_mn) FROM {AP}
        WHERE leakage_status = 'Paid - recoverable'
        """,
    "Lost - not recoverable":
        f"""
        SELECT SUM(leakage_amount_idr_mn) FROM {AP}
        WHERE leakage_status = 'Lost - not recoverable'
        """,
    "Number of flags":
        f"SELECT COUNT(*) FROM {AP} WHERE leakage_amount_idr_mn > 0",
    "Opening cash":
        f"""
        SELECT opening_cash_idr_mn FROM {WEEKLY} ORDER BY _row_order LIMIT 1
        """,
    "Minimum cash buffer":
        f"SELECT MIN(min_buffer_idr_mn) FROM {WEEKLY}",
    "Lowest weekly closing cash":
        f"SELECT MIN(closing_cash_idr_mn) FROM {WEEKLY}",
    "Weeks below buffer":
        f"""
        SELECT COUNT(*) FROM {WEEKLY}
        WHERE closing_cash_idr_mn < min_buffer_idr_mn
        """,
    "Net USD exposure":
        "SELECT SUM(amount_usd) FROM newdata.fact_fx_exposure",
    "Recommended hedge": None,
}


def scalar(connection, statement: str) -> float | None:
    value = connection.execute(text(statement)).scalar()
    return None if value is None else float(value)


def relative_ok(a: float, b: float, tolerance: float) -> bool:
    """Absolute tolerance, or 0.5% for values small enough that 1.0 is coarse.

    The workbook checks with ABS(diff) < 1 against figures in the hundreds of
    thousands. Applied to a ratio like 0.248 that would pass anything, so
    proportions are compared proportionally.
    """
    if abs(a) < 10 and abs(b) < 10:
        return abs(a - b) <= max(abs(a), abs(b)) * 0.005 + 1e-9
    return abs(a - b) < tolerance


def main() -> int:
    failures = 0

    with get_engine().connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))

        print("=" * 78)
        print("RECONCILIATION — the 14 checks from sheet 90_Reconciliation")
        print("=" * 78)

        for number, label, formula, sql_a, sql_b, tolerance in RECONCILIATION:
            try:
                a = scalar(connection, sql_a)
                b = scalar(connection, sql_b)
            except Exception as error:  # noqa: BLE001 - report, do not abort
                print(f"\nERROR  #{number:<2} {label}\n       {error}")
                failures += 1
                continue

            if a is None or b is None:
                print(f"\nERROR  #{number:<2} {label}\n       returned NULL")
                failures += 1
                continue

            passed = relative_ok(a, b, tolerance)
            failures += 0 if passed else 1
            print(f"\n{'PASS' if passed else 'FAIL'}   #{number:<2} {label}")
            print(f"       {formula}")
            print(f"       A = {a:>18,.2f}")
            print(f"       B = {b:>18,.2f}   diff {a - b:,.4f}")

        print()
        print("=" * 78)
        print("KPIs — the values on sheet 50_Agent_KPIs, recomputed from facts")
        print("=" * 78)

        stated = connection.execute(
            text(
                """
                SELECT agent, metric, value, unit
                FROM newdata.agent_kpis
                ORDER BY _row_order
                """
            )
        ).fetchall()

        for agent, metric, value, unit in stated:
            derivation = KPI_DERIVATIONS.get(metric, "MISSING")
            expected = float(value)

            if derivation == "MISSING":
                print(f"\nSKIP   {agent:<11} {metric}")
                print("       no derivation written for this metric")
                continue

            if derivation is None:
                print(f"\nPOLICY {agent:<11} {metric}")
                print(f"       stated as {expected:,.4f} {unit}; no fact derives it")
                continue

            try:
                computed = scalar(connection, derivation)
            except Exception as error:  # noqa: BLE001
                print(f"\nERROR  {agent:<11} {metric}\n       {error}")
                failures += 1
                continue

            if computed is None:
                print(f"\nERROR  {agent:<11} {metric}\n       returned NULL")
                failures += 1
                continue

            passed = relative_ok(computed, expected, 1.0)
            failures += 0 if passed else 1
            print(f"\n{'PASS' if passed else 'FAIL'}   {agent:<11} {metric}")
            print(f"       stated   {expected:>18,.4f} {unit}")
            print(f"       computed {computed:>18,.4f}   diff {computed - expected:,.4f}")

    print()
    print("=" * 78)
    if failures:
        print(f"{failures} check(s) failed. The dataset or the import is wrong.")
        print("Do not build on newdata until these are settled.")
    else:
        print("All checks passed. newdata is safe to build on.")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
