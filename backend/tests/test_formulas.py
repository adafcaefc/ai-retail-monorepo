"""Formula Manager: expression engine, the worked-example corpus, and CRUD.

The corpus test is the important one. `resources/formula.md` is a verification
pack -- 19 formulas x 5 workbook-traceable examples -- and the stored
Excel-free expressions are a hand derivation of the native Excel originals.
Replaying all 95 examples is what proves the derivation is faithful.
"""

from __future__ import annotations

import json
import math

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.common.constants import AppPaths
from src.formulas import repository, service
from src.formulas.expression import (
    evaluate_expression,
    parse,
    referenced_names,
)
from src.formulas.models import (
    GRAIN_LABELS,
    FormulaCreate,
    FormulaUpdate,
    Parameter,
)

REPO_ROOT = AppPaths.REPO_ROOT
WORKED_EXAMPLES = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "pages"
    / "main"
    / "formula_manager"
    / "workedExamples.json"
)


def load_formulas() -> list[dict[str, Any]]:
    payload = json.loads(
        Path(AppPaths.FORMULA_STORE).read_text(encoding="utf-8")
    )
    return payload["formulas"]


def load_examples() -> dict[str, list[dict[str, Any]]]:
    return json.loads(WORKED_EXAMPLES.read_text(encoding="utf-8"))


def corpus() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    examples = load_examples()
    return [
        (formula, case)
        for formula in load_formulas()
        for case in examples[formula["id"]]
    ]


CORPUS = corpus()


# -- the worked-example corpus ----------------------------------------


def test_corpus_covers_every_documented_example() -> None:
    """23 formulas x 5 examples, per formula.md's coverage summary.

    Nineteen of these transcribe the workbook's `Formulas` sheet. Twenty to
    twenty-two are ENGINE columns I, L and N -- real workbook formulas the
    sheet simply does not list, added when the Inventory Risk What-If panel
    needed to recompute them and found no catalogue entry to run.

    Twenty-three is `f23-markdown-at-risk-gross`. It is not new arithmetic:
    f14 used to hold that expression under the name "Recoverable at-risk
    value" while the workbook's AA column had already moved on to the net
    figure. Splitting them gave the gross one a home and let f14 hold what
    its name claims -- which is also what gave the markdown lever a term to
    move.
    """
    formulas = load_formulas()
    examples = load_examples()

    assert len(formulas) == 23
    assert len(CORPUS) == 115
    assert all(len(examples[formula["id"]]) == 5 for formula in formulas)


@pytest.mark.parametrize(
    ("formula", "case"),
    CORPUS,
    ids=[f"{formula['id']}:{case['address']}" for formula, case in CORPUS],
)
def test_worked_example_reproduces_workbook_result(
    formula: dict[str, Any],
    case: dict[str, Any],
) -> None:
    result = evaluate_expression(formula["expression"], case["values"])
    expected = case["expected"]

    if formula["result_type"] == "text":
        assert result == expected
        return

    # formula.md warns the workbook cache stores more precision than the
    # displayed value, so compare relatively rather than exactly.
    assert math.isclose(
        float(result), float(expected), rel_tol=1e-6, abs_tol=1e-9
    ), f"{case['address']}: got {result}, workbook says {expected}"


def test_every_stored_formula_declares_exactly_what_it_uses() -> None:
    for formula in load_formulas():
        declared = {item["key"] for item in formula["parameters"]}
        used = referenced_names(parse(formula["expression"]))
        assert used <= declared, f"{formula['id']} reads undeclared {used - declared}"
        assert declared <= used, f"{formula['id']} declares unused {declared - used}"


def test_stored_expressions_are_excel_free() -> None:
    for formula in load_formulas():
        expression = formula["expression"]
        assert not expression.startswith("=")
        for character in ("!", "$", ";", "^"):
            assert character not in expression, f"{formula['id']} contains {character}"


# -- expression engine -------------------------------------------------


def test_operator_precedence_and_parentheses() -> None:
    assert evaluate_expression("2 + 3 * 4", {}) == 14
    assert evaluate_expression("(2 + 3) * 4", {}) == 20
    assert evaluate_expression("10 / 4", {}) == 2.5
    assert evaluate_expression("-3 + 5", {}) == 2


def test_named_parameters_are_read_from_values() -> None:
    assert evaluate_expression("a * b + c", {"a": 2, "b": 3, "c": 4}) == 10


def test_allow_listed_functions() -> None:
    assert evaluate_expression("MAX(1, 7, 3)", {}) == 7
    assert evaluate_expression("MIN(1, 7, 3)", {}) == 1
    assert evaluate_expression("CEILING(11.3, 1)", {}) == 12
    assert evaluate_expression("NOT(1 > 2)", {}) is True
    assert evaluate_expression("AND(1 > 0, 2 > 1)", {}) is True
    assert evaluate_expression("OR(1 > 2, 2 > 1)", {}) is True
    assert evaluate_expression("IF(1 > 2, 10, 20)", {}) == 20


def test_round_uses_excel_half_away_from_zero() -> None:
    # Python's round() would give 2 and 4 here (banker's rounding).
    assert evaluate_expression("ROUND(2.5)", {}) == 3
    assert evaluate_expression("ROUND(3.5)", {}) == 4
    assert evaluate_expression("ROUND(-2.5)", {}) == -3
    assert evaluate_expression("ROUND(1.2345, 2)", {}) == 1.23


def test_if_does_not_evaluate_the_untaken_branch() -> None:
    # The false branch divides by zero; short-circuiting is what keeps guards
    # like IF(qty > 0, total / qty, 0) usable.
    assert evaluate_expression("IF(1 > 0, 5, 1 / 0)", {}) == 5


def test_text_comparison_is_case_insensitive() -> None:
    assert evaluate_expression('state = "healthy"', {"state": "Healthy"}) is True
    assert evaluate_expression('state <> "Healthy"', {"state": "Low"}) is True


@pytest.mark.parametrize(
    "expression",
    [
        "=SUM(A1:A5)",
        "ENGINE_STORE!J4 * 2",
        "SKU_Master!$G$6 * 2",
        "a ^ 2",
        "a & b",
        "MAX(1; 2)",
        "SUM(1, 2)",
        "(1 + 2",
        "1 + ",
        "* 3",
        "",
    ],
)
def test_rejects_excel_syntax_and_malformed_input(expression: str) -> None:
    with pytest.raises(ValueError):
        parse(expression)


def test_unknown_function_names_the_allow_list() -> None:
    with pytest.raises(ValueError, match="Allowed functions"):
        parse("SUM(1, 2)")


def test_missing_parameter_value_is_reported() -> None:
    with pytest.raises(ValueError, match="on_hand"):
        evaluate_expression("on_hand + 1", {})


def test_division_by_zero_is_reported() -> None:
    with pytest.raises(ValueError, match="Division by zero"):
        evaluate_expression("1 / zero", {"zero": 0})


# -- CRUD ---------------------------------------------------------------


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """An in-memory stand-in for `retail.formula`.

    These tests are about `service.py` -- slug derivation, uniqueness,
    expression validation, default fallback -- none of which is about storage.
    They used to point `AppPaths.FORMULA_STORE` at a tmp file; now that the
    repository is Postgres, the equivalent move is to fake the two functions
    the service actually calls rather than to make every one of them require a
    reachable database. A unit suite that needs the network is a unit suite
    people stop running.

    The real round trip is covered by `test_formula_repository_round_trip`
    below, which does talk to Postgres and skips when it cannot.
    """
    rows: list[dict[str, Any]] = []

    def fake_load() -> list[dict[str, Any]]:
        return [dict(row) for row in sorted(rows, key=lambda r: r.get("number", 0))]

    def fake_save(formulas: list[dict[str, Any]]) -> None:
        rows[:] = [dict(formula) for formula in formulas]

    monkeypatch.setattr(repository, "load", fake_load)
    monkeypatch.setattr(repository, "save", fake_save)
    return rows


def make_payload(**overrides: Any) -> FormulaCreate:
    fields: dict[str, Any] = {
        "name": "Coverage gap",
        "logic": "MAX(0, required - scheduled)",
        # Required, no default: a rule whose grain nobody stated is one an
        # agent cannot safely feed. See `models.Grain`.
        "grain": "store_roster",
        "sheet": "Workforce",
        "result_type": "number",
        "expression": "MAX(0, required - scheduled)",
        "parameters": [
            Parameter(key="required", label="Required", type="number", default=42),
            Parameter(key="scheduled", label="Scheduled", type="number", default=32),
        ],
    }
    fields.update(overrides)
    return FormulaCreate(**fields)


def test_empty_store_reads_as_empty(store: list[dict[str, Any]]) -> None:
    assert store == []
    assert service.list_formulas() == []


def test_grain_is_required_and_constrained() -> None:
    """The field the whole catalogue's safety rests on cannot be defaulted.

    `grain` decides which table a rule may be fed from. Sixteen of the
    twenty-two rules are store_sku, so a default would be right often enough
    to stop anyone checking -- and wrong exactly on the chain-net rules where
    it matters.
    """
    with pytest.raises(ValidationError):
        FormulaCreate(
            name="No grain",
            expression="a + 1",
            parameters=[Parameter(key="a", label="A")],
        )

    with pytest.raises(ValidationError):
        # A plausible wrong value: the old sheet name, which is what someone
        # would reach for if grain were still inferred from `sheet`.
        make_payload(grain="ENGINE_STORE")


def test_create_read_update_delete_round_trip(store: list[dict[str, Any]]) -> None:
    created = service.create_formula(make_payload())
    assert created["id"] == "coverage-gap"
    assert created["number"] == 1

    # Survives a reload from the store, not just in-memory state.
    assert service.get_formula("coverage-gap")["name"] == "Coverage gap"
    assert len(service.list_formulas()) == 1

    updated = service.update_formula(
        "coverage-gap",
        FormulaUpdate(
            name="Coverage shortfall",
            logic="MAX(0, required - scheduled)",
            grain="store_roster",
            sheet="Workforce",
            result_type="number",
            expression="MAX(0, required - scheduled) * 1",
            parameters=[
                Parameter(key="required", label="Required"),
                Parameter(key="scheduled", label="Scheduled"),
            ],
        ),
    )
    assert updated["name"] == "Coverage shortfall"
    assert service.get_formula("coverage-gap")["name"] == "Coverage shortfall"

    service.delete_formula("coverage-gap")
    assert service.list_formulas() == []


def test_saved_record_carries_grain(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    assert [item["id"] for item in store] == ["coverage-gap"]
    assert store[0]["grain"] == "store_roster"
    # Provenance survives too, but nothing reads it.
    assert store[0]["sheet"] == "Workforce"


def test_numbers_autoincrement_and_ids_deduplicate(store: list[dict[str, Any]]) -> None:
    first = service.create_formula(make_payload())
    second = service.create_formula(
        make_payload(name="Coverage gap, revised", id="coverage-gap")
    )

    assert (first["number"], second["number"]) == (1, 2)
    assert second["id"] == "coverage-gap-2"


def test_duplicate_name_is_rejected(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    with pytest.raises(ValueError, match="already exists"):
        service.create_formula(make_payload(number=9))


def test_duplicate_number_is_rejected(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload(number=3))
    with pytest.raises(ValueError, match="already used"):
        service.create_formula(make_payload(name="Another", number=3))


def test_missing_formula_raises_lookup_error(store: list[dict[str, Any]]) -> None:
    for call in (
        lambda: service.get_formula("nope"),
        lambda: service.delete_formula("nope"),
        lambda: service.evaluate_formula("nope", {}),
    ):
        with pytest.raises(LookupError):
            call()


def test_undeclared_parameter_blocks_a_save(store: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="undeclared"):
        service.create_formula(
            make_payload(expression="required - scheduled + mystery")
        )


def test_excel_expression_blocks_a_save(store: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="not supported|Excel"):
        service.create_formula(make_payload(expression="=Workforce!M9-Workforce!L9"))


def test_parameter_named_after_a_function_is_rejected(store: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match="clashes"):
        service.create_formula(
            make_payload(
                expression="max + 1",
                parameters=[Parameter(key="max", label="Max")],
            )
        )


# -- validate / evaluate -----------------------------------------------


def test_validate_reports_undeclared_and_unused() -> None:
    report = service.validate(
        "a + b",
        [Parameter(key="a", label="A"), Parameter(key="c", label="C")],
    )
    assert report["valid"] is False
    assert report["undeclared"] == ["b"]
    assert report["unused"] == ["c"]
    assert report["referenced"] == ["a", "b"]


def test_validate_accepts_a_matching_expression() -> None:
    report = service.validate(
        "MAX(0, a - b)",
        [Parameter(key="a", label="A"), Parameter(key="b", label="B")],
    )
    assert report["valid"] is True
    assert report["errors"] == []


def test_unused_parameter_is_reported_but_still_valid() -> None:
    # Reported, not rejected: a normal intermediate state while editing.
    report = service.validate(
        "a + 1",
        [Parameter(key="a", label="A"), Parameter(key="spare", label="Spare")],
    )
    assert report["valid"] is True
    assert report["unused"] == ["spare"]


def test_evaluate_uses_supplied_values(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    outcome = service.evaluate_formula(
        "coverage-gap", {"required": 50, "scheduled": 20}
    )
    assert outcome["result"] == 30
    assert outcome["result_type"] == "number"


def test_evaluate_falls_back_to_parameter_defaults(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    assert service.evaluate_formula("coverage-gap", {})["result"] == 10


def test_evaluate_coerces_numeric_strings_from_form_inputs(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    outcome = service.evaluate_formula(
        "coverage-gap", {"required": "1,200", "scheduled": "200"}
    )
    assert outcome["result"] == 1000


def test_evaluate_rejects_non_numeric_input(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    with pytest.raises(ValueError, match="needs a number"):
        service.evaluate_formula("coverage-gap", {"required": "many"})


def test_evaluate_returns_whole_numbers_without_a_decimal_tail(store: list[dict[str, Any]]) -> None:
    service.create_formula(make_payload())
    assert service.evaluate_formula("coverage-gap", {})["result"] == 10
    assert isinstance(service.evaluate_formula("coverage-gap", {})["result"], int)


# -- the live table -----------------------------------------------------
#
# Everything above fakes the repository, because it is testing service logic.
# These two talk to Postgres, and skip rather than fail when it is not
# reachable -- an offline checkout should still be able to run the suite.


def _catalogue_or_skip() -> list[dict[str, Any]]:
    try:
        rows = repository.load()
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"retail.formula is not reachable: {error}")
    if not rows:
        pytest.skip(
            "retail.formula is empty; seed it with "
            "scripts/import_formulas_to_db.py"
        )
    return rows


def test_formula_table_matches_the_workbook_transcript() -> None:
    """The imported table equals `formula.json` field for field.

    This is what makes the migration auditable. `formula.json` stays in the
    tree as the transcript `test_formula_conformance.py` checks against the
    workbook; the table is what runs. If the two drift, the conformance suite
    is answering a question about a file nobody evaluates any more.

    `grain` is excluded because the file has no such field -- it is derived
    once, on import, and asserted separately below.
    """
    stored = {row["id"]: row for row in _catalogue_or_skip()}
    transcript = {row["id"]: row for row in load_formulas()}

    assert set(stored) == set(transcript)

    for formula_id, expected in transcript.items():
        actual = stored[formula_id]
        for field in ("number", "name", "expression", "result_type"):
            assert actual[field] == expected[field], (
                f"{formula_id}.{field}: table has {actual[field]!r}, "
                f"transcript has {expected[field]!r}"
            )
        assert actual["parameters"] == expected["parameters"], (
            f"{formula_id}: parameters differ between table and transcript"
        )


def test_every_stored_formula_carries_a_usable_grain() -> None:
    """No rule reaches an agent ungrained, and the split is the known one.

    Grain decides which table a rule may be fed from, and feeding the wrong
    one returns a plausible number rather than an error -- so an ungrained
    rule is the failure this column exists to prevent, not a cosmetic gap.
    """
    rows = _catalogue_or_skip()
    split: dict[str, int] = {}
    for row in rows:
        grain = row.get("grain")
        assert grain in GRAIN_LABELS, f"{row['id']} has unusable grain {grain!r}"
        split[grain] = split.get(grain, 0) + 1

    # 17, not 16: f23-markdown-at-risk-gross is a store-grain formula.
    assert split == {"store_sku": 17, "chain_sku": 3, "store_roster": 3}
