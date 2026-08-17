"""Move the Expiry branch ahead of Stockout/Low in the workbook's State formulas.

Run it yourself (dry run first -- it writes nothing):

    cd backend
    ../.venv/Scripts/python.exe ../scripts/raise_expiry_priority.py
    ../.venv/Scripts/python.exe ../scripts/raise_expiry_priority.py --apply

Why: `State` is a nested IF that tests Stockout and Low before Expiry. Once
`ROP` was corrected to take its lead time from the designated Trade Agreement
row, ROP rose ~2.3x and every perishable SKU holding more days than its shelf
life also fell below its new ROP -- so all 199 rows that qualify for Expiry
were being reported as Stockout (117) or Low (82) instead, and Expiry read
zero across all 16,000 rows. There is no population that becomes Expiry "for
free": raising it necessarily takes those rows out of Stockout/Low.

`IF(a,"Stockout",IF(b,"Low",IF(c,"Expiry",tail)))` becomes
`IF(c,"Expiry",IF(a,"Stockout",IF(b,"Low",tail)))`. The three branches are
reordered, not rewritten, so the paren structure is identical.

Each formula is transformed **individually, in place**, never filled down.
`State` reaches shelf life through `SKU_Master!$O$6` -- a fully absolute
reference that shifts per SKU block (row 6 -> `$O$6`, row 7 -> `$O$7`, and in
ENGINE_STORE once per 20-store block). Assigning one transformed string to the
whole column would point all 16,000 rows at the first SKU's shelf life. So the
existing block is read, each cell's own formula is rewritten, and the block is
written back.

Every transform is checked by reassembling the branches in their ORIGINAL order
and asserting the result is byte-identical to the formula that was read. If the
parser mis-splits anything the run aborts before writing.

BASE State is transformed too. It has to be: What-If Δ is live minus baseline,
so a baseline still ranking Stockout first would make Δ non-zero at zero
levers, which is exactly the markdown bug this whole exercise started from.
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

# (sheet, block) -- every State-like column, live and baseline.
BLOCKS = [
    ("ENGINE", "J6:J805", "State"),
    ("ENGINE_STORE", "Q4:Q16003", "State"),
    ("ENGINE_STORE", "AL4:AL16003", "BASE State"),
]

# Branch labels in the order the formula currently tests them. The third is the
# one being promoted to first.
ORDER = ('"Stockout"', '"Low"', '"Expiry"')


def split_call(text: str) -> list[str]:
    """Split one function call's arguments at top-level commas.

    `text` must start just past the opening paren. Stops at the paren that
    closes the call. String literals are skipped so a comma inside `"a,b"`
    never splits, and nested calls are skipped by depth.
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False

    for char in text:
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
            elif char == "," and depth == 0:
                parts.append("".join(current))
                current = []
                continue
        current.append(char)

    parts.append("".join(current))
    return parts


def match_paren(text: str, open_index: int) -> int:
    """Index of the paren closing the one at `open_index`."""
    depth = 0
    in_string = False
    for index in range(open_index, len(text)):
        char = text[index]
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
    raise ValueError("unbalanced parentheses")


def find_if_chain(formula: str) -> tuple[str, str, str]:
    """Split a formula into (prefix, if_chain, suffix).

    BASE State wraps its IF chain in `LET(...)`, so the chain neither starts at
    the formula's first character nor ends at its last: the suffix carries
    LET's own closing paren. Dropping it is what the round-trip guard caught on
    the first attempt at this. The chain is the first `IF(` that is followed,
    at its own top level, by a Stockout branch.
    """
    index = formula.find("IF(")
    while index != -1:
        args = split_call(formula[index + 3:])
        if len(args) == 3 and args[1] == ORDER[0]:
            end = match_paren(formula, index + 2)
            return formula[:index], formula[index:end + 1], formula[end + 1:]
        index = formula.find("IF(", index + 1)
    raise ValueError(f"no IF chain testing {ORDER[0]} first was found")


def transform(formula: str) -> str:
    """Promote the Expiry branch to the front of the State chain."""
    prefix, chain, suffix = find_if_chain(formula)

    # Peel the three branches. Each `split_call` returns [cond, value, else].
    outer = split_call(chain[3:])
    middle = split_call(outer[2][3:])
    inner = split_call(middle[2][3:])

    for got, want in zip((outer[1], middle[1], inner[1]), ORDER):
        if got != want:
            raise ValueError(f"expected branch {want}, found {got}")

    def build(*branches: tuple[str, str], tail: str) -> str:
        out = tail
        for cond, value in reversed(branches):
            out = f"IF({cond},{value},{out})"
        return out

    tail = inner[2]

    # Round-trip guard: rebuilding in the ORIGINAL order must reproduce the
    # formula exactly, or the split above cannot be trusted to reorder it.
    rebuilt = prefix + build(
        (outer[0], outer[1]), (middle[0], middle[1]), (inner[0], inner[1]), tail=tail
    ) + suffix
    if rebuilt != formula:
        raise ValueError(f"round-trip mismatch\n  in : {formula}\n  out: {rebuilt}")

    return prefix + build(
        (inner[0], inner[1]), (outer[0], outer[1]), (middle[0], middle[1]), tail=tail
    ) + suffix


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    try:
        import win32com.client as win32
    except ImportError:
        sys.exit("pywin32 not installed -- this needs real Excel")

    if not TARGET.exists():
        sys.exit(f"missing: {TARGET}")

    app = win32.Dispatch("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    app.AskToUpdateLinks = False

    try:
        wb = app.Workbooks.Open(str(TARGET), ReadOnly=not args.apply, UpdateLinks=0)
        try:
            planned: list[tuple[str, str, tuple]] = []

            for sheet, block, label in BLOCKS:
                ws = wb.Worksheets(sheet)
                rows = ws.Range(block).Formula
                out = []
                changed = 0
                for row in rows:
                    formula = row[0]
                    if isinstance(formula, str) and ORDER[2] in formula:
                        try:
                            new = transform(formula)
                        except ValueError as exc:
                            sys.exit(f"{sheet}!{block}: {exc}")
                        out.append((new,))
                        changed += 1
                    else:
                        out.append((formula,))
                planned.append((sheet, block, tuple(out)))
                print(f"{sheet}!{block:<14} {label:<12} {changed}/{len(rows)} formulas")
                print(f"   before: {str(rows[0][0])[:96]}")
                print(f"   after : {str(out[0][0])[:96]}")
                print()

            if not args.apply:
                print("Dry run. Nothing was written. Re-run with --apply.")
                return 0

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = Path(tempfile.gettempdir()) / f"{TARGET.stem}.backup-{stamp}.xlsx"
            shutil.copy2(TARGET, backup)
            print(f"backup: {backup}\n")

            app.Calculation = -4135  # xlCalculationManual
            for sheet, block, values in planned:
                wb.Worksheets(sheet).Range(block).Formula = values
                print(f"  wrote {sheet}!{block}")

            print("\nrecalculating...")
            app.Calculation = -4105  # xlCalculationAutomatic
            app.CalculateFullRebuild()
            wb.Save()
            print("saved.")
            print(f"\nIf anything looks wrong: restore {backup}, or `git restore` the file.")
        finally:
            wb.Close(SaveChanges=False)
    finally:
        app.Quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
