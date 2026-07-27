// Agent metadata + optional custom dashboard view.
// The default view is the shared Workboard (dashboard payload driven).
export default {
  id: "finance.collection",
  name: "Collection",
  prompt: "Ask Collection about receivables...",
  description: "Review receivables, aging, and collection priorities.",
  starterPrompts: [
    "Summarize the largest overdue collection risks.",
    "Which customers should Collection prioritize?",
  ]
};
