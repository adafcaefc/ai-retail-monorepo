// Frontend-only page registry.
//
// A page is a navigable screen that is NOT an agent: no backend module, no
// chat, no monitoring, no board payload. The agent registry next door shapes
// what `GET /api/html/agents` returns; nothing here talks to the backend at
// all, so these screens keep working when the API does not.
//
// Adding one is a folder, not an import: drop `<folder>/<name>/index.js` here
// exporting `{ id, folder, name, component }` and it is discovered on build.
// The folder becomes a sidebar group (see groupByFolder in agents/registry.js).
//
// A descriptor may also carry `order` (default 0) to place itself explicitly;
// see buildPages below.

const pageModules = import.meta.glob("./*/*/index.js", { eager: true });

/**
 * Static pages -> UI items shaped exactly like agents, so the sidebar, the
 * active-item state and the board swap in App need no branch for them. Sidebar
 * order is `order` (default 0), then glob path.
 */
export function buildPages() {
  return Object.keys(pageModules)
    .sort()
    .map((path) => pageModules[path].default)
    .filter((page) => page && page.id && page.component)
    // Glob-path order is the default, but a page can opt out without being
    // renamed. Array#sort is stable, so pages sharing an order keep path
    // order. Data Source uses this: it is the only page that needs the
    // backend, so it must not win the sort and become agentIds[0].
    .sort((first, second) => (first.order ?? 0) - (second.order ?? 0))
    .map((page) => ({
      id: page.id,
      folder: page.folder,
      name: page.name,
      // App reads this to drop the agent chrome (toolbar, chat panel).
      isPage: true,
      // Keeps MonitoringProvider from polling an id no backend knows about.
      dashboardOnly: true,
      prompt: "",
      description: "",
      starterPrompts: [],
      dashboardComponent: page.component
    }));
}
