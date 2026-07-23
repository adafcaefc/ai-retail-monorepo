# AI Finance Forum Backend

Backend and chat UI for **Ledgerline Finance Forum** — an AI assistant platform for finance teams. Users ask questions about company financial data and receive structured, data-backed answers from specialized agents.

## What it does

The platform connects LLM agents to PostgreSQL financial data (collections, cashflow, performance, payment leakage) and renders responses as rich UI blocks: text, tables, charts, simulations, recommendations, and confidence assessments.

Four user-facing agents are available in the chat UI:

| UI name | Backend agent | Domain |
|---|---|---|
| Collections | `collection_agent` | Receivables, aging, DSO, recovery scenarios |
| Finance | `finance_agent` | KPIs, profitability, variance, performance |
| Leakage | `leakage_agent` | Payment integrity, duplicates, fraud signals |
| Treasury | `cashflow_agent` | Liquidity, cash forecasts, funding options |

Agents can also be consumed via Microsoft Teams (Adaptive Cards) through `/api/finance-agents/*`.

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL
- **AI:** [pydantic-ai](https://ai.pydantic.dev/) agents configured via JSON (`src/llm/config/`)
- **Frontend (dev):** React + Vite in `frontend/`
- **Frontend (production):** Self-contained `index.html` at the repo root
- **Deploy:** Docker, Azure Container Registry, Azure Container Apps

## Project layout

```
main.py                     FastAPI entry point
index.html                  Production chat UI (vanilla HTML/JS)
frontend/                   React + Vite app (local development)
src/
  api/                      REST endpoints (HTML chat, Teams webhooks)
  llm/                      Agent pipeline, tools, renderers, config
  cashflow/                 Treasury domain logic
  collections/              Collections domain logic
  chatflow/                 Conversation persistence
  db/                       Database models and session management
database/migrations/        PostgreSQL schema
scripts/import_excel/         Excel importers for financial data
tests/                      Pytest suite
```

## Running locally

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
# Configure .env (see Environment variables below)
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` for the production-style UI served from root `index.html`.

### Frontend (React dev server)

```bash
cd frontend
npm install
npm run dev
```

Vite runs on `http://127.0.0.1:5173` and proxies `/api/*` to the backend on port 8000.

## How the frontend is served today

There are two parallel frontends:

1. **Production / Docker** — FastAPI serves root `index.html` at `GET /` via `FileResponse`. The file contains inline HTML, CSS, and JavaScript. No build step is required; the Docker image copies the file as-is.

2. **Development** — The React app in `frontend/` runs as a separate Vite dev server. It calls the same backend API (`/api/html/*`) through a Vite proxy.

The React app is the intended long-term UI. The root `index.html` is a standalone fallback that mirrors the same API contract.

## Future plan: single HTML file from Vite

The goal is to replace the hand-maintained root `index.html` with a Vite build of the React app, still served as one file by FastAPI.

Planned approach:

1. Add `vite-plugin-singlefile` to inline JS and CSS into a single `index.html` at build time.
2. Configure Vite to output to a known path (e.g. `dist/index.html`).
3. Copy the built file to the repo root (or reference it directly) so `FileResponse("index.html")` continues to work unchanged.
4. Add a frontend build stage to the Dockerfile so production images ship the React-built UI instead of the hand-written one.
5. Retire the duplicate vanilla `index.html` once the React build is verified in production.

This keeps deployment simple (one file, no `StaticFiles` mount) while allowing the richer React component library (charts, simulation controls, block renderers) to become the production UI.

Alternative considered: serve `frontend/dist/` with FastAPI `StaticFiles`. That is better for caching and payload size but requires changing how the backend serves the UI. The single-file approach matches the current deployment model.

## API overview

| Route | Purpose |
|---|---|
| `GET /` | Serves chat UI (`index.html`) |
| `POST /api/html/chat` | SSE streaming chat with an agent |
| `GET /api/html/conversations` | List conversations |
| `GET /api/html/conversations/{id}` | Load a conversation |
| `POST /api/html/simulations/collections/recalculate` | Deterministic collection simulation |
| `POST /api/finance-agents/render` | Teams Adaptive Card rendering (webhook-protected) |
| `GET /health`, `/livez`, `/readyz` | Health checks |

See [AGENTS.md](./AGENTS.md) for detailed agent architecture, tools, output formats, and configuration.

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

## Database

PostgreSQL stores imported financial data (cashflow, collections, leakage) and chat conversation history. Run migrations from `database/migrations/` and import data with the scripts in `scripts/import_excel/`.

## Tests

```bash
pytest
```

## Further reading

- [AGENTS.md](./AGENTS.md) — Agent system architecture, tools, output schemas, and configuration
- [CLAUDE.md](./CLAUDE.md) — Pointer for Claude Code sessions
