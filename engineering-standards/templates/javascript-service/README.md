# Frontend extensibility skeleton

The frontend has two additive extensibility points, both auto-discovered via
`import.meta.glob` with no central import list (see
[`../../principles/architecture.md`](../../principles/architecture.md) for why this is
deliberately the opposite of the backend's explicit `ENABLED_MODULES`). Pick the one
that matches what you're building:

| You want to add | Use | Backend needed? |
|---|---|---|
| A screen with no chat, no dashboard payload, no monitoring (a reference page, a tool) | [`page/`](page/) | No |
| Custom dashboard UI for an existing backend agent | [`agent-override/`](agent-override/) | Yes — the agent must already exist and appear in `GET /api/html/agents` |

Files end in `.tmpl` so they're never picked up by the glob discovery while sitting in
this template folder.

## `page/` — a static page

1. Copy `page/PageName.jsx.tmpl` and `page/index.js.tmpl` to
   `frontend/src/pages/<folder>/<name>/`, dropping `.tmpl` and renaming
   `PageName.jsx.tmpl` to your component's actual name.
2. Replace every `{{folder}}`, `{{name}}`, `{{PageName}}` placeholder.
3. If this is the app's default screen, leave `order` unset (default `0`); if it must
   avoid the default-screen slot the way Data Source does, set `order` explicitly — see
   [AGENTS.md § Adding a static page](../../../AGENTS.md#adding-a-static-page-not-an-agent).
4. Add both English and Bahasa Indonesia strings to `src/i18n.js` for any user-facing
   copy — don't hardcode text in the component.
5. That's the whole change — no registry edit. `frontend/src/pages/registry.js`
   discovers the folder automatically.

## `agent-override/` — custom dashboard UI for an existing agent

1. Copy `agent-override/index.js.tmpl` to
   `frontend/src/agents/<folder>/<name>/index.js`, dropping `.tmpl`.
2. `<folder>.<name>` **must** already be a real backend agent id returned by
   `GET /api/html/agents` — this file only overrides fields the API already serves for
   that id; it's dropped entirely if the API stops returning that id.
3. Build the dashboard component the override points at, colocated in the same folder,
   with a `*.test.jsx` beside it using `@testing-library/react` + `vitest` (see
   `frontend/src/agents/retail/inventory_risk/` for a live three-file example: the
   dashboard component, its test, and `index.js`).

## Common to both

- No TypeScript — plain `.jsx`. No project ESLint/Prettier config exists yet; match the
  surrounding file's style.
- Colocate the test next to the component (`Foo.jsx` + `Foo.test.jsx`), mock API calls,
  never hit a real dev server in a test.
