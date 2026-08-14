import { createPlaceholderBoard } from "../common/PlaceholderBoard.jsx";

export default {
  id: "retail.workforce_optimizer",
  chatLabel: "Workforce",
  dashboardComponent: createPlaceholderBoard({
    mockupPage: "awf",
    agentNumber: 7,
    summary: "Peak-hour and brand-event staffing against availability.",
    covers: [
      "FTE gap per store, and the peak-season factor behind it",
      "Full-time / part-time / gap mix — no store runs on pure full-time",
      "Brand events that are short of staff",
      "A reallocation roster committed to the ERP Workforce Schedule",
    ],
    needs: [
      "Agent 1 · Demand Forecasting — peak hours are derived from the demand curve, not typed",
      "Agent 4 · Promotion Effectiveness — the brand-event calendar is the promo calendar",
      "A workforce table in Postgres. The workbook's 160 store rows (scheduled, required, gap, peak factor) exist in Azure SQL as retail.WorkforceSnapshot and have no Postgres counterpart at all",
    ],
  }),
};
