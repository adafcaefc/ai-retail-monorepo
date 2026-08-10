# AI Finance Forum Backend

Backend and chat UI for **Ledgerline Finance Forum** — an AI assistant platform for finance teams. Users ask questions about company financial data and receive structured, data-backed answers from specialized agents.

## What it does

The platform connects LLM agents to PostgreSQL financial data (collections, cashflow, performance, payment leakage) and renders responses as rich UI blocks: text, tables, charts, simulations, recommendations, and confidence assessments.

Four finance agents and a Retail module are available in the sidebar. The finance agents
read the `newdata` schema; Retail is chat-only and calls Dynamics 365 live instead:

Each agent is a self-contained folder under `src/llm/agents/<folder>/<name>/`
with a canonical id of the form `folder.agent`. Adding an agent means adding
that folder plus its id in `ENABLED_MODULES`.

| UI name | Canonical id | Chat agent | Domain |
|---|---|---|---|
| Finance | `finance.finance` | `finance.finance.chat` | KPIs, profitability, variance, performance |
| Leakage | `finance.leakage` | `finance.leakage.chat` | Payment integrity, duplicates, fraud signals |
| Collection | `finance.collection` | `finance.collection.chat` | Receivables, aging, DSO, recovery scenarios |
| Treasury | `finance.treasury` | `finance.treasury.chat` | Liquidity, cash forecasts, funding options |
| Retail | `retail.retail` | `retail.retail.chat` | Demand, stock cover, reorder signals — read live from D365 F&O, not from PostgreSQL. Its dashboard panel is still an empty shell |

Chat-capable agents can also be consumed via Microsoft Teams (Adaptive Cards) through `/api/finance-agents/*`.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL
- **AI:** [pydantic-ai](https://ai.pydantic.dev/) agents configured via JSON, one folder per agent under `src/llm/agents/`
- **Frontend (dev):** React + Vite in `frontend/`
- **Frontend (production):** Vite build in `frontend/dist`, served by FastAPI
- **Deploy:** Docker, Azure Container Registry, Azure Container Apps

## UI mockup (initial design)

The original product vision is captured in a self-contained HTML prototype at the repo root:

**[`03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html`](./03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html)** — *CFO Finance AI Suite mockup v10.1 (28 Jul 2026)*

Open it directly in a browser (no backend required). It is **illustrative only**: static ERP-style figures, canned chat replies, and client-side what-if math. It is not wired to the API or PostgreSQL.

The mockup defines the target **Ledgerline Finance suite** experience:

- Sidebar with four agents — Finance, Leakage, Collection, Treasury — using the same canonical IDs as the backend (`finance.finance`, `finance.leakage`, `finance.collection`, `finance.treasury`)
- Per-agent dashboard: KPI tiles, focus charts, side panels, what-if simulator, and suggested next actions
- Right-hand chat panel with chips, tables, charts, and confidence badges
- Cross-agent **agentic action** flows (approval routing, history, notifications) — design reference only; not implemented in the backend yet

The live app (`frontend/`) implements the chat + structured agent responses against real data. The mockup remains the north-star layout for the full dashboard experience.

## Project layout

```
03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html
                            UI mockup: Nusantara group, 3 entities, filters
                            (static prototype; open in browser)
Dataset_AI_Finance_Forum_V1.0_20260728.xlsx
                            The live dataset (star schema), loaded into the
                            `newdata` schema — see Database below
README_DATASET_V1.0_SCHEMA.md
                            That dataset's schema, ERD and migration notes
exisitingdb/                The four superseded workbooks; their schemas are
                            still in the database but nothing reads them
scripts/                    Excel importers, the SQL runner, and the verifiers
Dockerfile                  Multi-stage build (context = repo root): builds
                            frontend, then backend runtime
frontend/                   React + Vite app (built + served in production)
  src/agents/               Per-agent UI overrides for backend modules
  src/pages/                Static pages: frontend-only screens that are not
                            agents (no backend module, chat or monitoring).
                            Each <folder>/<name>/ is auto-discovered and
                            becomes a sidebar group — see AGENTS.md
  src/filters.js            Client-side dashboard filtering (QC-043)
  src/i18n.js               English/Bahasa Indonesia strings (QC-058)
  src/LanguageProvider.jsx  Language context; choice persists in localStorage
tmp/                        Scratch workspace (git-ignored)
backend/                    Python service (run everything from here)
  main.py                   FastAPI entry point
  requirements.txt          Python dependencies
  tests/                    102 fixture-based tests; no database required
  src/
    api/                    REST endpoints (HTML chat, Teams webhooks)
    actions/                Action store; impact.py recomputes cash impact
                            from the forecast instead of trusting stored prose
    llm/
      chivon/               Agent framework (config loader/runner)
      agents/               One folder per agent (finance/<name>/): config,
                            tools, dashboard; plus common/ shared tools+blocks
        common/tools/period.py
                            Treasury's forecast span (QC-035). The other three
                            agents derive their period in their own tools
      pipeline.py, ...      Agent pipeline and renderers
    cashflow/               Treasury import/service layer
    collections/            Collections cards layer
    chatflow/               Conversation persistence
    db/                     Database models and session management
```

## Current state

The product runs end to end against the live database. Recent work has been QC
remediation ahead of a CFO demo — 27 findings are closed and re-checkable with
`scripts/verify_qc_fixes.py`, including:

- **Filters** (`dashboard.filters`) — the backend declares which dimensions a payload can
  be sliced by and which elements each applies to; the frontend filters the delivered
  payload, so changing a filter costs no round trip and cannot disagree with the KPI row.
- **Period labels** — every chart states the span it covers, derived per domain from that
  domain's own data rather than assumed.
- **Bahasa Indonesia toggle** — payload and chrome translated on arrival; figures untouched.
- **Computed action impact** — Treasury action cards derive their before/after figures
  from the cash-flow forecast rather than replaying a sentence the model wrote when the
  action was seeded.

QC-002 and QC-003 — the four agents sitting on unrelated import batches, and their
revenue bases not being comparable — were properties of the old dataset and are closed
by the migration to `newdata`. All four agents now read one dataset, and Collection's
DSO denominator is provably the same revenue Finance reports.

Two verifiers keep this honest, and they answer different questions:

```bash
cd backend
../.venv/Scripts/python.exe ../scripts/verify_new_dataset.py   # is the DATA right?
../.venv/Scripts/python.exe ../scripts/verify_agent_bugs.py    # is the APP right?
```

`verify_new_dataset.py` re-expresses the dataset's own 14 reconciliation checks and 25
KPI derivations as SQL — a failure means the import is wrong. `verify_agent_bugs.py`
compares what each dashboard actually puts on screen against the same figures
recomputed from `newdata` — a failure means the application is wrong even though the
data is right. Both exit non-zero on failure, so either can gate a build.

## Running locally

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt
# Configure backend/.env (see Environment variables below)
cd backend
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` for the production-style UI. The server also serves the React build from the sibling `frontend/dist` when present.

Run uvicorn from `backend/`; imports are rooted there (`from src...`). A `--port` flag
overrides `PORT` in `.env`; `PORT` only applies when launching with `python main.py`.

### Frontend (React dev server)

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://127.0.0.1:5173` and proxies `/api/*` to the backend.

The app opens on **Main → Formula Store**, a static page rather than an agent board, so the
sidebar and both Main pages render even with the backend down — only the agent folders need
the API. Adding a page is described in [AGENTS.md](./AGENTS.md#adding-a-static-page-not-an-agent).

**The proxy target and the backend port must match.** The target is set in
[`frontend/vite.config.js`](./frontend/vite.config.js) and is currently `8000`. If you
start the backend on another port, change it there too, or the dev server's API calls
fail with no error on the backend side.

### Tests

```bash
cd backend
../.venv/Scripts/python.exe -m pytest tests/ -q     # 102 tests, no database needed

cd frontend
npm test                                            # vitest + jsdom, API mocked
```

Both suites run against fixtures. To check the findings that can only be settled against
real data, run the QC verifier, which needs a live `DATABASE_URL`:

```bash
cd backend
python ../scripts/verify_qc_fixes.py
```

Each row prints `PASS`, `OPEN` or `MANUAL` with the figure it was decided on. Exit code
is 1 only when a `PASS` regresses; `OPEN` rows are known work, not failures.

## How the frontend is served

- **Production / Docker** — The root `Dockerfile` is multi-stage: stage 1 (`node`) runs `npm ci && npm run build` on `frontend/`; stage 2 (`python`) installs the backend and copies the built `frontend/dist` to `/app/frontend/dist`. At runtime FastAPI serves `frontend/dist/index.html` at `GET /` (`main.py` resolves it as `BASE_DIR.parent/frontend/dist`). Returns 503 if no build is present.
- **Development** — The React app in `frontend/` runs as a separate Vite dev server (`npm run dev`) and calls the backend API through a Vite proxy.
- **Design reference** — `03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html` is the original static CFO suite prototype; it does not call the backend.

## API overview

| Route | Purpose |
|---|---|
| `GET /` | Serves the React build (`frontend/dist/index.html`) |
| `GET /api/html/agents` | Registry-driven list of user-facing agents |
| `POST /api/html/chat` | SSE streaming chat with an agent |
| `GET /api/html/dashboard/{agent}` | Dashboard payload for a canonical agent id |
| `GET /api/html/conversations` | List conversations |
| `GET /api/html/conversations/{id}` | Load a conversation |
| `POST /api/html/simulations/{collection,treasury,finance,leakage}/recalculate` | Deterministic simulation |
| `POST /api/finance-agents/render` | Teams Adaptive Card rendering (webhook-protected) |
| `GET /health`, `/livez`, `/readyz` | Health checks |

See [AGENTS.md](./AGENTS.md) for detailed agent architecture, tools, output formats, and configuration.

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Database

PostgreSQL stores imported financial data and chat conversation history. Full column
detail is in [database-structure.md](./database-structure.md); this is the shape.

### Schemas

| Schema | Tables | Holds |
|---|---:|---|
| `financial_performance` | 11 | KPIs, P&L, product margins, variance drivers, simulator levers and results |
| `cashflow` | 7 | 13-week forecast, AR timing, AP payables, other outflows, FX scenarios |
| `collections` | 7 | Customer credit and ageing, risk scores, DSO impact, recovery worklist |
| `payment_leakage` | 7 | AP transactions, anomaly detections, category breakdowns, action worklist |
| `chat` | 4 | Conversations, messages, alerts, actions |
| `audit` | 1 | Import lineage — one row per attempted workbook import |

37 application tables in total.

### How the domain data is organised

Every imported table hangs off one row in `audit.import_batches` via
`import_batch_id`, with `ON DELETE CASCADE`. A domain query picks a completed batch
first, then reads that batch's rows.

```
audit.import_batches ──┬─< financial_performance.*   (batch 19)
                       ├─< cashflow.*                (batch 2)
                       ├─< collections.*             (batch 11)
                       └─< payment_leakage.*         (batch 17)

chat.conversations ──< chat.messages
chat.alerts ──< chat.actions
```

Conventions worth knowing before reading any query:

- Columns ending `_idr_mn` are **IDR millions**; `usd_amount` and `usd_exposure` are USD.
- `source_sheet` records which workbook sheet produced each row.
- Week fields constrained to `1`–`13` are the thirteen-week cashflow horizon.
- `chat.actions.routes` is a PostgreSQL array of owner names.

### The known structural limitation

The four agents currently sit on **four unrelated import batches**, loaded from four
separately authored workbooks in [`exisitingdb/`](./exisitingdb/). There is no entity
dimension and no period dimension anywhere in the 32 domain tables — `import_batch_id`
is the only discriminator.

Two consequences show up directly in the product:

- Figures are not comparable across agents. Collection's revenue base is annual while
  Finance's is monthly, and no column states which is which.
- A filter has no column to attach to, which is why entity and period filtering is
  currently applied client-side to an already-delivered payload.

This describes the four superseded schemas, which are still present but no longer read.
`Dataset_AI_Finance_Forum_V1.0_20260728.xlsx` replaced them with a star schema carrying
real entity and period dimensions, loaded into `newdata`, which removes both problems.
See [README_DATASET_V1.0_SCHEMA.md](./README_DATASET_V1.0_SCHEMA.md) for that schema and
the migration notes.

The live database is authoritative. Re-run catalog queries when it changes rather than
trusting the migration files, which are implementation history and do not describe every
deployed table.

## Further reading

- [README_DATASET_V1.0_SCHEMA.md](./README_DATASET_V1.0_SCHEMA.md) — The live dataset: schema, ERD, value domains, and the migration it came from
- [database-structure.md](./database-structure.md) — Full deployed schema: every table, column, constraint and index
- [AGENTS.md](./AGENTS.md) — Agent system architecture, tools, output schemas, and configuration
- [03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html](./03_CFO_FinanceAI_Suite_Mockup_v10.1_dengan_dataset_baru_20260728.html) — Initial UI mockup (static prototype)
- [CLAUDE.md](./CLAUDE.md) — Pointer for Claude Code sessions
