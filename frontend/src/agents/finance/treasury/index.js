// Agent metadata + optional custom dashboard view.
// The default view is the shared Workboard (dashboard payload driven).
export default {
  id: "finance.treasury",
  name: "Treasury",
  prompt: "Ask Treasury about liquidity...",
  description: "Review liquidity and cash-flow forecasts.",
  starterPrompts: [
    "Explain the current cash and liquidity risks.",
    "Which action restores the minimum cash buffer fastest?",
  ]
};
