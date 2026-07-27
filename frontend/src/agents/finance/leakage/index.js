// Agent metadata + optional custom dashboard view.
// The default view is the shared Workboard (dashboard payload driven).
export default {
  id: "finance.leakage",
  name: "Leakage",
  prompt: "Ask Leakage about revenue exposure...",
  description: "Review billing gaps and revenue leakage.",
  starterPrompts: [
    "Summarize the largest leakage risks.",
    "Which leakage issues should be investigated first?",
  ]
};
