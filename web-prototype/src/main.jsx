import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";
import "./styles/classification-standards.css";
import "./styles/insight-generation.css";
import "./styles/task-flow.css";
import "./styles/desktop-layout.css";
import "./styles/analysis-dashboards.css";
import "./styles/classification-results.css";
import "./styles/operations.css";
import "./styles/visual-foundation.css";
import "./styles/return-insights.css";
import "./styles/ai-insight-reports.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
