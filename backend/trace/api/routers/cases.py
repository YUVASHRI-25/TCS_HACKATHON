"""Case endpoints. Read-only except review/adjudicate, which require notes and write audit entries."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from trace.api.deps import current_user
from trace.api.schemas.models import (AdjudicateIn, AuditOut, CaseFlow, CaseGraph, CaseOut, CaseSummary, CreateCaseIn,
                                      EvidenceDetail, FactOut, NextBestAction, ReviewIn, ReviewOut, WhatIfIn, WhatIfOut)
from pydantic import BaseModel, Field

from trace.application import copilot, manual_case
from trace.application import queries
from trace.application.dossier import build_dossier
from trace.application.review import ReviewError, adjudicate, nba, review, whatif
from trace.domain.scoring.score import ScoringConfig
from trace.infrastructure.container import Container, get_container
from trace.intelligence.llm.client import LlmError

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(current_user)])


def _case(case_id: str, c: Container) -> dict[str, Any]:
    case = c.cases.get(case_id)
    if case is None:
        raise HTTPException(404, f"case {case_id} not found")
    return case


def _facts(c: Container) -> dict[str, Any]:
    return c.config.catalogues.get("whatif_facts") or {}


def _scfg(c: Container) -> ScoringConfig:
    return ScoringConfig.from_dict(c.config.detectors)


def _summary(case: dict[str, Any]) -> dict[str, Any]:
    return {"id": case["id"], "tier": case["tier"], "priority_score": case["priority_score"], "status": case["status"],
            "summary": case["summary"], "n_members": sum(1 for e in case["entities"] if e["role"] == "member"),
            "exposure_total": case["exposure"]["total"], "finding_types": case["finding_types"],
            "origin": case.get("origin", "pipeline"), "created_by": case.get("created_by")}


@router.post("", response_model=CaseOut)
def create_case(body: CreateCaseIn, user: dict = Depends(current_user), c: Container = Depends(get_container)):
    try:
        return manual_case.create(c, body.accounts, body.title, body.notes, user["username"])
    except manual_case.ManualCaseError as e:
        raise HTTPException(422, str(e)) from e


@router.get("", response_model=list[CaseSummary])
def list_cases(tier: str | None = None, status: str | None = None, q: str | None = None,
               limit: int = Query(500, le=5000), offset: int = 0, c: Container = Depends(get_container)):
    return c.cases.list(tier=tier, status=status, q=q, limit=limit, offset=offset)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str, c: Container = Depends(get_container)):
    return _case(case_id, c)


@router.get("/{case_id}/graph", response_model=CaseGraph)
def get_graph(case_id: str, c: Container = Depends(get_container)):
    return queries.case_graph(c, _case(case_id, c))


@router.get("/{case_id}/flow", response_model=CaseFlow)
def get_flow(case_id: str, c: Container = Depends(get_container)):
    return queries.case_flow(c, _case(case_id, c))


@router.get("/{case_id}/evidence/{eid}", response_model=EvidenceDetail)
def get_evidence(case_id: str, eid: str, c: Container = Depends(get_container)):
    ev = queries.evidence_detail(c, _case(case_id, c), eid)
    if ev is None:
        raise HTTPException(404, f"evidence {eid} not in case {case_id}")
    return ev


@router.post("/{case_id}/review", response_model=ReviewOut)
def post_review(case_id: str, body: ReviewIn, user: dict = Depends(current_user), c: Container = Depends(get_container)):
    try:
        case, entry = review(_case(case_id, c), body.action, user["username"], body.notes, c.audit, body.resolution)
    except ReviewError as e:
        raise HTTPException(422, str(e)) from e
    c.cases.save(case)
    return {"case": _summary(case), "audit_entry": entry}


@router.get("/{case_id}/audit", response_model=AuditOut)
def get_audit(case_id: str, c: Container = Depends(get_container)):
    _case(case_id, c)
    v = c.audit.verify_detail()
    return {"entries": c.audit.chain(case_id), "chain_valid": v["valid"], "chain_entries": v["entries"],
            "broken_at_seq": v["broken_at_seq"]}


@router.get("/{case_id}/dossier.pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
def get_dossier(case_id: str, c: Container = Depends(get_container)):
    case = _case(case_id, c)
    pdf = build_dossier(case, queries.case_graph(c, case), c.audit.chain(case_id), c.audit.verify())
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="TRACE-{case_id}-dossier.pdf"'})


@router.get("/{case_id}/facts", response_model=list[FactOut])
def get_facts(case_id: str, c: Container = Depends(get_container)):
    case = _case(case_id, c)
    adj = case.get("adjudications", {})
    return [{"id": k, "label": v.get("label", k), "state": adj.get(k, "unknown"), "effort_minutes": v.get("effort_minutes")}
            for k, v in _facts(c).items()]


@router.post("/{case_id}/whatif", response_model=WhatIfOut)
def post_whatif(case_id: str, body: WhatIfIn, c: Container = Depends(get_container)):
    try:
        return whatif(_case(case_id, c), body.adjudications, _facts(c), _scfg(c))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


@router.post("/{case_id}/adjudicate", response_model=CaseOut)
def post_adjudicate(case_id: str, body: AdjudicateIn, user: dict = Depends(current_user),
                    c: Container = Depends(get_container)):
    try:
        case, _ = adjudicate(_case(case_id, c), body.fact, body.state, user["username"], body.note, _facts(c), _scfg(c),
                             c.audit)
    except ReviewError as e:
        raise HTTPException(422, str(e)) from e
    c.cases.save(case)
    return case


@router.get("/{case_id}/next-best-actions", response_model=list[NextBestAction])
def get_nba(case_id: str, c: Container = Depends(get_container)):
    return nba(_case(case_id, c), _facts(c), _scfg(c))


@router.get("/{case_id}/llm-audit")
def get_llm_audit(case_id: str, c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    _case(case_id, c)
    return c.llm_audit.for_case(case_id)


class CopilotIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


@router.post("/{case_id}/copilot")
def ask_copilot(case_id: str, body: CopilotIn, user: dict = Depends(current_user),
                c: Container = Depends(get_container)) -> dict[str, Any]:
    """LLM answer grounded in this case's evidence. 503 with the real reason when the LLM is unavailable."""
    case = _case(case_id, c)
    try:
        return copilot.ask(c, case, body.question, c.llm, user["username"])
    except LlmError as e:
        raise HTTPException(503, f"LLM unavailable: {e}") from e
    except copilot.CopilotError as e:
        raise HTTPException(422, str(e)) from e
