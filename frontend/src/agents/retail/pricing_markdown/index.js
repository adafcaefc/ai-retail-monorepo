import { createPlaceholderBoard } from "../common/PlaceholderBoard.jsx";

export default {
  id: "retail.pricing_markdown",
  chatLabel: "Pricing",
  dashboardComponent: createPlaceholderBoard({
    mockupPage: "a5",
    agentNumber: 5,
    summary: "Recover value from at-risk stock before it becomes a write-off.",
    covers: [
      "Markdown candidates and the depth each one needs",
      "Value at risk against value recoverable",
      "Price elasticity behind the depth chosen",
      "Our price against the market",
    ],
    needs: [
      "Agent 2 · Inventory Risk — the candidates are its expiry and slow-mover register; the mockup routes them here directly",
      "Agent 4 · Promotion Effectiveness — dim_item.elasticity is a typed per-SKU constant, not a fitted curve, so a depth recommendation resting on it has to say so",
      "A competitor price reference. The workbook's sku_master.comp_idx was never carried into Postgres, so 'priced vs market' has nothing to compare against yet",
    ],
  }),
};
