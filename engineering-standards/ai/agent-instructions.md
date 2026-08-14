# Building and Editing Chivon Agents

This repo's product *is* LLM agents, so this document doubles as instructions for a
human and for an AI coding assistant working in `backend/src/llm/agents/`. Read
[AGENTS.md](../../AGENTS.md) first for full mechanics — this is the ruleset a change
should be checked against, not a restatement of how the registry works.

## An agent is one folder plus one line — keep it that way

To add `finance.<name>` or `retail.<name>`:

1. `config/<folder>_<name>_chat.json` (+ `_monitoring.json` if the agent has
   monitoring/simulation/action passes) — see
   [`prompt-templates.md`](prompt-templates.md) for the system-prompt skeleton.
2. `tools/<name>_data.py` exposing a `TOOLS` dict; `tools/__init__.py` re-exporting it.
3. `dashboard.py` exposing `build()`.
4. `__init__.py` exposing `DESCRIPTOR = AgentDescriptor(...)`.
5. **One line** in `ENABLED_MODULES` (`src/llm/agents/modules.py`) — this is the single
   edit that turns the agent on, and it's the only central file you should need to
   touch. If you find yourself editing a second central file to make an agent appear,
   stop and check whether the new thing actually needs a static page instead (see
   AGENTS.md's "Adding a static page" section) — pages don't touch `ENABLED_MODULES` at
   all.

A folder that exists on disk but isn't in `ENABLED_MODULES` must be completely inert —
not imported, no configs loaded, invisible to the sidebar. That's what makes "scaffold
the agent, wire it up in a follow-up PR" a safe intermediate state. Don't rely on a
partially-built folder being "probably fine" because nothing imports it yet — verify it
actually isn't imported.

## System prompts must enforce the shared persona

Every agent inherits (or should replicate) the persona defined in `common.json`:

- Formal, professional tone for a CFO/executive audience.
- English only, no emojis.
- Direct and concise — bullet points and tables over long prose.
- Must state confidence per claim (Very High → Very Low).
- Must never present a forecast or simulation as fact.
- Decision-making stays with the user — an agent recommends, it doesn't decide.
- **Must call the relevant tool before answering a data question.** System prompts
  explicitly forbid inventing company figures. If you're writing a new agent's prompt
  and it can plausibly answer a question from "general knowledge" instead of a tool
  call, the prompt is under-constrained — say so explicitly, the way the existing
  agents' prompts do.

## Output must conform to the shared component schema

All chat-capable agents return `FinanceAgentOutput` — an ordered list of components,
each `{ format, content }` where `content` is a JSON **string** (never markdown, HTML,
or inline styling — the renderer owns presentation).

- **Maximum four components per response.**
- First component answers the primary question; order the rest for reading, not for
  convenience of generation.
- Confidence assessments should accompany factual claims, not just appear once at the
  end unrelated to which claim they cover.
- **Chart contract**: no colors, styling, or layout hints in a chart's `content` — the
  renderer assigns those (including business-meaningful defaults for labels like
  "High"/"Medium"/"Low"). Every numeric value must be a JSON number, never a string.
  Points with missing/non-finite values are silently dropped by the renderer, so don't
  rely on a `null` surviving to be handled downstream.
- **Reconciliation**: when a response includes both a table and a chart, build both from
  the *same ordered rows* from the same tool call, with identical labels and identical
  numeric values. A chart and table that disagree is a bug, not a rendering nuance — see
  the worked example in [AGENTS.md](../../AGENTS.md#reconciliation-with-tables).

Full schema and examples: [AGENTS.md § Output format](../../AGENTS.md#output-format).

## Tools

- Tools query the **latest completed import batch** for their domain — never assume
  "the most recent row," always resolve through the batch lookup the existing tools use.
- New tools go in `agents/<folder>/<name>/tools/`, common cross-agent tools in
  `agents/common/tools/`. Wrap tool calls with the existing event emitters
  (`src/llm/tool_events.py`) so the SSE stream shows live tool-call progress — don't
  bypass this for a "quick" tool.
- If a tool exposes freeform SQL access to new tables, add those tables to the correct
  domain allow-list in `common/tools/freeform_query.py` — see
  [`../principles/security.md`](../principles/security.md). Do not widen an existing
  agent's allow-list to unblock a different agent; give the new agent its own list.
- If a tool changes stored state (approving an action, persisting a simulation result),
  route it through a named service function with its own audit trail
  (`actions.service.*` is the existing pattern), not an ad hoc `UPDATE` in a freeform
  query.

## Config files

Configs are assembled disjointly: `common/config/*.json` first, then each **enabled**
module's `config/*.json` in `ENABLED_MODULES` order. A duplicate agent id across two
config files is a **hard error** at load time — that's intentional (it catches a
copy-pasted config that forgot to rename its agent id), don't work around it by renaming
one instead of finding why the collision happened. Reference shared models/constants
from `common.json` with `{{constants.OUTPUT_TYPES}}`-style template interpolation rather
than duplicating the schema inline.

## Removing or disabling an agent

Delete its id from `ENABLED_MODULES` — the folder can stay on disk. Check first whether
another module's config references one of its tools (e.g. Finance's
`get_alert_action_plan`) — a tool leaves `LOCAL_TOOLS` with its owning module, so
disabling that module can silently break a different agent's config. Grep for the tool
name across `config/*.json` before disabling, not after something breaks.

## Discovery is strict on purpose

A malformed id, a duplicate, a descriptor whose `DESCRIPTOR.id` disagrees with its
folder path — all of these raise at import rather than being skipped silently. If you
hit one of these errors while scaffolding a new agent, fix the mismatch; don't treat the
strictness as a bug to route around.
