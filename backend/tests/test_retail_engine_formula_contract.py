"""The formulas a retail board is sent must cover the ones it evaluates.

Every retail What-If engine runs in the browser over `payload["formulas"]`,
and each engine refuses to start unless every id in its own
`REQUIRED_FORMULAS` is present -- deliberately, so a missing rule fails at
load with a name rather than at the first slider drag with a NaN. The two
lists are written on opposite sides of the wire, though, so nothing stopped
them drifting apart: `f02-on-hand` was added to Agent 2's engine when
`atStore` stopped retyping the expression, the backend's `ENGINE_FORMULAS`
was not updated to match, and the live board threw on open while the fixture
build (which ships all twelve) stayed green.

Superset, not equality: a payload may carry a rule the engine does not
evaluate -- a chat tool cites the same tuple as provenance -- but it may never
carry fewer.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "agents" / "retail"

AGENTS = (
    "assortment_optimization",
    "demand_forecasting",
    "inventory_risk",
    "pricing_markdown",
    "promotion_effectiveness",
    "replenishment",
)


def required_formulas(agent: str) -> set[str]:
    """The ids `createEngine` refuses to start without, read from its source.

    Parsed rather than imported: pulling one const out of an ES module from
    pytest would mean a node round trip per agent, and the declaration is a
    flat array of string literals that a regex reads exactly.
    """
    source = (FRONTEND / agent / "data" / "engine.js").read_text(encoding="utf-8")
    match = re.search(
        r"const REQUIRED_FORMULAS = \[(.*?)\];", source, re.DOTALL
    )
    assert match, f"{agent}/data/engine.js has no REQUIRED_FORMULAS array"
    ids = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert ids, f"{agent}'s REQUIRED_FORMULAS is empty"
    return ids


def engine_formulas(agent: str) -> set[str]:
    module = importlib.import_module(f"src.llm.agents.retail.{agent}.dashboard")
    return set(module.ENGINE_FORMULAS)


@pytest.mark.parametrize("agent", AGENTS)
def test_the_payload_carries_every_formula_the_board_evaluates(agent: str) -> None:
    missing = required_formulas(agent) - engine_formulas(agent)
    assert not missing, (
        f"retail.{agent}'s dashboard payload omits {', '.join(sorted(missing))}, "
        f"which frontend/src/agents/retail/{agent}/data/engine.js evaluates. "
        "The board throws on open. Add the id to ENGINE_FORMULAS."
    )
