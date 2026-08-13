# JavaScript Style — Frontend

Applies to everything under `frontend/`. React 19 + Vite, plain JavaScript (`.jsx`) —
**this codebase does not use TypeScript.** Don't introduce `.ts`/`.tsx` files piecemeal;
that's a repo-wide decision, not a per-PR one. If you think the frontend should migrate
to TypeScript, raise it as its own proposal rather than converting the file you happen
to be touching.

## No linter/formatter is configured yet — match surrounding style exactly

There's no `.eslintrc`/`eslint.config.js` or `.prettierrc` checked into `frontend/`.
Same rule as the backend: don't invent your own style, open a neighboring component and
match its conventions (quote style, semicolons, prop destructuring pattern) so a future
lint/format pass doesn't produce unrelated churn.

## Conventions already in force

- **One default-exported, PascalCase component per file** — `InventoryRiskDashboard.jsx`
  exports `InventoryRiskDashboard`. Colocate its test as
  `InventoryRiskDashboard.test.jsx` in the same folder, not in a parallel `__tests__/`
  tree.
- **Tests: `@testing-library/react` + `vitest` + `jsdom`, API calls mocked.** Frontend
  tests never hit the real dev server or backend — see `App.test.jsx` and the
  per-dashboard `*.test.jsx` files for the mocking pattern to copy.
- **Two auto-discovery mechanisms, both via `import.meta.glob`, no central import list:**
  - `frontend/src/pages/registry.js` discovers `./*/*/index.js` for static pages.
  - `frontend/src/agents/registry.js` discovers per-agent UI overrides the same way.

  A new page or override is "a folder with the right shape," not "a folder plus an edit
  to a list somewhere." See [`../principles/architecture.md`](../principles/architecture.md)
  for why this is intentionally the opposite of the backend's explicit
  `ENABLED_MODULES` registration, and don't try to unify the two patterns — they're
  solving different problems.
- **i18n: every user-facing string goes through `src/i18n.js`**, not hardcoded inline,
  with English and Bahasa Indonesia entries. `LanguageProvider.jsx` holds the active
  language in context and persists the choice to `localStorage`. If you add UI copy,
  add both locale strings in the same PR — a hardcoded English string is a bug in this
  codebase, not a shortcut to fix later.
- **Filtering is client-side against a backend-declared contract.** The backend states
  which dimensions a payload can be sliced by and which elements each filter applies to
  (`dashboard.filters`); the frontend filters the already-delivered payload. Don't add a
  new filter that round-trips to the backend per change unless the data genuinely can't
  be delivered upfront — that defeats the reason this pattern exists (a filter flip
  can't disagree with the KPI row because there's no second fetch to race).
- **There is no router.** Navigation is `activeAgent` state in `App.jsx`. The one
  cross-page linking mechanism is a hash-based deep link
  (`#main.data_source?cell=SKU_Master!G6`), and `frontend/src/pages/excelAddress.js` is
  the **only** place in the app allowed to build that href. If a new page needs to link
  to another page, add a query key to that module's contract rather than building a
  second href scheme or introducing a router dependency to solve one link.

## Component structure

Follow the existing per-agent dashboard shape (`frontend/src/agents/<folder>/<name>/`):
a dashboard component that renders a payload fetched by the shared provider, plus an
`index.js` descriptor that's auto-discovered. Don't fetch data directly inside a deeply
nested component when the shared `AgentsProvider`/`MonitoringProvider` context already
carries it — those providers exist specifically so a page doesn't need its own fetch
lifecycle for data the app already has in memory. The two pages that do own their own
fetch (`Formula Manager`, `Data Source`) do so because they call endpoints no provider
covers — that's the bar for justifying a page-local fetch, not convenience.

## Charts

`ChartRenderer.jsx` owns chart rendering (Recharts) and expects the chart contract
documented in [AGENTS.md](../../AGENTS.md#chart-contract) — colors and styling are the
renderer's job, never something a data payload should carry. If you're building UI that
produces chart data (rather than consuming an agent's), still follow that contract
shape so it round-trips through the same renderer.
