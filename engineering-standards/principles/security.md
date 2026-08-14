# Security Principles

This repo's biggest security surface is that **LLM agents write SQL and arithmetic
expressions that get executed**. The patterns below exist specifically to make that
safe, plus the ordinary web-app baseline (secrets, input validation, least privilege).

## Never build SQL by string interpolation

All database access goes through SQLAlchemy `text()` with bound parameters
(`backend/src/llm/agents/common/tools/db.py`):

```python
result = connection.execute(text(statement), parameters).mappings()
```

No f-string or `.format()` SQL, ever — not even for "safe" values like an internal
enum or a table name you control. If a query needs a dynamic table name, resolve it
through an allow-list lookup (below), not string substitution.

## Agent-authored SQL is parsed, not trusted

Chat agents can run free-form SQL through `common/tools/freeform_query.py`, but the
tool never hands raw text to the database:

1. The statement is parsed with `sqlglot` (dialect `postgres`) into an AST — not
   validated with a regex, which is trivially bypassed.
2. Statement type is restricted (`SELECT`/`INSERT`/`UPDATE`/`DELETE`/`WITH` — a fixed
   `Literal`).
3. Every table referenced must appear in that **domain's** allow-list
   (`FINANCE_ALLOWED_TABLES`, `CASHFLOW_ALLOWED_TABLES`, `RETAIL_SHARED_TABLES` +
   per-board additions, etc.). Finance's chat agent cannot touch a Treasury table even
   though both exist in the same database.

**If you add a new table an agent should be able to query, add it to that domain's
allow-list explicitly.** Don't widen an existing list to cover a new use case for a
different agent — give the new agent its own list (composed from `RETAIL_SHARED_TABLES`
or similar if it's genuinely shared), so each domain's blast radius stays visible from
one tuple in one file.

## Never `eval()` user- or model-supplied expressions

`src/formulas/expression.py` evaluates the 19 stored retail/finance formulas —
arithmetic like `MAX(0, required - scheduled)` — without ever calling `eval()` or
`ast.parse()`. It tokenizes a fixed grammar, parses to a tuple AST, and walks it against
an explicit allow-list (`MAX MIN ROUND CEILING IF AND OR NOT`). `IF` short-circuits so a
guard like `IF(qty > 0, total / qty, 0)` can't divide by zero. Follow this pattern for
any future "evaluate an expression from data" feature — a hand-rolled grammar over a
fixed operator set, not a general-purpose evaluator with a blocklist bolted on.
Blocklists on `eval` are a known-broken pattern; don't reintroduce one.

Excel syntax (`!`, `$`, sheet references) is rejected by the parser with a message that
says so, not silently coerced — `resources/formula.md` is reference material used to
*derive* an expression, never a thing the app parses live.

## Secrets

- Real values live only in `.env` (backend) / local env (frontend), never committed.
  `.gitignore` blocks `.env` and `.env.*` but explicitly keeps `!.env.example` — the
  example files document required **shape**, not real credentials.
- When you add a new required environment variable, add it to `.env.example` with a
  comment explaining what it's for and what happens if it's unset (see the existing
  entries — `EXCEL_WORKBOOK_PATH` pointed at a missing path is documented to 503 the
  Data Source endpoints rather than crash the app; that's the standard to match for any
  new optional integration).
- `LOG_LEVEL=DEBUG` adds a line per Azure OpenAI call with status and rate-limit
  headroom — don't let a debug log path leak request/response bodies that could contain
  customer data.

## Input validation happens at the boundary, not throughout

FastAPI/Pydantic models validate request shape at the API boundary; malformed input
returns `422`, not a 500 from something failing three layers down. Internal functions
that receive already-validated data (a tool called by chivon with a validated
`input_model`) should trust that shape rather than re-validating — see
[`api-design.md`](api-design.md) for the status-code conventions this produces.

## Writes go through named service functions, not ad hoc mutation

`request_action_approval` and `simulate_action_impact` resolve a stored action and call
`actions.service.approve_action` / `actions.service.simulate_action` — named functions
with their own audit trail — rather than letting an agent's freeform-SQL tool issue an
`UPDATE` against `chat.actions`. If you're adding a new state-changing operation an
agent can trigger, give it a named service function with explicit inputs, not a path
through the freeform query tool, even if that table is already on an allow-list for
reads.

## Least privilege by domain, not by role

There's no user-auth layer in this app yet (the Teams webhook endpoint is the one
externally-reachable surface with its own protection) — the privilege boundary that
exists today is **per-agent-domain data access** via the allow-lists above. Treat that
boundary with the same care you'd give a role-based permission system: don't let one
domain's tool "temporarily" reach into another's tables to unblock a feature. Give the
feature its own tool and its own allow-list entry instead.
