# Engineering Standards — AI Retail Monorepo

This directory is the house style for this repo: **Ledgerline Finance Forum / AI 360
Retail Suite** — a FastAPI + pydantic-ai backend and a React + Vite frontend that serve
config-driven LLM agents over PostgreSQL financial and retail data.

It documents conventions this codebase already follows (so they survive contributor
turnover) and flags the few places we've deliberately left a gap rather than invent
process the repo doesn't need. Where a document describes "current state" instead of a
firm rule, that's intentional — don't cite it as a requirement that isn't enforced
anywhere.

**This is not a replacement for [AGENTS.md](../AGENTS.md) or [README.md](../README.md).**
Those two are the living architecture reference — registry mechanics, API contracts,
schema tables, key file index — and they change as the code changes. This directory is
the *why* and the *checklist*: principles a reviewer checks a PR against, and templates
that save you from re-deriving the folder shape every time. When the two disagree,
AGENTS.md/README.md are authoritative — file an update here.

## Layout

| Path | Purpose |
|---|---|
| [`principles/architecture.md`](principles/architecture.md) | The shape of the monorepo and why it's built config-driven / registry-first |
| [`principles/security.md`](principles/security.md) | Secrets, SQL safety, the allow-list pattern, no-`eval` rule |
| [`principles/testing.md`](principles/testing.md) | Test tiers, fixture-vs-integration split, the two-verifier pattern |
| [`principles/api-design.md`](principles/api-design.md) | REST/SSE conventions, status-code meaning, pagination |
| [`languages/python.md`](languages/python.md) | Backend code style (Python 3.12, FastAPI, SQLAlchemy, pydantic-ai) |
| [`languages/javascript-typescript.md`](languages/javascript-typescript.md) | Frontend code style (React 19, Vite, plain JS) |
| [`ai/agent-instructions.md`](ai/agent-instructions.md) | Rules for building/editing a chivon agent: prompts, tools, output schema |
| [`ai/definition-of-done.md`](ai/definition-of-done.md) | Checklist for "is this agent/feature change actually done" |
| [`ai/prompt-templates.md`](ai/prompt-templates.md) | Skeletons for chat/monitoring/simulation system prompts |
| [`templates/python-service/`](templates/python-service/) | Copy-paste skeleton for a new backend agent folder |
| [`templates/javascript-service/`](templates/javascript-service/) | Copy-paste skeleton for a new frontend page or agent UI override |
| [`pull-requests/pull-request-template.md`](pull-requests/pull-request-template.md) | PR description template |

## How to use this with an AI coding agent

Point Claude Code (or any other agent) at this directory the same way you'd point a
new hire at it: "read `engineering-standards/README.md` and the docs it links before
touching `backend/src/llm/agents/`." The `ai/` folder in particular exists because this
repo's own product *is* LLM agents — the standards for building an agent inside this
codebase and the standards for using an AI coding assistant on this codebase turned out
to share almost all their content (tool-before-answer, schema conformance, no invented
data), so `ai/agent-instructions.md` covers both.

## Keeping this current

These documents describe patterns as of 2026-08-13. When you introduce a new pattern
deliberately (a new allow-listed table, a new component format, a new test tier), update
the relevant file in the same PR — don't let this drift into aspirational documentation
nobody follows. If you find a rule here that the code no longer does, fix the doc or fix
the code; don't leave both standing.
