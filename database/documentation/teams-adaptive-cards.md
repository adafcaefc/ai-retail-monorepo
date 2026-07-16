# Teams finance card workflow

## Power Automate flow

1. Receive the Teams message or thread in Power Automate.
2. POST it to `POST /api/finance-agents/render` with `agent_name`, `context`, and either `lines` or Graph `messages`.
3. Read `adaptiveCard` from the successful response and use **Post adaptive card and wait for a response**. A plain incoming webhook cannot process `Action.Submit`.
4. When the user selects **Recalculate**, add an HTTP action that POSTs the wait action's `body` output to `POST /api/finance-agents/simulations/recalculate`. The endpoint accepts flat card data, `{ "data": ... }`, and `{ "body": { "data": ... } }` envelopes.
5. Post the returned `adaptiveCard` as the updated result card.

The button does not call the backend by itself. Power Automate must contain the HTTP action after **Post adaptive card and wait for a response**. Do not use **Post card in a chat or channel** or a plain incoming webhook for an interactive card.

Example HTTP action:

- Method: `POST`
- URI: `https://<backend-host>/api/finance-agents/simulations/recalculate`
- Header: `Content-Type: application/json`
- Optional header: `X-Teams-Webhook-Secret: <configured secret>`
- Body expression: `body('Post_adaptive_card_and_wait_for_a_response')`

The Teams wait action accepts one response. To allow another recalculation, post the returned card with a new **Post adaptive card and wait for a response** action, typically inside a bounded loop. Updating the old message alone does not create another response listener.

Set `TEAMS_WEBHOOK_SECRET` in the backend and send the same value in the `X-Teams-Webhook-Secret` header on every finance-agent request. If the setting is omitted, header verification is disabled for local compatibility. Keep the secret in deployment configuration, not source control.

## Deterministic card endpoints

- `GET /api/cashflow/adaptive-card` returns the latest 13-week forecast, minimum-buffer line, and cash-lever controls.
- `POST /api/cashflow/adaptive-card/simulate` accepts `accelerate_collection_idr_mn`, `defer_payment_idr_mn`, `credit_line_draw_idr_mn`, and `hedge_usd`.
- `GET /api/finance-agents/collections/adaptive-card` returns the current DSO/overdue position and a Customer A offer control.
- `POST /api/finance-agents/simulations/recalculate` dispatches `simulate_cashflow` and `calculate_collection_scenario` actions.

## Chart contract

Cards use Teams Adaptive Card version 1.5 with `Chart.Line`, `Chart.VerticalBar`, `Chart.Pie`, and `Chart.Donut`. Each chart includes a text/fact fallback. Unsupported source chart requests such as area or scatter are mapped to the closest supported chart. Tables use the native `Table` element.

The specialist LLM selects and structures components, but Python constructs and validates the final card JSON. Financial calculations remain in database-backed service tools rather than in the renderer.