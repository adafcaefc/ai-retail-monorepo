"""The one place that says which workbook the warehouse is allowed to hold.

WHY THIS EXISTS
`seed_retail_facts_from_json.py` and `seed_retail_dims_from_json.py` load
`resources/dbtemp/schema_with_data.json` from whatever checkout they are run
in, and neither used to look at where that extract came from. Three machines
seed this one Azure database, and on 2026-08-19 the fact tables were rewritten
six or seven times, flipping between two different workbooks -- chain-net ROP
for DGT-001 read 5813 at 15:00 local, 7474 at 17:00, and 5813 again at 17:45.
Nobody ran the wrong command. Each run faithfully copied the extract sitting in
its own checkout, and the basis in Azure ended up belonging to whoever seeded
last.

So the rule is not "be careful": it is that a seeder refuses an extract taken
from a workbook the repo has not pinned. A run from a stale checkout stops with
a message naming both hashes instead of quietly replacing 800 rows.

WHY A HASH AND NOT THE FILE NAME
The two workbooks in play differ in content, not in name -- `source_workbook`
reads `Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx` in extracts of
both. Only the bytes tell them apart.

CHANGING THE PINNED WORKBOOK
When the workbook is deliberately replaced, update EXPECTED_WORKBOOK_SHA256
here in the same commit that lands the new extract, so the pin and the data it
describes move together and the diff shows both. `--allow-workbook-change`
exists for the run that has to happen before that commit; it is a loud
override, not a way of life, and callers record it in the audit row.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FLAG = "--allow-workbook-change"

# `Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx`, 10,003,637 bytes.
# The workbook whose ENGINE sheet stores the ROP column every retail board
# reconciles against: 302 SKUs below reorder point, states 106/196/399/51/40/8.
EXPECTED_WORKBOOK_NAME = "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"
EXPECTED_WORKBOOK_SHA256 = (
    "5d7c0c72d25cc2deacffe8f0364be946105f9af85354d36d9b9d13e819a6ae74"
)

HASH_FIELD = "source_workbook_sha256"


class WorkbookMismatch(RuntimeError):
    """The extract was taken from a workbook this repo has not pinned."""


def verify(payload: dict[str, Any], *, allow_change: bool = False) -> str:
    """Check a parsed extract against the pinned workbook. Returns its hash.

    Call this after parsing and BEFORE the first write. The seeders delete a
    table before they refill it, so a check that runs late is a check that runs
    after the damage.

    An extract with no recorded hash fails as loudly as a mismatched one. It
    predates this guard, which means nothing knows which workbook produced it --
    accepting it on the grounds that it might be fine is the exact behaviour
    that let two bases take turns in the warehouse.
    """
    found = payload.get(HASH_FIELD)
    name = payload.get("source_workbook", "(unnamed)")

    if not found:
        if allow_change:
            return ""
        raise WorkbookMismatch(
            f"the extract records no {HASH_FIELD}, so the workbook behind it is "
            f"unknown.\n"
            f"  extract names : {name}\n"
            f"  fix           : re-run scripts/extract_workbook_schema.py against "
            f"{EXPECTED_WORKBOOK_NAME}\n"
            f"  override      : --allow-workbook-change"
        )

    if found != EXPECTED_WORKBOOK_SHA256:
        if allow_change:
            return found
        raise WorkbookMismatch(
            "this extract came from a different workbook than the one the repo "
            "pins.\n"
            f"  expected : {EXPECTED_WORKBOOK_SHA256}\n"
            f"             {EXPECTED_WORKBOOK_NAME}\n"
            f"  found    : {found}\n"
            f"             {name}\n"
            "  Seeding would replace the warehouse with the other workbook's "
            "figures.\n"
            "  fix      : pull the branch carrying the pinned extract, or re-run "
            "scripts/extract_workbook_schema.py\n"
            "  override : --allow-workbook-change (records the override in the "
            "audit row)"
        )

    return found


def describe(found: str, *, overridden: bool) -> str:
    """One line for the seeder to print, so a run says which workbook it used."""
    if overridden:
        shown = found or "(none recorded)"
        return f"WARN  workbook check overridden -- seeding from {shown[:16]}"
    return f"  ok  workbook {found[:16]} matches the pinned extract"


def overridden(argv: list[str] | None = None) -> bool:
    """Whether this run carries the override flag."""
    return FLAG in (sys.argv if argv is None else argv)


def check(source: Path, *, allow_change: bool | None = None) -> tuple[str, bool]:
    """Guard one extract file. Returns (hash, was_overridden), or exits non-zero.

    The seeders each keep their own `load_tables`, which parses the extract and
    keeps only the rows; this parses it again rather than reworking that
    signature, which a test also calls. Half a second against a run that
    rewrites 36,000 rows is not the cost worth optimising, and the guard has to
    hold the header the loader throws away.
    """
    allow = overridden() if allow_change is None else allow_change
    payload = json.loads(source.read_text(encoding="utf-8"))
    try:
        found = verify(payload, allow_change=allow)
    except WorkbookMismatch as error:
        print(f"FAIL  {error}")
        raise SystemExit(1) from error
    print(describe(found, overridden=allow))
    return found, allow
