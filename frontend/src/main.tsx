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
import { DatasetsPage } from "@/pages/Datasets";
import { ActivityPage, SettingsPage, UsersPage } from "@/pages/Admin";
import { SystemPage } from "@/pages/SystemHealth";
import { LoginPage } from "@/pages/Login";
import { useAuth } from "@/store/auth";
import { EmptyState } from "@/components/ui/primitives";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

function App() {
  const user = useAuth((s) => s.user);
  if (!user) return <LoginPage />;
  const admin = user.role === "admin";
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/metrics" element={<MetricsPage />} />
        <Route path="/live" element={<LiveStreamPage />} />
        {admin && <Route path="/admin/system" element={<SystemPage />} />}
        {admin && <Route path="/admin/users" element={<UsersPage />} />}
        {admin && <Route path="/admin/settings" element={<SettingsPage />} />}
        {admin && <Route path="/admin/activity" element={<ActivityPage />} />}
        <Route path="*" element={<EmptyState title="Page not found or not available for your role" />} />
      </Routes>
    </Shell>
  );
}

// Sign-out clears all cached data so the next user never sees the previous user's results.
useAuth.subscribe((s, prev) => { if (prev.user && !s.user) queryClient.clear(); });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
