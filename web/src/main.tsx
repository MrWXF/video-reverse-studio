import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/app-react.css";
import "./styles/studio-base.css";
import "./styles/studio-shell.css";
import "./styles/studio-reverse.css";
import "./styles/studio-projects.css";
import "./styles/studio-detail.css";
import "./styles/studio-generate.css";
import "./styles/studio-prompt.css";
import "./styles/studio-quality.css";
import "./styles/studio-responsive.css";
import "./styles/studio-simple.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("React root element was not found");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
