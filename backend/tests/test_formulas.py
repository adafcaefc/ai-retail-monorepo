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

from src.common.constants import AppPaths
from src.formulas import repository, service
from src.formulas.expression import (
    evaluate_expression,
    parse,
    referenced_names,
)
from src.formulas.models import FormulaCreate, FormulaUpdate, Parameter

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
    """19 formulas x 5 examples, per formula.md's coverage summary."""
    formulas = load_formulas()
    examples = load_examples()

    assert len(formulas) == 19
    assert len(CORPUS) == 95
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
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the repository at a throwaway file so tests never touch dbtemp."""
    path = tmp_path / "formula.json"
    monkeypatch.setattr(AppPaths, "FORMULA_STORE", path)
    return path


def make_payload(**overrides: Any) -> FormulaCreate:
    fields: dict[str, Any] = {
        "name": "Coverage gap",
        "logic": "MAX(0, required - scheduled)",
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


def test_missing_store_file_reads_as_empty(store: Path) -> None:
    assert not store.exists()
    assert service.list_formulas() == []


def test_create_read_update_delete_round_trip(store: Path) -> None:
    created = service.create_formula(make_payload())
    assert created["id"] == "coverage-gap"
    assert created["number"] == 1

    # Survives a reload from disk, not just in-memory state.
    assert service.get_formula("coverage-gap")["name"] == "Coverage gap"
    assert len(service.list_formulas()) == 1

    updated = service.update_formula(
        "coverage-gap",
        FormulaUpdate(
            name="Coverage shortfall",
            logic="MAX(0, required - scheduled)",
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


def test_saved_file_is_readable_json_with_a_version(store: Path) -> None:
    service.create_formula(make_payload())
    payload = json.loads(store.read_text(encoding="utf-8"))
    assert payload["version"] == repository.VERSION
    assert [item["id"] for item in payload["formulas"]] == ["coverage-gap"]


def test_numbers_autoincrement_and_ids_deduplicate(store: Path) -> None:
    first = service.create_formula(make_payload())
    second = service.create_formula(
        make_payload(name="Coverage gap, revised", id="coverage-gap")
    )

    assert (first["number"], second["number"]) == (1, 2)
    assert second["id"] == "coverage-gap-2"


def test_duplicate_name_is_rejected(store: Path) -> None:
    service.create_formula(make_payload())
    with pytest.raises(ValueError, match="already exists"):
        service.create_formula(make_payload(number=9))


def test_duplicate_number_is_rejected(store: Path) -> None:
    service.create_formula(make_payload(number=3))
    with pytest.raises(ValueError, match="already used"):
        service.create_formula(make_payload(name="Another", number=3))


def test_missing_formula_raises_lookup_error(store: Path) -> None:
    for call in (
        lambda: service.get_formula("nope"),
        lambda: service.delete_formula("nope"),
        lambda: service.evaluate_formula("nope", {}),
    ):
        with pytest.raises(LookupError):
            call()


def test_undeclared_parameter_blocks_a_save(store: Path) -> None:
    with pytest.raises(ValueError, match="undeclared"):
        service.create_formula(
            make_payload(expression="required - scheduled + mystery")
        )


def test_excel_expression_blocks_a_save(store: Path) -> None:
    with pytest.raises(ValueError, match="not supported|Excel"):
        service.create_formula(make_payload(expression="=Workforce!M9-Workforce!L9"))


def test_parameter_named_after_a_function_is_rejected(store: Path) -> None:
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


def test_evaluate_uses_supplied_values(store: Path) -> None:
    service.create_formula(make_payload())
    outcome = service.evaluate_formula(
        "coverage-gap", {"required": 50, "scheduled": 20}
    )
    assert outcome["result"] == 30
    assert outcome["result_type"] == "number"


def test_evaluate_falls_back_to_parameter_defaults(store: Path) -> None:
    service.create_formula(make_payload())
    assert service.evaluate_formula("coverage-gap", {})["result"] == 10


def test_evaluate_coerces_numeric_strings_from_form_inputs(store: Path) -> None:
    service.create_formula(make_payload())
    outcome = service.evaluate_formula(
        "coverage-gap", {"required": "1,200", "scheduled": "200"}
    )
    assert outcome["result"] == 1000


def test_evaluate_rejects_non_numeric_input(store: Path) -> None:
    service.create_formula(make_payload())
    with pytest.raises(ValueError, match="needs a number"):
        service.evaluate_formula("coverage-gap", {"required": "many"})


def test_evaluate_returns_whole_numbers_without_a_decimal_tail(store: Path) -> None:
    service.create_formula(make_payload())
    assert service.evaluate_formula("coverage-gap", {})["result"] == 10
    assert isinstance(service.evaluate_formula("coverage-gap", {})["result"], int)
