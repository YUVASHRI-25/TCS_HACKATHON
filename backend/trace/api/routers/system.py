"""Health, dashboard, capabilities, entities and metrics."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query

from trace.api.schemas.models import CapabilityOut, Dashboard, EntityHit, Health, Metrics
from trace.application import queries
from trace.eval.metrics import compute
from trace.infrastructure.container import Container, get_container
from trace.ingestion.capabilities import capability_table
from trace.ingestion.mapping import load_mapping

router = APIRouter(prefix="/api", tags=["system"])


def _cap_rows(c: Container) -> list[dict]:
    s = c.settings
    p = s.path(s.trace_processed_dir) / "capabilities.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return [r.to_dict() for r in capability_table(load_mapping(s.path(s.trace_mapping_path)))]


@router.get("/health", response_model=Health)
def health(c: Container = Depends(get_container)):
    s = c.settings
    return {"status": "ok", "mapping_configured": not load_mapping(s.path(s.trace_mapping_path)).is_empty,
            "pipeline_run": c.cases.latest_run() is not None, "llm_provider": s.llm_provider,
            "graph_backend": s.graph_backend}


@router.get("/capabilities", response_model=list[CapabilityOut])
def capabilities(c: Container = Depends(get_container)):
    return queries._caps_with_status(c.cases.latest_run(), _cap_rows(c))


@router.get("/dashboard", response_model=Dashboard)
def dashboard(c: Container = Depends(get_container)):
    return queries.dashboard(c, _cap_rows(c))


@router.get("/metrics", response_model=Metrics)
def metrics(c: Container = Depends(get_container)):
    run = c.cases.latest_run()
    cases = [c.cases.get(r["id"]) for r in c.cases.all_rows()] if run else []
    return compute(cases, run, c.config.detectors["tiers"])


@router.get("/entities/search", response_model=list[EntityHit])
def search(q: str = Query(min_length=1), limit: int = Query(20, le=200), c: Container = Depends(get_container)):
    return c.graph.search(q, limit)


@router.get("/entities/{entity_id}/neighbors")
def neighbors(entity_id: str, hops: int = Query(1, ge=1, le=3), c: Container = Depends(get_container)) -> dict:
    res = c.graph.neighbors(entity_id, hops)
    if not res["nodes"]:
        raise HTTPException(404, f"entity {entity_id} not found")
    return res
