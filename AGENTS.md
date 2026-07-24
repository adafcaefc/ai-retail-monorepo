# Agent System

This document describes the LLM agent architecture used by the AI Finance Forum Backend.

## Overview

Agents are defined declaratively in JSON config files under `src/llm/config/`, loaded at startup by the **Chivon** framework (`src/llm/agents/chivon.py`), and executed through **pydantic-ai** against Azure OpenAI.

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

| Mockup sidebar | Frontend ID | Backend config | Mockup subtitle |
|---|---|---|---|
| Finance | `finance` | `finance_agent` | Performance |
| Treasury | `treasury` | `cashflow_agent` | Cash & FX |
| Collections | `collections` | `collection_agent` | Receivables |
| Leakage | `leakage` | `leakage_agent` | Payment integrity |

Each mockup agent includes a dashboard (KPI tiles, charts, what-if levers), a chat panel (prompt chips, tables, inline charts, confidence badges), and cross-agent **agentic action** flows (approval routing, action history, status notifications). Those action-plan modals are aspirational — the backend today exposes chat, tools, and structured `FinanceAgentOutput` components only.

When extending agents or renderers, treat the mockup as the target presentation layer. Agent output schemas (`text`, `table`, `chart`, `simulation`, `recommendation`, `confidence`, `next_route`) map directly to patterns shown in the mockup chat and dashboard panels.

## Agent registry

### User-facing agents

These four agents appear in the chat UI. The frontend uses short IDs; the backend maps them to config agent names in `CHAT_AGENT_MAP` (`src/api/finance_agents_html.py`). IDs and display names match the initial mockup sidebar.

| Frontend ID | Config name | Display name | Config file |
|---|---|---|---|
| `collections` | `collection_agent` | Collections | `collection.json` |
| `finance` | `finance_agent` | Finance | `finance.json` |
| `leakage` | `leakage_agent` | Leakage | `leakage.json` |
| `treasury` | `cashflow_agent` | Treasury | `cashflow.json` |

### Internal agents

| Config name | Purpose | Config file |
|---|---|---|
| `simulator_agent` | Deterministic calculation helper for interactive simulation components | `simulator.json` |

The simulator agent is not exposed directly in the UI. It is invoked by the simulation pipeline (`src/llm/simulation_pipeline.py`) when an agent returns a `simulation` component and the user adjusts inputs.

## Configuration files

All config files are listed in `AppPaths.AGENTS_CONFIG_FILES` (`src/common/constants.py`):

| File | Contents |
|---|---|
| `common.json` | Shared models (`MessagesInput`, `FinanceAgentOutput`, `Component`), output type rules, persona/style prompts, content schemas |
| `finance.json` | Finance agent definition |
| `cashflow.json` | Treasury/cashflow agent definition |
| `collection.json` | Collections agent definition |
| `leakage.json` | Leakage agent definition |
| `simulator.json` | Simulator agent definition |

Configs are merged at load time. Agent entries in domain-specific files reference shared models and constants from `common.json` using template syntax: `{{constants.OUTPUT_TYPES}}`.

Each agent entry specifies:

- `input_model` — Pydantic model for input
- `output_model` — Pydantic model for structured output
- `retries` — Number of retry attempts on failure
- `tools` — List of tool names available to the agent
- `system_prompt` — Array of prompt lines (supports template interpolation)

## Tools

Tools are Python functions registered in `LOCAL_FINANCE_TOOLS` (`src/llm/tools/finance_data.py`). They query PostgreSQL using the latest completed import batch for the relevant agent.

| Tool | Used by | Description |
|---|---|---|
| `get_financial_performance_snapshot` | Finance | Company KPIs, profit, variance, product performance |
| `get_collections_snapshot` | Collections | AR summary, customer aging, DSO, ranking data |
| `calculate_collection_scenario` | Collections | Deterministic early-payment discount / cash recovery calculation |
| `get_cashflow_baseline` | Treasury | Current cash position, weekly forecast, drivers |
| `simulate_cashflow` | Treasury | Deterministic cashflow scenario with levers (collection acceleration, payment deferral, credit draw, hedging) |
| `get_payment_leakage_snapshot` | Leakage | Payment anomalies, duplicate payments, fraud signals, recovery worklist |
| `get_alert_action_plan` | Finance | Stored alerts from `chat.alerts` with their routed actions from `chat.actions` (spec, expected impact, owners, status) |
| `simulate_action_impact` | Finance | Detection stub for impact / what-if intent, and the mandatory gate before approval. Prints to the console and returns `SIMULATION_REQUESTED`; the simulation engine itself is not implemented, so expected impact comes from the stored `impact` and `simulation_summary` values |
| `request_action_approval` | Finance | Detection stub for approval intent. Prints the request to the console and returns `APPROVAL_REQUESTED`; it grants no approval, executes nothing, and writes nothing to the database |

Tool calls are wrapped with event emitters (`src/llm/tool_events.py`) so the SSE chat stream can show live tool-call progress to the user.

Agents must call the relevant tool before answering data questions. System prompts explicitly forbid inventing company values.

## Output format

All user-facing agents return `FinanceAgentOutput`:

```json
{
  "agent": "Finance | Cashflow | Collections | Leakage",
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
| `chart` | Trends, rankings, comparisons | Recharts in React UI; Adaptive Card charts in Teams |
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

Charts are the most structured component type. Agents emit a JSON object inside `Component.content`; renderers in the React UI (`frontend/src/components/ChartRenderer.jsx`) and Teams Adaptive Cards (`src/llm/adaptive_cards.py`) normalise and validate it.

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

| Agent value | Web UI renderer | Teams Adaptive Card | Use when |
|---|---|---|---|
| `line` | Line chart | `Chart.Line` | Trends over time, multi-series comparisons |
| `bar`, `column` | Bar chart | `Chart.VerticalBar` | Rankings, category comparisons |
| `waterfall`, `bridge`, `variance_bridge`, `ebitda_bridge` | Waterfall chart | Closest bar mapping | Variance/EBITDA bridges, step drivers |
| `pie` | Pie chart | `Chart.Pie` | Simple part-to-whole (2–6 categories) |
| `donut`, `doughnut` | Donut chart | `Chart.Donut` | Same as pie, with centre space |
| `area` | Area chart | Mapped to line | Web UI only; not native in Teams |
| Other (e.g. `scatter`) | Falls back to bar | Falls back to bar | Avoid unless no alternative |

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

#### Teams Adaptive Card mapping

The Teams renderer converts agent chart JSON to Adaptive Card v1.5 chart elements:

| Source `chart_type` | Adaptive Card element | Data key mapping |
|---|---|---|
| `line` (multi-series) | `Chart.Line` | `{ legend, values: [{ x, y }] }` |
| `bar`, `column` | `Chart.VerticalBar` | `{ x: label, y: value }` |
| `pie` | `Chart.Pie` | `{ legend: label, value: value }` |
| `donut` | `Chart.Donut` | `{ legend: label, value: value }` |

Each Teams chart includes a text/fact fallback container for clients that cannot render charts.

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

See also `database/documentation/teams-adaptive-cards.md` for Teams-specific chart rendering notes.

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
| `POST` | `/chat` | Stream a chat response (SSE). Body: `{ agent, message, conversation_id? }` |
| `GET` | `/conversations` | List stored conversations |
| `GET` | `/conversations/{id}` | Get messages for a conversation |
| `POST` | `/simulations/collections/recalculate` | Recalculate a collection scenario deterministically |

SSE event types: `status`, `tool_call`, `tool_result`, `assistant_response`, `done`, `error`.

### Teams integration (Adaptive Cards)

Prefix: `/api/finance-agents` (protected by `X-Teams-Webhook-Secret` header)

Defined in `src/api/finance_agents.py`. Renders agent output as Microsoft Teams Adaptive Cards for channel-specific workflows. Each agent maps to a Teams channel ID configured in `src/common/env.py`.

## Chivon framework

Chivon (`src/llm/agents/chivon.py`) is the agent loader/runner:

- **`load_from_file()`** — Parses JSON configs, builds Pydantic input/output models dynamically, creates pydantic-ai `Agent` instances with system prompts and tools.
- **`run_async()`** — Executes an agent with validated input.
- **`type()`** — Returns a registered Pydantic model by name (e.g. `FinanceAgentOutput`).

Loaded at startup via `load_chivon()` in `src/llm/chivon_impl.py`, which wires in the Azure OpenAI model provider and local finance tools.

## Data sources

Financial data is imported from Excel spreadsheets into PostgreSQL via scripts in `scripts/import_excel/`. Each import creates an audit batch (`audit.import_batches`) tagged with an agent name. Tools always query the latest completed batch.

Database schemas:

- `database/migrations/001_create_cashflow_foundation.sql`
- `database/migrations/002_create_cashflow_tables.sql`
- `database/migrations/003_create_collections_tables.sql`

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

1. Create or edit a JSON config in `src/llm/config/`.
2. Add the file to `AppPaths.AGENTS_CONFIG_FILES` if new.
3. Register any new tools in `LOCAL_FINANCE_TOOLS` (`src/llm/tools/finance_data.py`).
4. Add a frontend mapping in `CHAT_AGENT_MAP` if the agent should appear in the UI.
5. Add rendering support in `html_renderer.py` and React components if new output formats are introduced.
6. Write tests in `tests/`.

## Key source files

| File | Role |
|---|---|
| `03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html` | Initial UI mockup — static CFO suite prototype (design reference) |
| `src/llm/agents/chivon.py` | Agent framework (config parsing, model building, execution) |
| `src/llm/chivon_impl.py` | Startup loader |
| `src/llm/pipeline.py` | `render_agent_response()` orchestration |
| `src/llm/html_renderer.py` | Component → UI block rendering |
| `src/llm/simulation_pipeline.py` | Simulation recalculation via simulator agent |
| `src/llm/model_provider.py` | Azure OpenAI model configuration |
| `src/llm/tools/finance_data.py` | Database-backed agent tools |
| `src/api/finance_agents_html.py` | HTML chat SSE API |
| `src/api/finance_agents.py` | Teams Adaptive Card API |
| `src/llm/config/*.json` | Agent definitions and shared schemas |
