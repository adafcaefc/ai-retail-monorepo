"""Prove (or disprove) the reported Leakage / Finance / Collection defects.

Run it yourself:

    cd backend
    ../.venv/Scripts/python.exe ../scripts/verify_agent_bugs.py

This is the companion to `verify_new_dataset.py`, and the distinction matters:

    verify_new_dataset.py   is the DATA right?   (dataset -> newdata tables)
    verify_agent_bugs.py    is the APP right?    (newdata tables -> what the
                            dashboard actually puts on screen)

`verify_new_dataset.py` passes today. Every defect below therefore sits in
application code, not in the import: the correct number is already in the
database and the dashboard reports a different one.

Each check states EXPECTED (recomputed from `newdata` here, independently of
the agent) against ACTUAL (read out of the real dashboard payload), so a
disagreement is evidence rather than opinion.

Verdicts:

    BUG   the defect reproduces -- actual disagrees with the database
    OK    the defect does not reproduce (this is what a fix looks like)

Exit code is 0 when nothing reproduces, 1 while any BUG remains. That makes
this a regression gate: run it before a fix to see the defect, after a fix to
see it gone, and in CI to keep it gone.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from src.db.db import get_engine  # noqa: E402
from src.llm.agents import get_agent  # noqa: E402

# The reporting window every Finance figure uses: the twelve months to Sep 2026.
LAST_12M = "month >= '2025-10-01'"

TOL = 1.0  # IDR mn, the same tolerance sheet 90_Reconciliation uses.

results: list[tuple[str, str, str]] = []


def scalar(sql: str) -> float:
    with get_engine().connect() as connection:
        value = connection.execute(text(sql)).scalar()
    return float(value or 0)


def rows(sql: str) -> list[tuple]:
    with get_engine().connect() as connection:
        return [tuple(r) for r in connection.execute(text(sql))]


def dashboard(agent_id: str, entity: str | None = None) -> dict[str, Any]:
    return get_agent(agent_id).build_dashboard(entity, None, None)


def tile(payload: dict[str, Any], label: str) -> Any:
    for kpi in payload.get("kpis", []):
        if kpi.get("label") == label:
            return kpi.get("value_num", kpi.get("value"))
    return None


def view(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return (payload.get("views") or {}).get(name) or {}


def bars(payload: dict[str, Any], name: str) -> dict[str, float]:
    return {
        str(p.get("label")): float(p.get("value") or 0)
        for p in (view(payload, name).get("data") or [])
    }


def report(
    check: str,
    agent: str,
    title: str,
    expected: Any,
    actual: Any,
    ok: bool,
    note: str = "",
) -> None:
    verdict = "OK " if ok else "BUG"
    results.append((verdict, check, f"{agent} - {title}"))
    print(f"\n{verdict}  [{check}] {agent} - {title}")
    print(f"       expected (from newdata): {expected}")
    print(f"       actual   (on dashboard): {actual}")
    if note:
        print(f"       {note}")


def money(value: float) -> str:
    return f"{value:,.2f}"


# ----------------------------------------------------------------------------
# LEAKAGE
# ----------------------------------------------------------------------------

def check_leakage() -> None:
    print("\n" + "=" * 78)
    print("LEAKAGE")
    print("=" * 78)

    truth = dict(
        rows(
            "SELECT leakage_status, SUM(leakage_amount_idr_mn) "
            "FROM newdata.leakage_cases GROUP BY 1"
        )
    )
    blocked_db = float(truth.get("Blocked before payment", 0))
    recover_db = float(truth.get("Paid - recoverable", 0))
    lost_db = float(truth.get("Lost - not recoverable", 0))
    at_risk_db = blocked_db + recover_db + lost_db

    board = dashboard("finance.leakage")

    # L1 -- the split itself. `leakage_cases.payment_status` is only ever
    # Blocked/Pending, so a filter on payment_status='Paid' matches nothing and
    # everything lands in "blocked".
    blocked_ui = float(tile(board, "Blocked") or 0)
    report(
        "L1",
        "Leakage",
        "blocked / recoverable / lost split",
        f"blocked {money(blocked_db)}, recoverable {money(recover_db)}, "
        f"lost {money(lost_db)}",
        f"blocked {money(blocked_ui)}, recoverable/lost see L3",
        abs(blocked_ui - blocked_db) <= TOL,
        "root cause: leakage_data.py groups on payment_status, "
        "the dataset defines these on leakage_status",
    )

    # L3 -- a chart named "blocked vs recoverable vs lost" has to partition the
    # at-risk total, not exceed it.
    bv = bars(board, "blockvs")
    total_ui = sum(bv.values())
    report(
        "L3",
        "Leakage",
        "'Blocked vs recoverable vs lost' bars must sum to at-risk",
        f"{money(at_risk_db)} (= {money(blocked_db)} + {money(recover_db)} "
        f"+ {money(lost_db)})",
        f"{money(total_ui)} from {bv}",
        abs(total_ui - at_risk_db) <= TOL,
        f"bars are {total_ui / at_risk_db * 100:.0f}% of the total they split"
        if at_risk_db
        else "",
    )

    # L4 -- protection rises with the claw-back rate, and can never exceed the
    # money at risk.
    rec = bars(board, "recovery")
    over = {k: v for k, v in rec.items() if v > at_risk_db + TOL}
    ordered = list(rec.values()) == sorted(rec.values())
    report(
        "L4",
        "Leakage",
        "'Recovery scenario' must rise with the rate and stay under at-risk",
        f"every bar <= {money(at_risk_db)}, ascending pessimistic->current",
        f"{rec}",
        not over and ordered,
        f"bars above the at-risk line: {over}" if over else "ordering inverted",
    )

    # L5 -- the simulator splits blocked into fraud + other, and recoverable
    # into duplicates + overbilling. Those four are the money still in play,
    # so they sum to blocked + recoverable. Lost cash is not in the simulator
    # because no lever moves it, which is why this is not at-risk.
    base = (board.get("simulator") or {}).get("baseline") or {}
    parts = (
        float(base.get("fraud") or 0)
        + float(base.get("other_blocked") or 0)
        + float(base.get("duplicates_amount") or 0)
        + float(base.get("overbill_amount") or 0)
    )
    in_play_db = blocked_db + recover_db
    report(
        "L5",
        "Leakage",
        "simulator baseline components reconcile to blocked + recoverable",
        f"{money(in_play_db)} (= {money(blocked_db)} + {money(recover_db)}; "
        f"lost {money(lost_db)} has no lever)",
        f"{money(parts)} from {base}",
        abs(parts - in_play_db) <= TOL,
    )

    # L2 -- the entity slices. This is the one that fabricates: an entity with
    # no fraud case still shows a fraud tile, because the dashboard substitutes
    # a hardcoded 3,800 when its lookup comes back empty.
    for entity in ("LE-ID01", "LE-SG01", "LE-MY01"):
        fraud_db = scalar(
            "SELECT COALESCE(SUM(leakage_amount_idr_mn), 0) "
            "FROM newdata.leakage_cases "
            f"WHERE legal_entity_id = '{entity}' "
            "AND leakage_type = 'Bank-change fraud'"
        )
        dup_db = scalar(
            "SELECT COALESCE(SUM(leakage_amount_idr_mn), 0) "
            "FROM newdata.leakage_cases "
            f"WHERE legal_entity_id = '{entity}' "
            "AND leakage_type = 'Duplicate payment'"
        )
        flagged_db = scalar(
            "SELECT COALESCE(SUM(leakage_amount_idr_mn), 0) "
            f"FROM newdata.leakage_cases WHERE legal_entity_id = '{entity}'"
        )
        slice_board = dashboard("finance.leakage", entity)
        fraud_ui = float(tile(slice_board, "Fraud held") or 0)
        dup_ui = float(tile(slice_board, "Duplicates") or 0)
        flagged_ui = float(tile(slice_board, "Flagged this cycle") or 0)
        ok = abs(fraud_ui - fraud_db) <= TOL and abs(dup_ui - dup_db) <= TOL
        report(
            f"L2/{entity}",
            "Leakage",
            f"entity tiles are real, not substituted ({entity})",
            f"fraud {money(fraud_db)}, duplicates {money(dup_db)}, "
            f"flagged {money(flagged_db)}",
            f"fraud {money(fraud_ui)}, duplicates {money(dup_ui)}, "
            f"flagged {money(flagged_ui)}",
            ok,
            f"components {money(fraud_ui + dup_ui)} vs flagged "
            f"{money(flagged_ui)} - components exceed the total"
            if fraud_ui + dup_ui > flagged_ui + TOL
            else "",
        )

    # L6 -- three of the four monitoring passes still name the legacy tables,
    # which the runtime allow-list rejects.
    config = (
        REPO
        / "backend/src/llm/agents/finance/leakage/config"
        / "finance_leakage_monitoring.json"
    ).read_text(encoding="utf-8")
    legacy = config.count("payment_leakage.")
    report(
        "L6",
        "Leakage",
        "monitoring config points at live tables",
        "0 references to payment_leakage.* (legacy schema)",
        f"{legacy} references to payment_leakage.*",
        legacy == 0,
        "these queries are refused at runtime by LEAKAGE_ALLOWED_TABLES",
    )


# ----------------------------------------------------------------------------
# FINANCE
# ----------------------------------------------------------------------------

def check_finance() -> None:
    print("\n" + "=" * 78)
    print("FINANCE")
    print("=" * 78)

    board = dashboard("finance.finance")

    # F1 -- the opex table. fact_opex carries the real five-line split; the
    # dashboard probes column names that no longer exist and falls back to a
    # hardcoded illustrative table from the previous dataset.
    opex_db = scalar(
        f"SELECT SUM(actual_idr_mn) FROM newdata.fact_opex WHERE {LAST_12M}"
    )
    table = (view(board, "opex").get("table") or {}).get("rows") or []
    total_ui = 0.0
    for row in table:
        if str(row[0]).lower().startswith("total"):
            total_ui = float(str(row[1]).replace(",", ""))
    report(
        "F1",
        "Finance",
        "opex table total matches fact_opex",
        money(opex_db),
        money(total_ui),
        abs(total_ui - opex_db) <= TOL,
        f"off by {opex_db / total_ui:.0f}x - and the KPI tile on the same "
        f"board implies {money(opex_db)}"
        if total_ui
        else "",
    )

    # F1b -- the per-line split is available and should be used.
    lines_db = rows(
        "SELECT opex_line, SUM(actual_idr_mn) FROM newdata.fact_opex "
        f"WHERE {LAST_12M} GROUP BY 1 ORDER BY 2 DESC"
    )
    ui_lines = {
        str(r[0]): float(str(r[1]).replace(",", ""))
        for r in table
        if not str(r[0]).lower().startswith("total")
    }
    matched = sum(
        1
        for name, amount in lines_db
        if abs(ui_lines.get(str(name), -1) - float(amount)) <= TOL
    )
    report(
        "F1b",
        "Finance",
        "opex lines are the real ones",
        f"{len(lines_db)} lines, e.g. "
        + ", ".join(f"{n} {money(float(a))}" for n, a in lines_db[:2]),
        f"{matched}/{len(lines_db)} lines match; shown: "
        + ", ".join(f"{k} {money(v)}" for k, v in list(ui_lines.items())[:2]),
        matched == len(lines_db),
    )

    # F2 -- a waterfall has to walk from its first bar to its last. Under an
    # entity filter the endpoints are scoped but the steps are not, so it
    # stops adding up.
    for entity in (None, "LE-SG01"):
        slice_board = dashboard("finance.finance", entity)
        data = view(slice_board, "drivers").get("data") or []
        values = [float(p.get("value") or 0) for p in data]
        if len(values) < 3:
            continue
        walk = sum(values[:-1])
        landing = values[-1]
        report(
            f"F2/{entity or 'group'}",
            "Finance",
            f"EBITDA waterfall reconciles ({entity or 'no filter'})",
            f"budget + steps == actual bar ({money(landing)})",
            f"budget + steps = {money(walk)}",
            abs(walk - landing) <= TOL,
            f"gap of {money(abs(walk - landing))} - endpoints follow the "
            "entity filter, the steps do not"
            if abs(walk - landing) > TOL
            else "",
        )


# ----------------------------------------------------------------------------
# COLLECTION
# ----------------------------------------------------------------------------

def check_collection() -> None:
    print("\n" + "=" * 78)
    print("COLLECTION")
    print("=" * 78)

    board = dashboard("finance.collection")
    ageing = bars(board, "aging")

    open_ar_db = scalar(
        "SELECT SUM(invoice_amount_idr_mn) FROM newdata.fact_ar_invoices "
        "WHERE status = 'Open'"
    )
    current_db = scalar(
        "SELECT SUM(invoice_amount_idr_mn) FROM newdata.fact_ar_invoices "
        "WHERE status = 'Open' AND aging_bucket = 'Current'"
    )

    # C1 -- the Current bar is summed from a truncated customer list, so it
    # loses every customer who has no overdue at all.
    current_ui = ageing.get("Current", 0.0)
    report(
        "C1",
        "Collection",
        "ageing 'Current' bar matches open AR in that bucket",
        money(current_db),
        money(current_ui),
        abs(current_ui - current_db) <= TOL,
        f"short by {money(current_db - current_ui)} - the snapshot returns "
        "25 of 40 customers and the chart sums that list",
    )

    # C1b -- and therefore the whole chart disagrees with the KPI beside it.
    total_ui = sum(ageing.values())
    ar_tile = float(tile(board, "AR outstanding") or 0)
    report(
        "C1b",
        "Collection",
        "ageing bars sum to the AR outstanding tile",
        f"{money(open_ar_db)} (tile reads {money(ar_tile)})",
        f"{money(total_ui)} from {ageing}",
        abs(total_ui - ar_tile) <= TOL,
        "chart and KPI tile disagree on the same board",
    )

    # C1c -- the overdue buckets are fine, which is what makes C1 easy to miss.
    overdue_db = scalar(
        "SELECT SUM(invoice_amount_idr_mn) FROM newdata.fact_ar_invoices "
        "WHERE status = 'Open' AND aging_bucket <> 'Current'"
    )
    overdue_ui = sum(v for k, v in ageing.items() if k != "Current")
    report(
        "C1c",
        "Collection",
        "overdue buckets are correct (control check)",
        money(overdue_db),
        money(overdue_ui),
        abs(overdue_ui - overdue_db) <= TOL,
        "expected to pass — isolates the defect to the Current bucket",
    )

    # C2 -- a scenario run that names no customer. This used to fall back to
    # the literal "PT Anugerah Prima (Customer A)", the previous dataset's
    # label for CU-001; the current dataset drops the suffix, the lookup is a
    # substring match, and so the call failed with "Customer was not found".
    # The fix resolves the customer from the ledger instead, so the check is
    # whether the call runs and lands on the most overdue customer -- not
    # whether some hardcoded name still happens to match.
    from src.llm.agents.finance.collection.tools.collection_data import (  # noqa: PLC0415
        calculate_collection_scenario,
    )

    top_overdue = rows(
        """
        SELECT customer_name
        FROM newdata.fact_ar_invoices
        WHERE status = 'Open'
        GROUP BY customer_id, customer_name
        ORDER BY SUM(invoice_amount_idr_mn)
            FILTER (WHERE days_past_due > 0) DESC NULLS LAST
        LIMIT 1
        """
    )
    expected_customer = top_overdue[0][0] if top_overdue else "(none)"
    try:
        resolved = calculate_collection_scenario(
            cash_to_collect_idr_mn=100
        )["customer_name"]
    except Exception as error:  # noqa: BLE001 - the defect is any failure here
        resolved = f"raised {type(error).__name__}: {error}"

    report(
        "C2",
        "Collection",
        "a scenario with no customer named resolves from the ledger",
        f"{expected_customer!r} (the most overdue customer)",
        f"{resolved!r}",
        resolved == expected_customer,
    )


def main() -> int:
    print(__doc__.split("Verdicts:")[0].strip())
    check_leakage()
    check_finance()
    check_collection()

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    bugs = [r for r in results if r[0] == "BUG"]
    for verdict, check, title in results:
        print(f"  {verdict}  {check:14} {title}")
    print(
        f"\n{len(bugs)} of {len(results)} checks reproduce a defect."
        if bugs
        else f"\nAll {len(results)} checks clean."
    )
    return 1 if bugs else 0


if __name__ == "__main__":
    raise SystemExit(main())
