import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";
import { AgentsProvider } from "./agents/AgentsProvider.jsx";
import { MonitoringProvider } from "./monitoring/MonitoringProvider.jsx";
import "./styles.css";

// AgentsProvider is outermost: monitoring runs per agent, so it waits for the
// module list the backend serves.
ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <AgentsProvider>
      <MonitoringProvider>
        <App />
      </MonitoringProvider>
    </AgentsProvider>
  </React.StrictMode>
);