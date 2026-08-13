# Python Style — Backend

Applies to everything under `backend/`. Python 3.12, FastAPI, SQLAlchemy 2.0,
pydantic-ai. Run all backend commands from `backend/` — imports are rooted there
(`from src...`).

## No formatter/linter is configured yet — match surrounding style exactly

There is currently no `pyproject.toml`, `ruff.toml`, `.flake8`, or `mypy.ini` in this
repo. That's a gap worth closing (a `ruff` config covering lint + format would fit this
codebase's style with minimal friction), but until one is added and committed, **don't
invent your own formatting rules** — open a file in the same area you're editing and
match its indentation, quote style, and import grouping exactly, so a future
auto-formatter pass doesn't produce a diff full of unrelated churn. The conventions
below describe what the existing code already does consistently.

## Conventions already in force

- **`from __future__ import annotations`** as the first import in every module that uses
  type hints (which is nearly all of them). Keep doing this even though 3.12 doesn't
  strictly require it — it's consistent across the codebase and cheap to keep that way.
- **Full type hints** on function signatures, including internal helpers — see
  `common/tools/db.py`'s `_row`, `_rows`, `_json_value`. Return types are annotated even
  on private `_`-prefixed functions.
- **SQLAlchemy Core, not the ORM**, for agent tool queries — `text()` with bound
  parameters, `.mappings()` for dict-shaped rows. This repo doesn't use declarative ORM
  models for the read-heavy agent-tool query layer; don't introduce one for a new tool
  without a specific reason the Core style doesn't cover.
- **Pydantic models for all agent I/O** — `input_model`/`output_model` per chivon agent
  config, built dynamically from JSON. Application code outside the agent layer uses
  plain dataclasses (`AgentDescriptor`, `MonitoringPass` in `descriptor.py`) where
  runtime validation isn't the point.
- **Docstrings only where the *why* isn't obvious from the code** — this mirrors the
  repo-wide comment policy in `CLAUDE.md`. `db.py`'s `_legal_entities` is the model to
  follow: the docstring explains *why* it's read live instead of hardcoded ("a fourth
  entity added to the dataset later should not need a matching code change"), not *what*
  the function does. A one-line "Get the legal entities" docstring on top of an
  obviously-named function is noise; delete it rather than write it.
- **No `eval()`/`exec()`**, ever, including for "trusted" internal input — see
  [`../principles/security.md`](../principles/security.md) for the expression-parser
  pattern to use instead when you need to evaluate something dynamic.
- **Exact-pinned dependencies** in `requirements.txt`, each with a comment explaining
  *why it's there* when that's not obvious from the package name alone (see how
  `httpx`, `sqlglot`, and `mssql-python` are annotated). When you add a dependency,
  pin the exact version and add that comment — a bare `some-package>=1.0` with no
  explanation is what to avoid.

## Errors and validation

Validate at system boundaries — FastAPI/Pydantic request models, chivon's dynamically
built `input_model` — and let internal code trust that shape once past the boundary.
Don't add defensive `isinstance`/`None` checks deeper in the call stack for conditions
the boundary already rules out; it hides the actual contract and adds dead branches
nothing exercises. See [`../principles/security.md`](../principles/security.md) for how
this interacts with the 422-at-the-boundary convention.

## Comments

Match the top-level repo policy (`CLAUDE.md`): default to no comments. Add one only when
it captures something the code can't: a non-obvious constraint, a workaround for a
specific external bug, or (as above) a rationale a reader would otherwise have to
reconstruct. Don't restate the signature in prose above the function.

## Tests

`backend/tests/test_<subject>.py`, `pytest`, fixture-based by default (no live DB). See
[`../principles/testing.md`](../principles/testing.md) for the integration-marker
pattern and the two-verifier convention for anything that needs to check against real
data.
