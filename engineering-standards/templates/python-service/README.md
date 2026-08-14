# Backend agent skeleton

This repo doesn't have "services" in the microservice sense — the equivalent unit is a
**chivon agent folder** under `backend/src/llm/agents/<folder>/<name>/`. This directory
is a copy-paste starting point for one, matching the shape documented in
[AGENTS.md § Adding or modifying an agent](../../../AGENTS.md#adding-or-modifying-an-agent)
and [`../../ai/agent-instructions.md`](../../ai/agent-instructions.md).

Files end in `.tmpl` so they're never accidentally imported or discovered by the
registry while sitting in this template folder.

## Steps

1. Copy this folder's contents to `backend/src/llm/agents/<folder>/<name>/`, dropping
   the `.tmpl` suffixes.
2. Replace every `{{folder}}`, `{{name}}`, `{{DisplayName}}` placeholder — grep for
   `{{` after copying to make sure none were missed.
3. Fill in the tool query in `tools/{{name}}_data.py` against the real schema (`newdata`
   or `retail`) and register the table(s) it touches in the correct allow-list in
   `common/tools/freeform_query.py` if the tool is freeform-SQL-reachable — see
   [`../../principles/security.md`](../../principles/security.md).
4. Fill in `config/{{folder}}_{{name}}_chat.json` using
   [`../../ai/prompt-templates.md`](../../ai/prompt-templates.md) — don't skip the
   shared persona lines.
5. Add `"{{folder}}.{{name}}"` to `ENABLED_MODULES` in `src/llm/agents/modules.py` at
   the sidebar position you want. This is the one edit that turns the agent on.
6. Run `cd backend && pytest tests/ -q` — chivon's strict discovery will raise at import
   if the descriptor id disagrees with the folder path or a config id collides.
7. Frontend needs no change unless the agent wants custom dashboard UI — see
   [`../javascript-service/README.md`](../javascript-service/README.md) for that
   optional override.
8. Work through [`../../ai/definition-of-done.md`](../../ai/definition-of-done.md)
   before opening the PR.

## What's in this skeleton

```
config/
  {{folder}}_{{name}}_chat.json.tmpl     Chat agent config
tools/
  __init__.py.tmpl                       Re-exports TOOLS
  {{name}}_data.py.tmpl                  One example data tool
dashboard.py.tmpl                        build() returning an empty/starter dashboard payload
__init__.py.tmpl                         DESCRIPTOR = AgentDescriptor(...)
```

Monitoring/simulation/action passes aren't included here because not every agent has
them (`retail.retail` in the live codebase doesn't — see its `__init__.py` for the
minimal shape with `monitoring_passes=()`, `simulation_agent=""`, `action_agent=""`).
Add a `{{folder}}_{{name}}_monitoring.json` alongside the chat config only if the agent
needs monitoring passes, using the templates in
[`../../ai/prompt-templates.md`](../../ai/prompt-templates.md).
