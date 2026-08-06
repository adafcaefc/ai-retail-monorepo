# Agent System

This document describes the LLM agent architecture used by the AI Finance Forum Backend.

> All source paths below are relative to the `backend/` directory (e.g. `src/llm/agents/` is `backend/src/llm/agents/`). Run backend commands from `backend/`.

## Overview

Agents are **modular**: each one is a self-contained folder under `src/llm/agents/<folder>/<name>/` holding its descriptor and dashboard; chat-capable agents also hold their config and tools. One constant — `ENABLED_MODULES` in `src/llm/agents/modules.py` — lists the modules that are switched on, and the registry (`src/llm/agents/__init__.py`) loads exactly those. Config JSON is loaded at startup by the **Chivon** framework (`src/llm/chivon/chivon.py`) and executed through **pydantic-ai** against Azure OpenAI.

`ENABLED_MODULES` is the single source of truth for **both** sides of the app. The backend serves it (with each module's display metadata) from `GET /api/html/agents`, and the React sidebar is built from that response — the frontend has no module list of its own. A folder that is not listed is never imported, and its configs never reach chivon. List order is sidebar order. Modules marked `dashboard_only` may reuse the shared header and frontend chat presentation, but their backend chat, monitoring, action, and data controls remain disabled.

Canonical agent ids have the form `folder.agent` (e.g. `finance.treasury`); the chivon chat/monitoring/simulation/action agents are keyed as `finance.treasury.chat`, `finance.treasury.monitoring.liquidity`, `finance.treasury.simulation`, `finance.treasury.action`.

Each agent:

1. Receives a conversation as `MessagesInput` (a list of `{sender, text}` lines).
2. May call one or more database-backed tools for verified financial data.
3. Returns structured `FinanceAgentOutput` — an ordered list of typed components.
4. Has components rendered to UI blocks (HTML, charts, simulations) by `src/llm/html_renderer.py`.

```
User message
    → POST /api/html/chat
    → render_agent_response()
    → chivon.run_async(agent_name, messages_input)
    → agent calls tools (PostgreSQL)
    → FinanceAgentOutput (components[])
    → render_ui_blocks()
    → SSE stream to client
```

## UI mockup (initial design)

The original CFO suite UX is defined in **`03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html`** at the repo root (v9.2, 21 Jul 2026). Open it in a browser with no backend — it is a static prototype with illustrative figures and canned interactions.

The mockup is the design reference for how agents should feel in the product:

| Mockup sidebar | Canonical id | Chat agent | Mockup subtitle |
|---|---|---|---|
| Finance | `finance.finance` | `finance.finance.chat` | Performance |
| Treasury | `finance.treasury` | `finance.treasury.chat` | Cash & FX |
| Collection | `finance.collection` | `finance.collection.chat` | Receivables |
| Leakage | `finance.leakage` | `finance.leakage.chat` | Payment integrity |

Each mockup agent includes a dashboard (KPI tiles, charts, what-if levers), a chat panel (prompt chips, tables, inline charts, confidence badges), and cross-agent **agentic action** flows (approval routing, action history, status notifications). Those action-plan modals are aspirational — the backend today exposes chat, tools, and structured `FinanceAgentOutput` components only.

When extending agents or renderers, treat the mockup as the target presentation layer. Agent output schemas (`text`, `table`, `chart`, `simulation`, `recommendation`, `confidence`, `next_route`) map directly to patterns shown in the mockup chat and dashboard panels.

## Agent registry

### User-facing agents

These modules appear in the dashboard sidebar because `ENABLED_MODULES` lists them. Frontend and backend share one canonical id (`folder.agent`); for chat-capable modules, the backend resolves it to the chat agent via the registry (`get_agent(id).chat_agent`, `src/llm/agents/__init__.py`).

| Canonical id | Chat agent | Display name | Folder |
|---|---|---|---|
| `finance.finance` | `finance.finance.chat` | Finance | `agents/finance/finance/` |
| `finance.treasury` | `finance.treasury.chat` | Treasury | `agents/finance/treasury/` |
| `finance.collection` | `finance.collection.chat` | Collection | `agents/finance/collection/` |
| `finance.leakage` | `finance.leakage.chat` | Leakage | `agents/finance/leakage/` |
| `retail.retail` | — (dashboard only) | Retail | `agents/retail/retail/` |

### Internal agents

| Config name | Purpose | Config file |
|---|---|---|
| `simulator_agent` | Deterministic calculation helper for interactive simulation components | `common/config/simulator.json` |

The simulator agent is not exposed directly in the UI. It is invoked by the simulation pipeline (`src/llm/simulation_pipeline.py`) when an agent returns a `simulation` component and the user adjusts inputs.

## Configuration files

Config files are assembled by the registry as `AGENT_CONFIG_FILES` (`src/llm/agents/__init__.py`): `agents/common/config/*.json` first (shared models/constants must merge before agents that reference them), then `config/*.json` for each **enabled** module, in `ENABLED_MODULES` order. Configs belonging to a folder that is not listed are not loaded, so its agent ids do not exist at runtime.

| File | Contents |
|---|---|
| `common/config/common.json` | Shared models (`MessagesInput`, `FinanceAgentOutput`, `Component`), output type rules, persona/style prompts, content schemas |
| `common/config/subagents.json` | Shared monitoring/simulation/action models and prompt constants |
| `common/config/simulator.json` | Simulator agent definition |
| `finance/<agent>/config/finance_<agent>_chat.json` | The agent's chat agent (`finance.<agent>.chat`) |
| `finance/<agent>/config/finance_<agent>_monitoring.json` | Its four monitoring agents plus its `simulation` and `action` agents |

Configs are merged at load time (strict disjoint union — a duplicate agent id across folders is a hard error). Agent entries reference shared models and constants from `common.json` using template syntax: `{{constants.OUTPUT_TYPES}}`.

Each agent entry specifies:

- `input_model` — Pydantic model for input
- `output_model` — Pydantic model for structured output
- `retries` — Number of retry attempts on failure
- `tools` — List of tool names available to the agent
- `system_prompt` — Array of prompt lines (supports template interpolation)

## Tools

Tools are Python functions assembled into the flat `LOCAL_TOOLS` map by the registry (`src/llm/agents/__init__.py` = `COMMON_TOOLS` + each descriptor's `tools`). Common tools live in `agents/common/tools/` (`freeform_query.py`, `monitoring_tools.py`, `alert_actions.py`, `db.py`); each agent's domain tools live in `agents/finance/<agent>/tools/`. They query PostgreSQL using the latest completed import batch for the relevant agent.

| Tool | Used by | Description |
|---|---|---|
| `get_financial_performance_snapshot` | Finance | Company KPIs, profit, variance, product performance |
| `get_collections_snapshot` | Collections | AR summary, customer aging, DSO, ranking data |
| `calculate_collection_scenario` | Collections | Deterministic early-payment discount / cash recovery calculation |
| `get_cashflow_baseline` | Treasury | Current cash position, weekly forecast, drivers |
| `simulate_cashflow` | Treasury | Deterministic cashflow scenario with levers (collection acceleration, payment deferral, credit draw, hedging) |
| `get_payment_leakage_snapshot` | Leakage | Payment anomalies, duplicate payments, fraud signals, recovery worklist |
| `get_alert_action_plan` | Finance | Stored alerts from `chat.alerts` with their routed actions from `chat.actions` (spec, expected impact, owners, status) |
| `simulate_action_impact` | Finance | Resolves a stored action and runs `actions.service.simulate_action` (domain simulation agent); persists `simulation_summary` and returns metrics. Mandatory gate before approval |
| `request_action_approval` | Finance | Resolves a stored action and marks it approved via `actions.service.approve_action`. Does not execute the remediation |

Tool calls are wrapped with event emitters (`src/llm/tool_events.py`) so the SSE chat stream can show live tool-call progress to the user.

Agents must call the relevant tool before answering data questions. System prompts explicitly forbid inventing company values.

## Output format

All chat-capable user-facing agents return `FinanceAgentOutput`:

```json
{
  "agent": "Finance | Treasury | Collection | Leakage",
  "components": [
    {
      "format": "text | bullet_list | table | chart | recommendation | simulation | next_route | confidence",
      "content": "{ ... JSON string matching the format schema ... }"
    }
  ]
}
```

### Component formats

Defined in `common.json` under `constants.OUTPUT_TYPES` and `constants.FINANCE_AGENT_OUTPUT_SCHEMAS`:

| Format | Purpose | Rendered as |
|---|---|---|
| `text` | Explanatory prose (max ~5 sentences) | HTML heading + paragraph |
| `bullet_list` | Multiple distinct points | HTML bullet list |
| `table` | Exact figures, before/after comparisons | HTML table |
| `chart` | Trends, rankings, comparisons | Recharts in React UI |
| `recommendation` | Prioritized actions with impact, assumptions, risks | HTML recommendation cards |
| `simulation` | Interactive what-if with adjustable inputs | HTML form + backend recalculation |
| `next_route` | Stakeholder/agent routing suggestions | HTML routing list |
| `confidence` | Confidence assessment per claim | HTML confidence badges |

Rules:

- Maximum four components per response.
- Components are ordered for display; the first should answer the primary question.
- `content` must be a valid JSON string — no markdown, HTML, or styling in agent output.
- Confidence assessments should accompany factual claims.

### Chart contract

Charts are the most structured component type. Agents emit a JSON object inside `Component.content`; the React UI renderer (`frontend/src/components/ChartRenderer.jsx`) normalises and validates it.

#### Top-level schema

```json
{
  "title": "Overdue AR by customer",
  "subtitle": "Top 5 customers by overdue balance",
  "note": "Figures in IDR mn from latest import batch.",
  "chart_type": "bar",
  "x_axis_title": "Customer",
  "y_axis_title": "IDR mn",
  "unit": "IDR mn",
  "target": 8000,
  "target_label": "Minimum buffer",
  "data": []
}
```

| Field | Required | Description |
|---|---|---|
| `title` | Yes | Short heading displayed above the chart |
| `chart_type` | Yes | See supported types below |
| `data` | Yes | Array of data points or series objects |
| `x_axis_title` | No | X-axis label |
| `y_axis_title` | No | Y-axis label; may also convey the unit |
| `subtitle` | No | Supporting context below the title |
| `note` | No | Caveats, definitions, or data-source footnote |
| `unit` | No | Explicit unit label (fallback if `y_axis_title` is absent) |
| `target` | No | Reference threshold for line-chart comparisons |
| `target_label` | No | Label for the target line |

Do not include colours, styling, layout hints, or rendering instructions. The renderer assigns colours automatically (including business-meaningful defaults for labels like "High", "Medium", "Low", aging buckets, etc.).

#### Supported `chart_type` values

| Agent value | Web UI renderer | Use when |
|---|---|---|
| `line` | Line chart | Trends over time, multi-series comparisons |
| `bar`, `column` | Bar chart | Rankings, category comparisons |
| `waterfall`, `bridge`, `variance_bridge`, `ebitda_bridge` | Waterfall chart | Variance/EBITDA bridges, step drivers |
| `pie` | Pie chart | Simple part-to-whole (2–6 categories) |
| `donut`, `doughnut` | Donut chart | Same as pie, with centre space |
| `area` | Area chart | Area trends over time |
| Other (e.g. `scatter`) | Falls back to bar | Avoid unless no alternative |

If `chart_type` is `bar` and the title/subtitle contains "bridge" or "waterfall", the web UI auto-detects a waterfall chart.

#### Single-series data shape

Used for bar, column, waterfall, pie, and donut charts, and for simple single-series line charts.

```json
{
  "chart_type": "bar",
  "title": "Estimated recovery by customer",
  "y_axis_title": "IDR mn",
  "data": [
    { "label": "PT Anugerah Prima", "value": 4200 },
    { "label": "PT Maju Jaya", "value": 3100 },
    { "label": "PT Sinar Abadi", "value": 2800 }
  ]
}
```

**Point field aliases** (renderer accepts any of these):

| Role | Preferred | Accepted aliases |
|---|---|---|
| Category label | `label` | `name`, `category`, `x`, `week`, `period` |
| Numeric value | `value` | `y`, `amount`, `total` |

Rules:

- Every value must be a **number**, not a string. `"5000"` is invalid; `5000` is correct.
- Points with missing or non-finite values are silently dropped.
- Preserve exact labels and values from tool output — do not re-round or rename customers/periods.

#### Multi-series data shape

Used for line charts comparing actual vs baseline, buffer, target, or scenario.

```json
{
  "chart_type": "line",
  "title": "Closing cash vs minimum buffer",
  "x_axis_title": "Week",
  "y_axis_title": "USD",
  "data": [
    {
      "legend": "Closing cash",
      "values": [
        { "label": "W1", "value": 24000 },
        { "label": "W2", "value": 26000 },
        { "label": "W3", "value": 25500 }
      ]
    },
    {
      "legend": "Minimum buffer",
      "values": [
        { "label": "W1", "value": 8000 },
        { "label": "W2", "value": 8000 },
        { "label": "W3", "value": 8000 }
      ]
    }
  ]
}
```

Rules:

- Each series object requires `legend` (series name) and `values` (array of `{ label, value }` points).
- All series being compared should share the same label set (e.g. all cover W1–W13).
- Use multi-series line charts when overlaying a threshold, buffer, target, or scenario against actuals.

#### Reconciliation with tables

When a response includes both a chart and a table (common in Collections agent responses):

1. Build both from the **same ordered rows** returned by the tool.
2. Use **identical labels** in chart `data[].label` and table row labels.
3. Use **identical numeric values** — the chart, table, and narrative must reconcile.
4. Typical component order: `text` → `table` → `chart` → `simulation`.

#### Examples by use case

**Customer ranking (Collections):**

```json
{
  "title": "Overdue balance by customer",
  "chart_type": "bar",
  "y_axis_title": "IDR mn",
  "data": [
    { "label": "Customer A", "value": 12500 },
    { "label": "Customer B", "value": 9800 }
  ]
}
```

**Cash forecast vs buffer (Treasury):**

```json
{
  "title": "13-week closing cash forecast",
  "chart_type": "line",
  "x_axis_title": "Week",
  "y_axis_title": "USD",
  "data": [
    {
      "legend": "Closing cash",
      "values": [
        { "label": "W1", "value": 2400000 },
        { "label": "W2", "value": 2350000 }
      ]
    },
    {
      "legend": "Minimum buffer",
      "values": [
        { "label": "W1", "value": 800000 },
        { "label": "W2", "value": 800000 }
      ]
    }
  ]
}
```

**Risk distribution (Leakage):**

```json
{
  "title": "Leakage exposure by category",
  "chart_type": "donut",
  "data": [
    { "label": "Duplicate payments", "value": 320 },
    { "label": "Overpayments", "value": 180 },
    { "label": "Unmatched invoices", "value": 95 }
  ]
}
```

### Simulation components

Simulations include:

- `inputs` — User-adjustable parameters (id, label, min, max, step, default, unit)
- `outputs` — Calculated metrics
- `calculation_instructions` — Explicit formulas referencing input/output labels
- `action` — Backend handler to invoke on submit (e.g. `calculate_collection_scenario`, `simulate_cashflow`)
- `submit_data` — Fixed context (e.g. customer name) passed to the backend

Collection simulations use `action = "calculate_collection_scenario"` with input IDs `cash_to_collect_idr_mn` and `discount_pct`.

Cashflow simulations use `action = "simulate_cashflow"` with input IDs `accelerate_collection_idr_mn`, `defer_payment_idr_mn`, `credit_line_draw_idr_mn`, and `hedge_usd`.

## Rendering pipeline

```
FinanceAgentOutput.components
    → render_ui_blocks()          (src/llm/html_renderer.py)
    → list[UiBlock]               (type: html | chart | simulation | next_route)
    → SSE assistant_response event
    → Client renders blocks
```

The HTML renderer converts each component format to a self-contained HTML fragment. The React frontend (`frontend/src/components/BlockRenderer.jsx`, `ChartRenderer.jsx`, `SimulationRenderer.jsx`) renders the same block types with richer interactivity.

## API endpoints

### HTML chat (used by web UI)

Prefix: `/api/html`

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Stream a chat response (SSE). Body: `{ agent, message, conversation_id? }` — `agent` is a canonical id (`finance.treasury`) |
| `GET` | `/agents` | The enabled modules, in `ENABLED_MODULES` order (`{ id, folder, name, display, description, prompt, starter_prompts }`). The frontend sidebar is built entirely from this |
| `GET` | `/dashboard/{agent}` | Dashboard payload for one canonical agent id |
| `GET` | `/conversations` | List stored conversations |
| `GET` | `/conversations/{id}` | Get messages for a conversation |
| `POST` | `/simulations/{collection,treasury,finance,leakage}/recalculate` | Recalculate a scenario deterministically |

SSE event types: `status`, `tool_call`, `tool_result`, `assistant_response`, `done`, `error`.

## Chivon framework

Chivon (`src/llm/chivon/chivon.py`) is the agent loader/runner:

- **`load_from_file()`** — Parses JSON configs, builds Pydantic input/output models dynamically, creates pydantic-ai `Agent` instances with system prompts and tools.
- **`run_async()`** — Executes an agent with validated input.
- **`type()`** — Returns a registered Pydantic model by name (e.g. `FinanceAgentOutput`).

Loaded at startup via `load_chivon()` in `src/llm/chivon/loader.py`, which feeds it the registry's `AGENT_CONFIG_FILES` and `LOCAL_TOOLS` plus the Azure OpenAI model provider.

## Data sources

Financial data is imported from Excel spreadsheets into PostgreSQL. Each import creates an audit batch (`audit.import_batches`) tagged with an importer agent name (`financial_performance_agent`, `cashflow_agent`, `collections_credit_agent`, `payment_leakage_fraud_agent`). Tools always query the latest completed batch. These importer names are distinct from the canonical agent ids and are not renamed by the `folder.agent` scheme.

## Conversation persistence

Chat conversations are stored via `src/chatflow/repository.py`. The HTML chat API creates conversations, saves messages, and supports listing/loading history.

Note: Full history integration into agent context is partially implemented — see TODO comments in `src/api/finance_agents_html.py`.

## Persona and style

All agents share a common persona defined in `common.json`:

- Formal, professional tone suitable for CFO/executive audience
- English only, no emojis
- Direct and concise; bullet points and tables preferred over long prose
- Must assess confidence in claims (Very High → Very Low)
- Never present forecasts or simulations as facts
- Decision-making remains with the user

## Adding or modifying an agent

An agent is one folder plus one line. To add `finance.<name>`, create `src/llm/agents/finance/<name>/`:

1. `config/finance_<name>_chat.json` and `config/finance_<name>_monitoring.json` — chat + monitoring/simulation/action agents, keyed `finance.<name>.chat`, `finance.<name>.monitoring.*`, `finance.<name>.simulation`, `finance.<name>.action`.
2. `tools/<name>_data.py` exposing a `TOOLS` dict; `tools/__init__.py` re-exports it.
3. `dashboard.py` exposing `build()` (uses helpers from `agents/common/dashboard_blocks.py`).
4. `__init__.py` exposing `DESCRIPTOR = AgentDescriptor(...)`, including the presentation strings the sidebar renders (`display`, `description`, `prompt`, `starter_prompts`).
5. Add `"finance.<name>"` to `ENABLED_MODULES` in `src/llm/agents/modules.py`, at the position you want it to occupy in the sidebar. **This is the only central edit, and it is what switches the agent on.**
6. Frontend: nothing to do — the sidebar picks it up from `GET /api/html/agents`. Only if the agent needs custom UI, add an optional `frontend/src/agents/finance/<name>/index.js` default-exporting `{ id, ... }`; it is auto-discovered by `import.meta.glob` and its fields override the API's.
7. If the domain has new tables, add them to the allow-lists in `agents/common/tools/freeform_query.py`.
8. Add tests as needed.

To **remove** an agent, delete its id from `ENABLED_MODULES`. The folder can stay on disk — it is no longer imported, its tools leave `LOCAL_TOOLS`, its configs leave chivon, and it disappears from the sidebar. Note that a tool owned by one module and referenced by another's config (e.g. Finance's `get_alert_action_plan`) leaves with its owner, so disabling that module breaks the config that references it.

A dashboard-only module follows the same registry pattern but sets `dashboard_only=True`, may omit Chivon configs and tools, and supplies an empty or custom `build_dashboard`. Its frontend module override provides `dashboardComponent`; the shared shell may still render its normal header and chat presentation, while `dashboard_only` prevents chat submission and disables monitoring, action, and data requests.

Discovery is strict: an id that is malformed, duplicated, missing on disk, or whose `DESCRIPTOR.id` disagrees with its folder path raises at import rather than being skipped.

## Key source files

| File | Role |
|---|---|
| `03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html` | Initial UI mockup — static CFO suite prototype (design reference) |
| `src/llm/chivon/chivon.py` | Agent framework (config parsing, model building, execution) |
| `src/llm/chivon/loader.py` | Startup loader (`load_chivon`, `get_chivon`) |
| `src/llm/agents/modules.py` | **`ENABLED_MODULES`** — the one list of enabled modules, in sidebar order |
| `src/llm/agents/__init__.py` | Registry: loads the enabled descriptors, builds `AGENT_CONFIG_FILES` / `LOCAL_TOOLS`, `get_agent()` |
| `src/llm/agents/descriptor.py` | `AgentDescriptor` / `MonitoringPass` dataclasses |
| `src/llm/agents/finance/<name>/` | Per-agent config, tools, dashboard, descriptor |
| `src/llm/agents/common/` | Shared config, tools (`freeform_query`, `monitoring_tools`, `alert_actions`, `db`), `dashboard_blocks.py` |
| `src/llm/pipeline.py` | `render_agent_response()` orchestration |
| `src/llm/html_renderer.py` | Component → UI block rendering |
| `src/llm/model_provider.py` | Azure OpenAI model configuration |
| `src/api/finance_agents_html.py` | HTML chat SSE API |
| `frontend/src/agents/AgentsProvider.jsx` | Fetches `GET /api/html/agents` once and shares the module list app-wide (`useAgents()`) |
| `frontend/src/agents/registry.js` | Shapes the API response for the UI (`buildAgents`, `groupByFolder`) + auto-discovered optional per-agent overrides |
