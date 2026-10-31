// Typed API client over the GENERATED OpenAPI schema (src/api/schema.ts, from scripts/export_types.sh).
// There is no mock client: every call goes to the running TRACE backend.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

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
