# Migration: Postgres (`DATABASE_URL`) → Azure SQL (`AZURE_SQL_CONNECTIONSTRING`)

## Why

The backend ran two separate databases: Postgres (`DATABASE_URL`, via SQLAlchemy)
for the ORM/raw-SQL layer — retail dashboards, `chat.*` (conversations,
messages, alerts, actions), `retail.formula`, the finance agents — and Azure
SQL (`AZURE_SQL_CONNECTIONSTRING`, via `mssql_python`) for the workbook
ingestion pipeline and the new adaptive-retrieval vector store (`ai.*`). The
goal was to retire Postgres entirely and run everything retail-relevant
against the one Azure SQL database. Finance-side tables/tools were explicitly
out of scope (stale, not used as a migration reference).

## What changed

### Connection layer
- `backend/src/common/env.py` — `AppConfig.DATABASE_URL` replaced with
  `AZURE_SQL_CONNECTIONSTRING`.
- `backend/src/db/db.py` — `get_engine()` now builds a SQLAlchemy engine via
  the `mssql+pyodbc` dialect (`odbc_connect=` with the raw ADO.NET-shaped
  connection string, auto-appending `Driver={ODBC Driver 18 for SQL Server}`
  if missing). `session_scope()`/`get_db_session()` signatures are unchanged,
  so none of the ~14 files that depend on them needed code changes beyond the
  SQL-dialect fixes below.
- `pyodbc==5.2.0` added to `backend/requirements.txt` (replacing `psycopg`).

### SQL dialect fixes (Postgres → T-SQL)
Every file with raw SQL against the ORM-managed tables was updated:
`src/actions/repository.py`, `src/formulas/repository.py`,
`src/llm/agents/common/tools/{db,freeform_query,alert_actions}.py`, the
retail agent dashboards/tools (`inventory_risk`, `demand_forecasting`,
`replenishment`, `promotion_effectiveness`), `scripts/import_formulas_to_db.py`,
and `backend/tests/test_actions_monitoring_integration.py` /
`test_retail_fact_seed.py`. Translations applied throughout:

| Postgres | T-SQL |
|---|---|
| `LIMIT n` | `TOP (n)` (moved into the `SELECT`) |
| `count(*) FILTER (WHERE cond)` | `sum(CASE WHEN cond THEN 1 ELSE 0 END)` |
| `x ORDER BY y DESC NULLS LAST` | `ORDER BY CASE WHEN y IS NULL THEN 1 ELSE 0 END, y DESC` |
| `col::numeric`, `round(x)` (1-arg) | cast dropped, `round(x, n)` (2-arg, required in T-SQL) |
| `= ANY(:array)` | `IN :list` with `bindparam(..., expanding=True)` |
| bare boolean column in `WHERE`/`CASE` (`WHERE p.is_reorder`) | `= 1` explicit comparison (T-SQL has no implicit boolean columns) |
| `WHERE TRUE` | `WHERE 1 = 1` |
| `pg_try_advisory_lock` / `pg_advisory_unlock` | `sp_getapplock` / `sp_releaseapplock` (`@LockOwner='Session'`) |
| `INSERT ... RETURNING id` | `INSERT ... OUTPUT INSERTED.id VALUES ...` |
| `ON CONFLICT (id) DO UPDATE ...` | `MERGE ... WITH (HOLDLOCK) ... WHEN MATCHED / WHEN NOT MATCHED` |
| `NOW()` / `now()` | `SYSUTCDATETIME()` |
| `CAST(x AS jsonb)` | dropped — JSON stored as plain `NVARCHAR(MAX)`, dumped/parsed in Python |
| `text[]` column (`chat.actions.routes`) | `NVARCHAR(MAX)` JSON-array string, encoded on write / decoded on read in `repository.py` (both `save_action` **and** `save_actions`) |
| `SET TRANSACTION READ ONLY` | dropped (no T-SQL equivalent for an ad hoc session; enforced by convention instead) |
| `'a' || 'b'` string concat | `'a' + 'b'` |
| `count(DISTINCT (a, b, c))` row-constructor | `count(*)` over a `SELECT DISTINCT a, b, c` subquery |
| `sqlglot` dialect for agent-generated SQL (`freeform_query.py`) | `"postgres"` → `"tsql"` |
| `pg_constraint`/`pg_class`/`pg_namespace` (CHECK constraint introspection) | `sys.check_constraints`/`sys.tables`/`sys.schemas` |
| UUID columns returned as `uuid.UUID` by psycopg | pyodbc returns `UNIQUEIDENTIFIER` as an **uppercase `str`** — `repository._row()` now lowercases `id`/`alert_id` so generated and stored ids compare equal |

### New schema: `sql/retail/002_create_orm_schema.sql`
Azure SQL already had its own `retail.*` schema (PascalCase: `LegalEntity`,
`Store`, `Sku`, `Vendor`, `Promotion`, `InventorySnapshot`,
`ReplenishmentProposal`, ...) from the workbook-bootstrap ingestion pipeline,
plus the `ai.*` vector schema. Neither covered what the ORM/dashboard code
actually queries: `retail.dim_vertical`/`dim_item`/`dim_store`/`dim_vendor`/
`dim_calendar`, `retail.fact_*` (chain-net and per-store), `retail.
agent_kpi_reference`/`trade_agreement`/`replenishment_proposal`/
`promotion_detail`/`promotion_vertical_kpi`/`forecast_*`/`formula`, and the
entire `chat.*` schema (`conversations`, `messages`, `alerts`, `actions`,
`monitoring_runs`).

Wrote and applied a new, additive, idempotent (`IF OBJECT_ID(...) IS NULL`)
T-SQL migration translating the Postgres DDL
(`scripts/create_retail_schema.py`, `scripts/create_chat_schema.py`,
`scripts/migrate_monitoring_runs.py`) to Azure SQL types (`NVARCHAR` for
`TEXT`, `BIT` for `BOOLEAN`, `DECIMAL` for `NUMERIC`, `FLOAT` for `DOUBLE
PRECISION`, `DATETIME2(3)` for `TIMESTAMPTZ`, `BIGINT IDENTITY(1,1)` for
`BIGSERIAL`). Table partitioning (`PARTITION BY RANGE`) was dropped — not
required for correctness. New snake_case tables coexist without name
collision alongside the existing PascalCase workbook-bootstrap tables.

Applied directly against the live Azure SQL database (52 batches, all
succeeded). The three superseded Postgres scripts got a docstring pointing at
the new SQL file; they're kept only as the historical record of the shape
this schema was translated from.

**Important limitation**: the new tables were created empty. The existing
PascalCase `retail.*` tables are raw workbook staging data with no computed
fields (`margin_rp`, `at_risk_value`, `days_cover`, `state`, `growth_index`,
`is_viral`, etc.) — those are outputs of the formula engine applied to raw
data, not columns present anywhere in the raw import, so there's no view that
can map one onto the other. Populating `retail.fact_*` with real numbers is a
separate follow-up (port the seeding pipeline, or point it at the same source
workbook). `retail.formula` **was** seeded (22 rows, via the now-T-SQL-ified
`scripts/import_formulas_to_db.py`) because several agent modules read it
eagerly at import time and the app cannot start without it.

### Adaptive retrieval gateway disabled (temporary)
`backend/src/llm/pipeline.py`'s auto-invocation of `ChatRetrievalGateway` for
every `retail.*` agent is commented out: no embedding provider is configured
yet, so every call would fail (or return no evidence) and hard-abort the
agent response. The module-level `_DEFAULT_RETAIL_GATEWAY` instance is no
longer eagerly constructed either, to avoid any import-time provider loading.
Retail agents fall back to their existing `query_retail_*` tools
(`freeform_query.py`) in the meantime — kept registered, not removed, per
plan. Re-enable once `RETAIL_EMBEDDING_PROVIDER` is actually populated.

### Cleanup
- `DATABASE_URL` removed from `backend/.env.example` (replaced with an
  `AZURE_SQL_CONNECTIONSTRING` template), `docker-compose.yml` (the local
  Postgres alternative is retired — file gutted to a pointer note), and
  `README.md`.
- `backend/tests/test_actions_monitoring_integration.py`'s `skipif` now keys
  off `AZURE_SQL_CONNECTIONSTRING`.

## Verification performed
- SQLAlchemy engine connects to Azure SQL end-to-end via `mssql+pyodbc`.
- Manually exercised `TOP`+`JOIN` and `CASE`-aggregation query shapes against
  the new empty tables (0 rows, no errors).
- Manually exercised the `chat.actions`/`chat.alerts` write path: insert,
  JSON-encoded `routes` round-trips as a Python list, `IN` expanding-param
  filter, `sp_getapplock`/`sp_releaseapplock`, cleanup — all correct.
- All four retail dashboard builders (`demand_forecasting`, `inventory_risk`,
  `replenishment`, `promotion_effectiveness`) run their full query set
  against Azure SQL with no SQL errors (return empty results, as expected
  with unseeded fact tables).
- `backend/tests/test_actions_monitoring_integration.py` — **3/3 passed**
  against the live Azure SQL database (append-only double-populate, advisory
  lock contention/release, forced-failure run marking).
- Full `pytest backend/tests/` run: first pass surfaced 19 failures, all
  traced to either (a) two real Postgres-syntax bugs (`WHERE TRUE` in
  `replenishment/dashboard.py`, `count(DISTINCT (a,b,c))` row-constructor in
  a fact-seed test) — both fixed and reverified with a direct `dashboard.build()`
  call — or (b) fixture/reconciliation tests that need seeded fact data,
  which is the known follow-up below, not a SQL bug. Full suite rerun
  in progress to confirm the final count.

## Known follow-ups (not done here)
- Seed `retail.fact_*`/`dim_*` with real data (currently empty — dashboards
  build without error but return zero rows; fixture/reconciliation tests
  that assert on real data will keep failing until this is done).
- Re-enable the adaptive retrieval gateway once an embedding provider is
  configured.
- Finance-side Postgres tools/tables were left untouched (explicitly out of
  scope) — they still reference `newdata.*`/`audit.import_batches` patterns
  that were not migrated.
