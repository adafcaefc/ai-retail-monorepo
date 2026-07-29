# AI Finance Forum Backend

Backend and chat UI for **Ledgerline Finance Forum** — an AI assistant platform for finance teams. Users ask questions about company financial data and receive structured, data-backed answers from specialized agents.

## What it does

The platform connects LLM agents to PostgreSQL financial data (collections, cashflow, performance, payment leakage) and renders responses as rich UI blocks: text, tables, charts, simulations, recommendations, and confidence assessments.

Four user-facing agents are available in the chat UI:

Each agent is a self-contained folder under `src/llm/agents/<folder>/<name>/`
with a canonical id of the form `folder.agent`. Adding an agent = adding a
folder (no central registry to edit).

| UI name | Canonical id | Chat agent | Domain |
|---|---|---|---|
| Finance | `finance.finance` | `finance.finance.chat` | KPIs, profitability, variance, performance |
| Leakage | `finance.leakage` | `finance.leakage.chat` | Payment integrity, duplicates, fraud signals |
| Collection | `finance.collection` | `finance.collection.chat` | Receivables, aging, DSO, recovery scenarios |
| Treasury | `finance.treasury` | `finance.treasury.chat` | Liquidity, cash forecasts, funding options |

Agents can also be consumed via Microsoft Teams (Adaptive Cards) through `/api/finance-agents/*`.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL
- **AI:** [pydantic-ai](https://ai.pydantic.dev/) agents configured via JSON, one folder per agent under `src/llm/agents/`
- **Frontend (dev):** React + Vite in `frontend/`
- **Frontend (production):** Vite build in `frontend/dist`, served by FastAPI
- **Deploy:** Docker, Azure Container Registry, Azure Container Apps

## UI mockup (initial design)

The original product vision is captured in a self-contained HTML prototype at the repo root:

**[`03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html`](./03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html)** — *CFO Finance AI Suite mockup v9.2 (21 Jul 2026)*

Open it directly in a browser (no backend required). It is **illustrative only**: static ERP-style figures, canned chat replies, and client-side what-if math. It is not wired to the API or PostgreSQL.

The mockup defines the target **Ledgerline Finance suite** experience:

- Sidebar with four agents — Finance, Leakage, Collection, Treasury — using the same canonical IDs as the backend (`finance.finance`, `finance.leakage`, `finance.collection`, `finance.treasury`)
- Per-agent dashboard: KPI tiles, focus charts, side panels, what-if simulator, and suggested next actions
- Right-hand chat panel with chips, tables, charts, and confidence badges
- Cross-agent **agentic action** flows (approval routing, history, notifications) — design reference only; not implemented in the backend yet

The live app (`frontend/`) implements the chat + structured agent responses against real data. The mockup remains the north-star layout for the full dashboard experience.

## Project layout

```
03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html
                            Initial UI mockup (static prototype; open in browser)
Dockerfile                  Multi-stage build (context = repo root): builds
                            frontend, then backend runtime
frontend/                   React + Vite app (built + served in production)
tmp/                        Scratch workspace (git-ignored)
backend/                    Python service (run everything from here)
  main.py                   FastAPI entry point
  requirements.txt          Python dependencies
  src/
    api/                    REST endpoints (HTML chat, Teams webhooks)
    llm/
      chivon/               Agent framework (config loader/runner)
      agents/               One folder per agent (finance/<name>/): config,
                            tools, dashboard; plus common/ shared tools+blocks
      pipeline.py, ...      Agent pipeline and renderers
    cashflow/               Treasury import/service layer
    collections/            Collections cards layer
    chatflow/               Conversation persistence
    db/                     Database models and session management
```

## Running locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
# Configure backend/.env (see Environment variables below)
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` for the production-style UI. The server also serves the React build from the sibling `frontend/dist` when present.

### Frontend (React dev server)

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://127.0.0.1:5173` and proxies `/api/*` to the backend on port 8000.

## How the frontend is served

- **Production / Docker** — The root `Dockerfile` is multi-stage: stage 1 (`node`) runs `npm ci && npm run build` on `frontend/`; stage 2 (`python`) installs the backend and copies the built `frontend/dist` to `/app/frontend/dist`. At runtime FastAPI serves `frontend/dist/index.html` at `GET /` (`main.py` resolves it as `BASE_DIR.parent/frontend/dist`). Returns 503 if no build is present.
- **Development** — The React app in `frontend/` runs as a separate Vite dev server (`npm run dev`) and calls the backend API through a Vite proxy.
- **Design reference** — `03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html` is the original static CFO suite prototype; it does not call the backend.

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

PostgreSQL stores imported financial data (cashflow, collections, leakage) and chat conversation history.

## Further reading

- [03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html](./03_CFO_FinanceAI_Suite_Mockup_v9.2_20260721.html) — Initial UI mockup (static prototype)
- [AGENTS.md](./AGENTS.md) — Agent system architecture, tools, output schemas, and configuration
- [CLAUDE.md](./CLAUDE.md) — Pointer for Claude Code sessions
