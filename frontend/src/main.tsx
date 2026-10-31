import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/index.css";

// Phase 4 builds the console against the running API. Until then this renders only the guardrail banner.
function App() {
  return (
    <div className="min-h-screen bg-slate-950 font-sans text-slate-200">
      <div role="note" className="bg-amber-500/10 px-4 py-2 text-sm text-amber-300">
        Decision support only. A human investigator makes the final decision.
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
