# API Design Principles

Full endpoint tables live in [AGENTS.md](../../AGENTS.md) and [README.md](../../README.md).
This is the conventions those endpoints share, so a new route stays consistent with the
existing ones instead of inventing its own dialect.

## Prefix per domain, no version segment

Routes are grouped by domain, not by version: `/api/html` (chat + dashboards),
`/api/excel` (workbook viewer), `/api/formulas` (formula CRUD),
`/api/finance-agents` (Teams webhook). There is currently no `/v1` segment anywhere —
this is a single deployable with no external API consumers to version against. Don't
add versioning preemptively; if an actual breaking-change-with-external-consumers need
shows up, that's the point to introduce it, not before.

## Status codes encode *why*, not just *what*

This repo distinguishes three failure shapes and uses a different code for each —
match this rather than defaulting everything to 400/500:

| Code | Means | Example |
|---|---|---|
| `404` | The specific resource doesn't exist | Unknown formula id, unknown sheet name |
| `422` | The request itself is malformed or fails validation | Bad `offset`/`limit`, unparseable formula expression, undeclared parameter, non-numeric input |
| `503` | The **deployment** is wrong, not the request | Missing workbook file, missing frontend build — the endpoint would work fine with correct configuration |

The 503 convention is the one most worth preserving deliberately: `GET /` 503s when
`frontend/dist` isn't present, and `/api/excel/*` 503s when the configured workbook path
doesn't resolve, specifically so a misconfigured deployment is distinguishable from a
client sending a bad request. If you add an endpoint that depends on an optional
external resource (a file, a feature-flagged integration), give a missing dependency its
own 503 path rather than letting it surface as a 404 or an unhandled 500.

An `offset` past the last row of a paginated resource is an **empty page**, not an
error — pagination bounds are not validation failures once `offset`/`limit` themselves
are well-formed.

## Streaming uses SSE with a fixed event vocabulary

Chat responses stream over SSE (`POST /api/html/chat`) with event types `status`,
`tool_call`, `tool_result`, `assistant_response`, `done`, `error`. If you add another
streaming endpoint, reuse this vocabulary rather than inventing new event names for the
same concepts — the frontend's SSE handling and the Teams Adaptive Card renderer both
assume this shape.

## Pagination: explicit defaults and caps, stated in the response contract

`GET /api/excel/sheets/{name}?offset=&limit=` defaults `limit` to 100 and caps it at
500. Any new paginated endpoint should state both a default and a hard cap explicitly
(in the route and in its doc table) rather than leaving `limit` unbounded — the Excel
endpoint's cap exists because the underlying parse is expensive per row; think about
your own endpoint's per-row cost before picking a number, don't just copy 500.

## Payload shape: descriptive keys by default, compact keys only when bandwidth-justified

Most JSON payloads in this API use full, readable keys. The one exception is the Excel
cell payload (`v`, `t`, `b`, `i`, `a`, `va`, `w`, `fg`, `bg`, with defaults omitted
entirely and a bare `null` for an empty cell) — justified because a single page can
carry up to 500 × 31 cells and the key overhead was measured to matter. Don't reach for
short keys as a default style choice; it costs readability everywhere it isn't actually
paying for itself. If you believe a new endpoint needs it, document the shape's legend
next to the endpoint the way `src/excel/formatting.py` does, and name the one frontend
file that owns decoding it (`cellStyle.js` is that file for the Excel payload) so the
contract isn't reverse-engineered from two places independently.

## IDs: slugify with override, not client-generated UUIDs

`POST /api/formulas` slugifies `id` from `name` when the caller omits it, and
auto-increments `number` for display ordering. Prefer this pattern (server-derived,
human-legible id with an explicit override escape hatch) over opaque client-generated
UUIDs for resources a person will reference by name in conversation or in a URL
fragment — formula ids and deep-link targets (`#main.data_source?cell=...`) both lean on
ids being readable.

## Request bodies mirror canonical domain ids, not display names

`POST /api/html/chat` takes `{ agent, message, conversation_id? }` where `agent` is the
canonical `folder.agent` id (`finance.treasury`), never the display name (`Treasury`).
Any new endpoint that references an agent, page, or module should take the canonical id
— it's the one identifier guaranteed stable across the registry, the config files, and
the frontend sidebar.
