// Typed API client over the GENERATED OpenAPI schema (src/api/schema.ts, from scripts/export_types.sh).
// There is no mock client: every call goes to the running TRACE backend.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { useAuth } from "@/store/auth";

export const api = createClient<paths>({ baseUrl: "" });

// Attach the session token; a 401 ends the session and returns to sign-in.
api.use({
  onRequest({ request }) {
    const tok = useAuth.getState().token;
    if (tok) request.headers.set("Authorization", `Bearer ${tok}`);
    return request;
  },
  onResponse({ response, request }) {
    if (response.status === 401 && !request.url.includes("/api/auth/")) useAuth.getState().signOut();
    return response;
  },
});

/** Authenticated download (e.g. the dossier PDF) without putting the token in a URL. */
export async function download(url: string, filename: string) {
  const tok = useAuth.getState().token;
  const res = await fetch(url, { headers: tok ? { Authorization: `Bearer ${tok}` } : {} });
  if (!res.ok) throw new ApiError(res.statusText || "Download failed", res.status);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export type Schemas = components["schemas"];
export type CaseOut = Schemas["CaseOut"];
export type CaseSummary = Schemas["CaseSummary"];
export type EvidenceOut = Schemas["EvidenceOut"];
export type EvidenceDetail = Schemas["EvidenceDetail"];
export type CaseGraph = Schemas["CaseGraph"];
export type GraphNode = Schemas["GraphNode"];
export type GraphEdge = Schemas["GraphEdge"];
export type CaseFlow = Schemas["CaseFlow"];
export type Dashboard = Schemas["Dashboard"];
export type CapabilityOut = Schemas["CapabilityOut"];
export type AuditOut = Schemas["AuditOut"];
export type WhatIfOut = Schemas["WhatIfOut"];
export type NextBestAction = Schemas["NextBestAction"];
export type FactOut = Schemas["FactOut"];
export type Metrics = Schemas["Metrics"];
export type ChatMessage = Schemas["ChatMessageOut"];
export type ChatAnswer = Schemas["ChatAnswer"];
export type Tier = CaseOut["tier"];
export type FactState = FactOut["state"];

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

/** Unwrap an openapi-fetch result, turning HTTP errors into thrown ApiErrors for TanStack Query. */
export function unwrap<T>(res: { data?: T; error?: unknown; response: Response }): T {
  if (res.error !== undefined || res.data === undefined) {
    const detail =
      typeof res.error === "object" && res.error && "detail" in res.error
        ? String((res.error as { detail: unknown }).detail)
        : res.response.statusText || "Request failed";
    throw new ApiError(detail, res.response.status);
  }
  return res.data;
}

/** Authenticated JSON call for endpoints whose payload is not described in the generated OpenAPI types. */
export async function jsonCall<T = unknown>(method: "GET" | "POST", url: string, body?: unknown): Promise<T> {
  const tok = useAuth.getState().token;
  const res = await fetch(url, {
    method,
    headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) useAuth.getState().signOut();
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(data && typeof data.detail === "string" ? data.detail : res.statusText || "Request failed", res.status);
  return data as T;
}
