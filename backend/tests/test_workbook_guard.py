"""The seeders refuse an extract taken from a workbook the repo has not pinned.

WHY THIS TEST EXISTS
On 2026-08-19 the retail fact tables were rewritten six or seven times across
one day, alternating between two workbooks that share a file name. Chain-net
ROP for DGT-001 read 5813, then 7474, then 5813 again. No run was a mistake:
each copied the extract sitting in its own checkout, and the basis in Azure
belonged to whoever seeded last.

So the case that matters here is not the happy one. It is that a stale extract
STOPS the seeder, and that an extract predating the guard stops it too --
silence on the unknown case is what the whole guard exists to remove.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXTRACT = REPO / "resources" / "dbtemp" / "schema_with_data.json"


def _load_guard():
    """Import by path — `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "workbook_guard", REPO / "scripts" / "workbook_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["workbook_guard"] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


@pytest.fixture(scope="module")
def header() -> dict:
    """The checked-in extract's header, without its 5.9 MB of rows."""
    payload = json.loads(EXTRACT.read_text(encoding="utf-8"))
    return {key: value for key, value in payload.items() if key != "tables"}


def test_the_checked_in_extract_is_the_pinned_workbook(header: dict) -> None:
    """The pin and the extract beside it must agree, or every seed is blocked.

    This is the one that fails when someone updates the workbook and forgets
    the pin, or moves the pin without re-extracting. Either way the two have
    come apart, and a seeder in this checkout would refuse to run.
    """
    assert guard.verify(header) == guard.EXPECTED_WORKBOOK_SHA256
    assert header["source_workbook"] == guard.EXPECTED_WORKBOOK_NAME


def test_an_extract_from_another_workbook_is_refused(header: dict) -> None:
    """The failure the guard was built for, and the message it owes the reader.

    A run blocked without both hashes on screen leaves the reader guessing
    which checkout they are in, which is the position everyone was in on the
    day this happened.
    """
    other = dict(header, source_workbook_sha256="f" * 64)

    with pytest.raises(guard.WorkbookMismatch) as caught:
        guard.verify(other)

    message = str(caught.value)
    assert guard.EXPECTED_WORKBOOK_SHA256 in message
    assert "f" * 64 in message
    assert guard.FLAG in message


def test_an_extract_predating_the_guard_is_refused(header: dict) -> None:
    """No recorded hash means the workbook behind it is unknown, not fine.

    Passing it would reintroduce exactly the silence being removed: a seed
    whose source nothing can name.
    """
    older = {k: v for k, v in header.items() if k != guard.HASH_FIELD}

    with pytest.raises(guard.WorkbookMismatch) as caught:
        guard.verify(older)

    assert "extract_workbook_schema.py" in str(caught.value)


@pytest.mark.parametrize("field", ["f" * 64, None])
def test_the_override_lets_a_deliberate_change_through(
    header: dict, field: str | None
) -> None:
    """`--allow-workbook-change` is the seam for the run that replaces the pin.

    It returns what it found rather than what was expected, so the caller can
    record the actual workbook in the audit row instead of the one the repo
    still names.
    """
    payload = dict(header)
    if field is None:
        payload.pop(guard.HASH_FIELD)
    else:
        payload[guard.HASH_FIELD] = field

    assert guard.verify(payload, allow_change=True) == (field or "")


def test_the_flag_is_read_from_the_command_line() -> None:
    """The seeders take no options otherwise, so this is the whole interface."""
    assert guard.overridden(["seed.py", guard.FLAG]) is True
    assert guard.overridden(["seed.py"]) is False
