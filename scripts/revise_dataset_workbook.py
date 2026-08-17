"""Port the engine-formula fixes from Dataset_AI_Retail.xlsx into the v8.2 workbook.

Run it yourself (dry run first -- it writes nothing):

    cd backend
    ../.venv/Scripts/python.exe ../scripts/revise_dataset_workbook.py
    ../.venv/Scripts/python.exe ../scripts/revise_dataset_workbook.py --apply

Why this exists: markdown in the What-If Simulator did not work, and the cause
was in the engine formulas rather than the data. A corrected workbook
(`Dataset_AI_Retail.xlsx`) exists but also drops three workforce formulas that
the code and `retail.formula` still reference, so it is used as a reference to
port from rather than adopted wholesale.

Driven through real Excel via win32com, NOT openpyxl. Reading this workbook
with openpyxl emits "Conditional Formatting extension is not supported and will
be removed" and "Unknown extension is not supported and will be removed" --
saving through it would strip those and the nine chart sheets. Excel also
recalculates, which openpyxl cannot do, so the verification numbers below are
real rather than stale cached values.

Every formula is read **verbatim, cell by cell**, out of the reference and
written to the same address in the target. Nothing is filled down and no
formula string is rewritten. That matters because the Workforce lookups are
fully absolute (`=Stores!$A$6`): assigning one such string to a whole column
would point all 160 rows at store S001. Reading the real block sidesteps the
question entirely -- whatever the reference has per row is what the target
gets, whether the reference shifts references per row or not.

What is deliberately NOT ported: the removal of `Required (workforce)`,
`Scheduled (roster)` and `Coverage gap` from the Formulas sheet. Those map to
f17/f18/f19, which are still registered in `retail.formula` and still
referenced in code. The Formulas sheet therefore ends up at 28 metrics: the 16
both workbooks share, those 3, and the 9 the reference adds.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "resources" / "Copy of AI_360_Retail_Dataset_v8.2_General_20260806.xlsx"

# The reference workbook is deliberately NOT kept in the repo -- one 15 MB
# binary that is only ever read is not worth versioning next to the 15 MB one
# that is. Point --reference at wherever your copy lives; the default is where
# it was downloaded to.
DEFAULT_REFERENCE = Path.home() / "Downloads" / "Dataset_AI_Retail.xlsx"

# (sheet, header row, first data row, last data row)
SHEETS = {
    "ENGINE": (5, 6, 805),
    "ENGINE_STORE": (3, 4, 16003),
}

# Columns whose formula differs between the two workbooks, from a full
# column-by-column diff rather than the handful the audit sheets call out.
# ENGINE and ENGINE_STORE share identical column letters A..AE in both files,
# so a formula lifted from one lands on the same fields in the other.
PORT = {
    "ENGINE": ["G", "H", "P"],
    "ENGINE_STORE": [
        "J", "N", "O", "U", "Y", "Z",  # recalculated
        "AA",                          # renamed: At-risk value -> Markdown recoverable
        "AF",                          # new
        "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO",  # new: BASE baseline block
    ],
}

# Workforce holds pasted snapshots where the reference holds live lookups. The
# computed columns (E,F,G,J..P -- including Scheduled/Required/Gap, which are
# f17/f18/f19) are already formulas in both files and are left alone. Only
# these six dimension columns are static, which is why the sheet's store list
# would not follow `Stores` once the dummy rows are replaced with real data.
# Rows 6..165 are the 160 stores; row 166 is a TOTAL row and must not be
# touched.
WORKFORCE = {
    "sheet": "Workforce",
    "blocks": ["A6:D165", "H6:I165"],
    "columns": "A=Store B=Vertical C=Store name D=Cluster H=Event I=Event lift",
}

# The Formulas sheet documents the engine, so leaving it at 19 entries would
# describe an engine this workbook no longer has: AA changed meaning and AF and
# AH:AO did not exist. Rows 6..24 stay exactly as they are (16 shared + the 3
# workforce ones); the reference's 9 additions land after them.
FORMULAS = {
    "sheet": "Formulas",
    "source": "A22:C30",   # the reference's 9 additions
    "dest": "A25:C33",     # appended after our row 24, `Coverage gap`
    "format_from": "A24:C24",
}


def excel_app(win32):
    app = win32.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    app.AskToUpdateLinks = False
    return app


def read_reference(win32, reference: Path) -> dict[str, object]:
    """Everything to be written, read straight out of the reference file."""
    app = excel_app(win32)
    try:
        wb = app.Workbooks.Open(str(reference), ReadOnly=True, UpdateLinks=0)
        try:
            engine: dict[str, dict[str, tuple[str, str]]] = {}
            for sheet, (hrow, drow, _last) in SHEETS.items():
                ws = wb.Worksheets(sheet)
                engine[sheet] = {
                    col: (ws.Range(f"{col}{hrow}").Value, ws.Range(f"{col}{drow}").Formula)
                    for col in PORT[sheet]
                }

            # Whole blocks, verbatim. `.Formula` on a multi-cell range hands
            # back a row-major tuple of tuples, one entry per cell, so each row
            # keeps its own reference instead of inheriting row 6's.
            wf = wb.Worksheets(WORKFORCE["sheet"])
            workforce = {a1: wf.Range(a1).Formula for a1 in WORKFORCE["blocks"]}

            fm = wb.Worksheets(FORMULAS["sheet"])
            formulas = fm.Range(FORMULAS["source"]).Value

            return {"engine": engine, "workforce": workforce, "formulas": formulas}
        finally:
            wb.Close(SaveChanges=False)
    finally:
        app.Quit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help=f"reference workbook to port from (default: {DEFAULT_REFERENCE})",
    )
    args = ap.parse_args()

    try:
        import win32com.client as win32
    except ImportError:
        sys.exit("pywin32 not installed -- this needs real Excel")

    for path in (TARGET, args.reference):
        if not path.exists():
            sys.exit(f"missing: {path}")

    print(f"reference: {args.reference}")
    print("reading reference formulas...")
    ref = read_reference(win32, args.reference)
    engine, workforce, formulas = ref["engine"], ref["workforce"], ref["formulas"]

    print(f"\n{'SHEET':<15}{'COL':<5}{'HEADER':<26}FORMULA")
    print("-" * 100)
    for sheet in SHEETS:
        for col in PORT[sheet]:
            header, formula = engine[sheet][col]
            print(f"{sheet:<15}{col:<5}{str(header)[:24]:<26}{str(formula)[:52]}")

    print("-" * 100)
    print(f"Workforce      {WORKFORCE['columns']}")
    for a1, block in workforce.items():
        print(f"               {a1:<10}{len(block)} rows x {len(block[0])} cols, verbatim")
        print(f"               {'':<10}row 1: {str(block[0][0])[:56]}")
        print(f"               {'':<10}row 2: {str(block[1][0])[:56]}")

    print("-" * 100)
    print(f"Formulas       {FORMULAS['source']} -> {FORMULAS['dest']}  (19 -> 28 metrics)")
    for row in formulas:
        print(f"               + {str(row[0])[:40]}")

    total = sum(len(v) for v in PORT.values())
    print("-" * 100)
    print(f"{total} engine columns, {len(workforce)} Workforce blocks, {len(formulas)} metrics")

    if not args.apply:
        print("\nDry run. Nothing was written. Re-run with --apply.")
        return 0

    # Backup goes outside the repo on purpose: the repo is meant to carry
    # exactly one dataset workbook, and `git HEAD` already holds the
    # pre-revision original, so a second copy beside the file buys nothing.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path(tempfile.gettempdir()) / f"{TARGET.stem}.backup-{stamp}.xlsx"
    shutil.copy2(TARGET, backup)
    print(f"\nbackup: {backup}")

    app = excel_app(win32)
    try:
        wb = app.Workbooks.Open(str(TARGET), UpdateLinks=0)
        try:
            # Manual calculation while writing: 16,000 rows x 16 columns would
            # otherwise trigger a full recalculation on every single assignment.
            app.Calculation = -4135  # xlCalculationManual

            for sheet, (hrow, drow, last) in SHEETS.items():
                ws = wb.Worksheets(sheet)
                for col in PORT[sheet]:
                    header, formula = engine[sheet][col]
                    if header is not None:
                        ws.Range(f"{col}{hrow}").Value = header
                    # Assigning to the whole range lets Excel adjust the row
                    # references per row, exactly like filling down. Safe for
                    # these columns because each addresses its own row (`$A4`,
                    # `VLOOKUP($A4, ...)`) -- verified at rows 4, 5, 24, 100.
                    ws.Range(f"{col}{drow}:{col}{last}").Formula = formula
                    print(f"  {sheet}.{col} <- {str(header)[:30]}")

            ws = wb.Worksheets(WORKFORCE["sheet"])
            for a1, block in workforce.items():
                # Verbatim block write -- see the module docstring for why this
                # cannot be a single fill-down string.
                ws.Range(a1).Formula = block
                print(f"  Workforce.{a1} <- {len(block)} rows verbatim")

            ws = wb.Worksheets(FORMULAS["sheet"])
            ws.Range(FORMULAS["format_from"]).Copy()
            ws.Range(FORMULAS["dest"]).PasteSpecial(-4122)  # xlPasteFormats
            app.CutCopyMode = False
            ws.Range(FORMULAS["dest"]).Value = formulas
            print(f"  Formulas.{FORMULAS['dest']} <- {len(formulas)} metrics")

            print("\nrecalculating (this takes a moment on 16,000 rows)...")
            app.Calculation = -4105  # xlCalculationAutomatic
            app.CalculateFullRebuild()
            wb.Save()
            print("saved.")
        finally:
            wb.Close(SaveChanges=False)
    finally:
        app.Quit()

    print(f"\nIf anything looks wrong: restore {backup}, or `git restore` the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
