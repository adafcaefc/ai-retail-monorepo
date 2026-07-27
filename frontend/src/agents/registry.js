// Frontend agent registry.
//
// The enabled modules and all their presentation strings come from the
// backend (`GET /api/html/agents`, driven by agents/modules.py). Nothing here
// decides which agents exist — these helpers only shape the API response for
// the UI.
//
// A module may drop an optional `<folder>/<name>/index.js` here to override or
// extend its UI (e.g. a custom board view). Such files are auto-discovered;
// there is no import line to add.

const overrideModules = import.meta.glob("./*/*/index.js", { eager: true });

const OVERRIDES = Object.fromEntries(
  Object.values(overrideModules)
    .map((module) => module.default)
    .filter((override) => override && override.id)
    .map((override) => [override.id, override])
);

/** API items -> UI agents, keyed by canonical id. API order is preserved. */
export function buildAgents(items) {
  return (items || []).map((item) => ({
    id: item.id,
    folder: item.folder,
    name: item.display,
    prompt: item.prompt || "",
    description: item.description || "",
    starterPrompts: item.starter_prompts || [],
    // An override wins, so a module can customise its own UI.
    ...(OVERRIDES[item.id] || {})
  }));
}

/** Group agents into [{ folder, label, agents }], in first-seen API order. */
export function groupByFolder(agentList) {
  const groups = [];
  const byFolder = new Map();

  for (const agent of agentList) {
    const folder = agent.folder || "other";

    if (!byFolder.has(folder)) {
      const group = {
        folder,
        label: folderLabel(folder),
        agents: []
      };
      byFolder.set(folder, group);
      groups.push(group);
    }

    byFolder.get(folder).agents.push(agent);
  }

  return groups;
}

function folderLabel(folder) {
  return folder.charAt(0).toUpperCase() + folder.slice(1);
}
