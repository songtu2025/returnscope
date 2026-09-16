import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";
import "./styles/desktop-layout.css";
import "./styles/visual-foundation.css";

const root = document.getElementById("root");
if (!root) throw new Error("缺少应用挂载节点 #root");

createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
