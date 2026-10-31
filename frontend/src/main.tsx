import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./styles/index.css";
import { Shell } from "@/components/layout/Shell";
import { DashboardPage } from "@/pages/Dashboard";
import { CasesPage } from "@/pages/Cases";
import { CaseWorkspacePage } from "@/pages/CaseWorkspace";
import { ExplorerPage } from "@/pages/Explorer";
import { MetricsPage } from "@/pages/Metrics";
import { LiveStreamPage } from "@/pages/LiveStream";
import { EmptyState } from "@/components/ui/primitives";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
            <Route path="/explorer" element={<ExplorerPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/live" element={<LiveStreamPage />} />
            <Route path="*" element={<EmptyState title="Page not found" />} />
          </Routes>
        </Shell>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
