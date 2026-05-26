import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./style.css";

// StrictMode helps catch effect/cleanup mistakes in interactive widgets like
// upload preview, drag listeners, and Three.js mount lifecycle.
ReactDOM.createRoot(document.getElementById("app") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

