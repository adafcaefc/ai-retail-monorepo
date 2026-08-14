import { createPlaceholderBoard } from "../common/PlaceholderBoard.jsx";

export default {
  id: "retail.vendor_brand_performance",
  chatLabel: "Vendor",
  dashboardComponent: createPlaceholderBoard({
    mockupPage: "avb",
    agentNumber: 8,
    summary: "Vendor scorecard, OTIF, funding, and brand contribution.",
    covers: [
      "Vendor scorecard: OTIF, fill rate, defect, lead adherence",
      "GMV and funding run-rate per vendor",
      "Brand contribution and the top brands behind it",
      "Concentration risk across vendors and brands",
    ],
    needs: [
      "Agent 3 · Replenishment — it already scores vendor service on reorder lines; this board is that scoring widened to the whole book, not a second copy of it",
      "Agent 4 · Promotion Effectiveness — supplier funding is confirmed against promo offers",
      "Brand facts. Postgres carries brand only as a column on dim_item; the workbook's brand_performance rows live in Azure SQL and were never seeded across",
      "Delivery history over time. retail.fact_purchase_receipt is empty and every vendor metric today is one snapshot, so no trend can be drawn from them",
    ],
  }),
};
