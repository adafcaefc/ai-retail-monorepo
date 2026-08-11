"""Rebuild the worked-example corpus from `resources/formula.md`.

The verification pack is the source of truth: 19 formulas x 5 examples, each
recording the workbook cell holding the result *and* a table of the source
cells every input was read from. The UI's copy of that corpus lives in
`frontend/src/pages/main/formula_manager/workedExamples.json`, which used to
carry only the result cell -- the per-input source cells stayed locked in the
prose, so nothing in the app could say where `base_ads = 20.9096` came from.

This module is the single parser for the pack. It generates the JSON rather
than anyone hand-editing it, and `test_worked_example_cells.py` imports the
same functions to assert the two have not drifted apart.

    cd backend
    python -m src.formulas.verification_pack            # check, exit 1 on drift
    python -m src.formulas.verification_pack --write    # regenerate the JSON

Mapping inputs to cells is positional: the Nth row of an example's source-cell
table is the Nth declared parameter of the formula. The pack writes them in
that order throughout, and a table may carry *extra* trailing rows for workbook
intermediates that are not parameters at all (Formula 12 cites the at-risk
value it multiplies out), so surplus rows are dropped rather than matched. A
misalignment cannot pass unnoticed: `test_formulas.py` replays all 95 examples
through the stored expressions, and shuffled inputs do not reproduce the
workbook's answer.
"""

from __future__ import annotations

import json
import re
import sys

from pathlib import Path
from typing import Any

from src.common.constants import AppPaths

PACK_PATH = AppPaths.REPO_ROOT / "resources" / "formula.md"

EXAMPLES_PATH = (
    AppPaths.REPO_ROOT
    / "frontend"
    / "src"
    / "pages"
    / "main"
    / "formula_manager"
    / "workedExamples.json"
)

_FORMULA_HEADING = re.compile(r"^## Formula (\d+): (.+)$", re.MULTILINE)

_EXAMPLE_HEADING = re.compile(r"^### Example (\d+): (.+)$", re.MULTILINE)

_RESULT = re.compile(r"\*\*Result:\*\* `([^`]+)` = \*\*(.+?)\*\*")

# | Source sheet | Cell | Saved value | Role |
_SOURCE_ROW = re.compile(
    r"^\| `([^`]+)` \| `([^`]+)` \| (.*?) \| (.*?) \|$",
    re.MULTILINE,
)


def _value(text: str) -> Any:
    """A saved workbook value as the pack prints it.

    Thousands separators are display, not data: the pack writes `18,900` where
    the corpus needs 18900. Anything that is not a number stays a string --
    `Y`, `N`, `Stockout`.
    """
    cleaned = text.strip().replace(",", "")

    try:
        number = float(cleaned)
    except ValueError:
        return text.strip()

    # Keep integers as integers so the generated JSON reads like the workbook
    # (`demand_lever: 0`, not `0.0`).
    if "." not in cleaned and "e" not in cleaned.lower():
        return int(number)

    return number


def parse_pack(
    markdown: str,
    formulas: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """The pack's 95 examples, keyed by formula id.

    `formulas` supplies the parameter order the source-cell tables are read
    against -- the pack names cells, the store names parameters, and neither
    knows about the other.
    """
    by_number = {formula["number"]: formula for formula in formulas}
    corpus: dict[str, list[dict[str, Any]]] = {}

    sections = _FORMULA_HEADING.split(markdown)

    # split() yields [preamble, number, name, body, number, name, body, ...].
    for index in range(1, len(sections), 3):
        number = int(sections[index])
        body = sections[index + 2]

        formula = by_number.get(number)
        if formula is None:
            raise ValueError(
                f"formula.md documents formula {number}, "
                "which the store does not define"
            )

        corpus[formula["id"]] = _parse_examples(formula, body)

    missing = [
        formula["id"] for formula in formulas if formula["id"] not in corpus
    ]
    if missing:
        raise ValueError(f"formula.md documents no examples for {missing}")

    return corpus


def _parse_examples(
    formula: dict[str, Any],
    body: str,
) -> list[dict[str, Any]]:
    keys = [parameter["key"] for parameter in formula["parameters"]]
    examples: list[dict[str, Any]] = []

    sections = _EXAMPLE_HEADING.split(body)

    for index in range(1, len(sections), 3):
        ordinal = sections[index]
        heading = sections[index + 1]
        example = sections[index + 2]
        where = f"{formula['id']} example {ordinal}"

        result = _RESULT.search(example)
        if result is None:
            raise ValueError(f"{where} states no result cell")

        rows = _SOURCE_ROW.findall(example)
        if len(rows) < len(keys):
            raise ValueError(
                f"{where} cites {len(rows)} source cells for "
                f"{len(keys)} parameters"
            )

        values: dict[str, Any] = {}
        sources: dict[str, str] = {}

        for key, (sheet, cell, saved, _role) in zip(keys, rows):
            values[key] = _value(saved)
            sources[key] = f"{sheet}!{cell}"

        examples.append(
            {
                # Backticks are markdown emphasis around the SKU and store
                # codes, not part of the label.
                "label": heading.replace("`", "").strip(),
                "address": result.group(1),
                "expected": _value(result.group(2)),
                "values": values,
                "sources": sources,
            }
        )

    return examples


def build() -> dict[str, list[dict[str, Any]]]:
    """Parse the pack on disk against the stored formulas."""
    from src.formulas import repository

    return parse_pack(
        PACK_PATH.read_text(encoding="utf-8"),
        repository.load(),
    )


def render(corpus: dict[str, list[dict[str, Any]]]) -> str:
    return json.dumps(corpus, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    corpus = build()
    generated = render(corpus)
    current = (
        Path(EXAMPLES_PATH).read_text(encoding="utf-8")
        if EXAMPLES_PATH.exists()
        else ""
    )

    if "--write" in argv:
        EXAMPLES_PATH.write_text(generated, encoding="utf-8", newline="\n")
        total = sum(len(cases) for cases in corpus.values())
        state = "unchanged" if generated == current else "rewritten"
        print(
            f"{EXAMPLES_PATH.name} {state}: "
            f"{len(corpus)} formulas, {total} examples"
        )
        return 0

    if generated == current:
        print(f"{EXAMPLES_PATH.name} matches {PACK_PATH.name}")
        return 0

    print(
        f"{EXAMPLES_PATH.name} is out of date with {PACK_PATH.name}. "
        "Run with --write."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
