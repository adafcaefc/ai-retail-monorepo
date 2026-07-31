import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";
import { AgentsProvider } from "./agents/AgentsProvider.jsx";
import { LanguageProvider } from "./LanguageProvider.jsx";
import { MonitoringProvider } from "./monitoring/MonitoringProvider.jsx";
import "./styles.css";

// LanguageProvider is outermost: it holds no data of its own, and everything
// below it renders wording (QC-058). AgentsProvider comes next because
// monitoring runs per agent, so it waits for the module list the backend
// serves.
ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <LanguageProvider>
      <AgentsProvider>
        <MonitoringProvider>
          <App />
        </MonitoringProvider>
      </AgentsProvider>
    </LanguageProvider>
  </React.StrictMode>
);