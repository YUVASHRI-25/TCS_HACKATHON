import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type FactState } from "@/api/client";

export const qk = {
  health: ["health"] as const,
  dashboard: ["dashboard"] as const,
  metrics: ["metrics"] as const,
  cases: (f: CaseFilters) => ["cases", f] as const,
  case: (id: string) => ["case", id] as const,
  graph: (id: string) => ["case", id, "graph"] as const,
  flow: (id: string) => ["case", id, "flow"] as const,
  evidence: (id: string, eid: string) => ["case", id, "evidence", eid] as const,
  audit: (id: string) => ["case", id, "audit"] as const,
  facts: (id: string) => ["case", id, "facts"] as const,
  nba: (id: string) => ["case", id, "nba"] as const,
  search: (q: string) => ["search", q] as const,
  neighbors: (id: string, hops: number) => ["neighbors", id, hops] as const,
};

export interface CaseFilters {
  tier?: string;
  status?: string;
  q?: string;
}

export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: async () => unwrap(await api.GET("/api/health")) });

export const useDashboard = () =>
  useQuery({ queryKey: qk.dashboard, queryFn: async () => unwrap(await api.GET("/api/dashboard")) });

export const useMetrics = () =>
  useQuery({ queryKey: qk.metrics, queryFn: async () => unwrap(await api.GET("/api/metrics")) });

export const useCases = (f: CaseFilters) =>
  useQuery({
    queryKey: qk.cases(f),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/cases", {
          params: { query: { tier: f.tier || undefined, status: f.status || undefined, q: f.q || undefined } },
        }),
      ),
  });

export const useCase = (id: string) =>
  useQuery({
    queryKey: qk.case(id),
    queryFn: async () => unwrap(await api.GET("/api/cases/{case_id}", { params: { path: { case_id: id } } })),
  });

export const useCaseGraph = (id: string) =>
  useQuery({
    queryKey: qk.graph(id),
    queryFn: async () => unwrap(await api.GET("/api/cases/{case_id}/graph", { params: { path: { case_id: id } } })),
  });

export const useCaseFlow = (id: string) =>
  useQuery({
    queryKey: qk.flow(id),
    queryFn: async () => unwrap(await api.GET("/api/cases/{case_id}/flow", { params: { path: { case_id: id } } })),
  });

export const useEvidence = (id: string, eid: string | null) =>
  useQuery({
    queryKey: qk.evidence(id, eid ?? ""),
    enabled: !!eid,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/cases/{case_id}/evidence/{eid}", { params: { path: { case_id: id, eid: eid ?? "" } } }),
      ),
  });

export const useAudit = (id: string) =>
  useQuery({
    queryKey: qk.audit(id),
    queryFn: async () => unwrap(await api.GET("/api/cases/{case_id}/audit", { params: { path: { case_id: id } } })),
  });

export const useFacts = (id: string) =>
  useQuery({
    queryKey: qk.facts(id),
    queryFn: async () => unwrap(await api.GET("/api/cases/{case_id}/facts", { params: { path: { case_id: id } } })),
  });

export const useNextBestActions = (id: string) =>
  useQuery({
    queryKey: qk.nba(id),
    queryFn: async () =>
      unwrap(await api.GET("/api/cases/{case_id}/next-best-actions", { params: { path: { case_id: id } } })),
  });

export const useEntitySearch = (q: string) =>
  useQuery({
    queryKey: qk.search(q),
    enabled: q.trim().length > 0,
    queryFn: async () => unwrap(await api.GET("/api/entities/search", { params: { query: { q, limit: 20 } } })),
  });

export const useNeighbors = (id: string | null, hops: number) =>
  useQuery({
    queryKey: qk.neighbors(id ?? "", hops),
    enabled: !!id,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/entities/{entity_id}/neighbors", {
          params: { path: { entity_id: id ?? "" }, query: { hops } },
        }),
      ),
  });

export function useWhatIf(id: string) {
  return useMutation({
    mutationFn: async (adjudications: Record<string, FactState>) =>
      unwrap(
        await api.POST("/api/cases/{case_id}/whatif", { params: { path: { case_id: id } }, body: { adjudications } }),
      ),
  });
}

export function useReview(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      action: "confirm_for_investigation" | "reject_false_positive" | "request_more_info";
      reviewer: string;
      notes: string;
    }) => unwrap(await api.POST("/api/cases/{case_id}/review", { params: { path: { case_id: id } }, body })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["case", id] });
      void qc.invalidateQueries({ queryKey: ["cases"] });
      void qc.invalidateQueries({ queryKey: qk.dashboard });
    },
  });
}

export function useAdjudicate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { fact: string; state: FactState; reviewer: string; note: string }) =>
      unwrap(await api.POST("/api/cases/{case_id}/adjudicate", { params: { path: { case_id: id } }, body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["case", id] }),
  });
}
