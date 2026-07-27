// Agent metadata + optional custom dashboard view.
// The default view is the shared Workboard (dashboard payload driven).
export default {
  id: "finance.finance",
  name: "Finance",
  prompt: "Ask Finance about performance...",
  description: "Explore financial performance and plan variances.",
  starterPrompts: [
    "Explain the main finance performance risks.",
    "What are the largest EBITDA variance drivers?",
  ]
};
