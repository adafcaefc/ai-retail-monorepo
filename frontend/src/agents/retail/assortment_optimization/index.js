import { createPlaceholderBoard } from "../common/PlaceholderBoard.jsx";

export default {
  id: "retail.assortment_optimization",
  chatLabel: "Assortment",
  dashboardComponent: createPlaceholderBoard({
    mockupPage: "a6",
    agentNumber: 6,
    summary: "GMROI, tail share, delist and grow candidates, capital freed.",
    covers: [
      "Delist and grow candidates, ranked",
      "GMROI per line, and the tail's share of the range",
      "Capital freed by a range change",
      "The range change routed to ERP for approval",
    ],
    needs: [
      "Agent 2 · Inventory Risk — the tail starts as its slow-mover set",
      "Agent 5 · Pricing & Markdown — a line is only a delist candidate once markdown has failed to move it",
      "Agent 4 · Promotion Effectiveness — a line carried by promo is not a fair delist candidate on its own numbers",
    ],
  }),
};
