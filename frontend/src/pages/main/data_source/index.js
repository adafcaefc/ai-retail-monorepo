// Hidden from the frontend sidebar: no default export means
// frontend/src/pages/registry.js's glob discovery skips this folder.
// See docs/DISABLED_FEATURES.md to re-enable.
//
// import DataSource from "./DataSource.jsx";
//
// export default {
//   id: "main.data_source",
//   folder: "main",
//   name: "Data Source",
//   component: DataSource,
//   // Sorts after the backend-free pages. "data_source" would otherwise win the
//   // glob sort and become the app's default screen (App.jsx picks agentIds[0]),
//   // and this is the one page that cannot render during an API outage.
//   order: 1,
// };
