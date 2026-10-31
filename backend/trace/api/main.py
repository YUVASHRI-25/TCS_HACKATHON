"""FastAPI app. Routers are added in Phase 3."""

from __future__ import annotations

from fastapi import FastAPI

from trace.infrastructure.settings import get_settings
from trace.ingestion.capabilities import capability_table
from trace.ingestion.mapping import load_mapping

app = FastAPI(title="TRACE API", description="Decision support only. A human investigator makes the final decision.")


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    cfg = load_mapping(s.path(s.trace_mapping_path))
    return {"status": "ok", "mapping_configured": not cfg.is_empty, "llm_provider": s.llm_provider,
            "graph_backend": s.graph_backend}


@app.get("/api/capabilities")
def capabilities() -> list[dict]:
    s = get_settings()
    return [c.to_dict() for c in capability_table(load_mapping(s.path(s.trace_mapping_path)))]
