# Architecture Principles

Full mechanics live in [AGENTS.md](../../AGENTS.md) and [README.md](../../README.md).
This is the reasoning behind the shape, so changes stay consistent with it instead of
just compiling.

## One deployable, two halves

The repo builds a single Docker image (`Dockerfile`, multi-stage: `node` builds
`frontend/`, `python:3.12-slim` serves it plus the API). There is no service mesh, no
separate frontend deployment, no API gateway. `main.py` serves the React build directly
at `GET /` and 503s if it isn't present. Don't introduce a second deployable (a
standalone frontend host, a split API service) without a reason stronger than "feels
more scalable" — it isn't free here, and nothing in the current load profile asks for it.

## Config-driven agents, one registry list

Every LLM agent is a self-contained folder under `backend/src/llm/agents/<folder>/<name>/`
(config JSON + tools + dashboard + descriptor). `ENABLED_MODULES` in
`src/llm/agents/modules.py` is the **single source of truth** for which agents exist, in
what sidebar order, on both sides of the app — the frontend has no module list of its
own and builds its sidebar from `GET /api/html/agents`.

The principle this encodes: **one edit switches a feature on**, and that edit is
explicit and reviewable (a diff to one list), never implicit (a file existing on disk).
Adding a folder without adding it to `ENABLED_MODULES` must be inert — that's what makes
"build it, don't wire it up yet" a safe intermediate state during a PR. See
[`ai/agent-instructions.md`](../ai/agent-instructions.md) for the full checklist.

## Two different "add a thing" mechanisms, on purpose

The frontend uses the opposite pattern for **static pages** (`frontend/src/pages/`) and
**per-agent UI overrides** (`frontend/src/agents/`): both are auto-discovered via
`import.meta.glob`, no central list, no import line. That's not an inconsistency to
"fix" — it's deliberate:

- Backend agents change what's **enabled and in what order**, cross-cutting concern
  (registry, tool merging, config merging, sidebar order) — so that needs one reviewable
  list.
- Frontend pages/overrides are purely additive and presentational — a folder with the
  right shape just works, and forcing a central import list would only add merge
  conflicts with no corresponding safety benefit.

When you build a new extensibility point, pick the mechanism that matches which of
those two shapes it is. Don't default to auto-discovery just because it's less
boilerplate — the explicit-list backend pattern exists because silent enablement is the
actual failure mode it prevents.

## Backend is not a general query engine

Agent tools query the **latest completed import batch** for their domain and are
scoped to an explicit per-domain table allow-list (`freeform_query.py`). An agent for
Collections cannot read Treasury's tables even via its "freeform SQL" tool. This is a
security boundary (see [`security.md`](security.md)) but also an architectural one: a
new agent domain gets its own allow-list rather than widening an existing one, so one
agent's blast radius stays legible from its own file.

## Compute once, trust the recomputation over stored prose

Action cards derive their before/after figures from the cashflow forecast
(`actions/impact.py`) rather than replaying a sentence an LLM wrote when the action was
seeded. Filters are declared by the backend (`dashboard.filters`) and applied
client-side to an already-delivered payload, rather than round-tripping per filter
change — but the backend still owns *which* dimensions and elements a filter is allowed
to touch, so the frontend can't invent a filter the data doesn't support.

The general rule: **when a figure can be derived from the data, derive it — don't cache
a model's restatement of it and trust the cache.** This applies as much to new dashboard
cards as it did to the original QC fixes that established the pattern.

## The dataset migration is a live architectural constraint, not history

Four of today's agents still read four independently-imported, unrelated batches
(`exisitingdb/` schemas) with no shared entity or period dimension — figures aren't
comparable across them, and filtering is client-side because there's no column to filter
on. The `newdata` star schema (and `retail` for the retail agents) fixes this. New work
should target `newdata`/`retail`, not extend the old per-agent schemas — check
`database-structure.md` and `README_DATASET_V1.0_SCHEMA.md` before adding a table, and
prefer adding to the star schema's dimension/fact shape over inventing a new
domain-local table.
