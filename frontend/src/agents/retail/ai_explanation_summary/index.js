import { createPlaceholderBoard } from "../common/PlaceholderBoard.jsx";

export default {
  id: "retail.ai_explanation_summary",
  chatLabel: "Summary",
  dashboardComponent: createPlaceholderBoard({
    mockupPage: "a7",
    agentNumber: 9,
    summary: "Executive consolidation of Agents 1-8.",
    covers: [
      "One numbered line per agent, each tracing back to that agent's own figure",
      "Where the value comes from, and what it rests on",
      "Approval status across the ERP log",
      "Reconciliation: the agents' numbers checked against each other",
    ],
    needs: [
      "Agents 1 through 8 — it summarises them, so every one of them has to report before this board can say anything true",
      "A cross-agent reconciliation rule. Two agents can price the same line differently and both be right; this board has to say which one the summary used",
    ],
  }),
};
