"""Investigation copilot: the LLM answers from structured case context only and must cite IDs that exist.

The LLM never sets a number. Its output is validated with Pydantic; any cited ID that is not in the supplied
context is rejected and reported, and responses containing banned wording are refused (guardrails)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from trace.application import queries
from trace.infrastructure.container import Container
from trace.intelligence.llm.client import LlmClient, LlmError

BANNED = ("guilty", "criminal", "fraudster", "confirmed fraud", "launderer")
MAX_EVIDENCE_TXNS = 8
MAX_LINKS = 150

SYSTEM = """You are the investigation copilot of TRACE, a financial-crime network decision-support tool.
Rules:
- Use ONLY the JSON context provided. Never invent transactions, amounts, entities, dates or evidence.
- Every claim must cite IDs that appear in the context (evidence ids like E01, transaction ids, link ids, entity ids).
- Never state or imply guilt. Use wording such as "requires human investigation". Anomaly is not criminality.
- Always consider legitimate explanations, contradictory evidence and data limitations from the context.
- If the context cannot answer the question, say so in `answer` and list what is missing in `data_limitations`.
- Do not state numeric scores that are not in the context.
Return ONLY a JSON object with this shape:
{"answer": str, "claims": [{"text": str, "evidence_ids": [str], "record_ids": [str]}],
 "legitimate_explanations": [str], "contradictory_evidence": [str], "data_limitations": [str],
 "suggested_next_steps": [str]}"""


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)


class CopilotAnswer(BaseModel):
    answer: str
    claims: list[Claim] = Field(default_factory=list)
    legitimate_explanations: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)


class CopilotError(RuntimeError):
    pass


def build_context(c: Container, case: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Structured context + the set of IDs the model is allowed to cite."""
    allowed: set[str] = set()
    ev = []
    for e in case["evidence"]:
        allowed.add(e["id"])
        txns = [str(t) for t in e["txn_ids"]]
        allowed.update(txns)
        ev.append({"id": e["id"], "finding_type": e["finding_type"], "source": e["source"],
                   "description": e["description"], "entities": e["entities"][:10],
                   "n_transactions": len(txns), "transaction_ids": txns[:MAX_EVIDENCE_TXNS],
                   "strength": e["strength"]})
    ents = []
    for x in case["entities"]:
        allowed.add(x["id"])
        ents.append({"id": x["id"], "type": x["type"], "role": x["role"], "derived": x["derived"]})
    g = queries.case_graph(c, case)
    links = []
    for ed in g["edges"]:
        if ed["type"] == "TRANSFERS_TO":
            continue
        if len(links) < MAX_LINKS:
            allowed.add(ed["id"])
            links.append({"id": ed["id"], "type": ed["type"], "from": ed["source"], "to": ed["target"],
                          "confidence": ed.get("confidence"), "evidence_ids": ed["evidence_ids"]})
    sb = case["score_breakdown"]
    ctx = {
        "case_id": case["id"], "tier": case["tier"], "priority_score": case["priority_score"],
        "status": case["status"], "summary": case["summary"],
        "score_note": "priority_score is a transparent weighted sum of deterministic signals, not a probability",
        "signals": [{"signal": s["signal"], "points": s["points"], "evidence_ids": s["evidence_ids"],
                     "source": s["source"]} for s in sb["signals"]],
        "penalties_from_legitimate_explanations": sb.get("penalties", []),
        "hypotheses": [{"id": h["id"], "label": h["label"], "support": h["support"],
                        "evidence_for": h.get("evidence_for", []), "evidence_against": h.get("evidence_against", [])}
                       for h in case["hypotheses"]],
        "alternative_explanations": [{k: a.get(k) for k in ("id", "label", "status", "fit", "reason", "evidence_ids")}
                                     for a in case["alternatives"]],
        "entities": ents, "relationship_links": links, "evidence": ev,
        "exposure": case["exposure"],
        "investigator_recorded_facts": case.get("adjudications", {}),
        "score_after_recorded_facts": case.get("adjudicated"),
        "data_limitations": [d["reason"] for d in case["capabilities_disabled"]],
        "suggested_next_steps": [n["label"] for n in case["next_steps"]],
    }
    return ctx, allowed


def ask(c: Container, case: dict[str, Any], question: str, llm: LlmClient, user: str) -> dict[str, Any]:
    q = question.strip()
    if not q:
        raise CopilotError("question is empty")
    ctx, allowed = build_context(c, case)
    prompt = json.dumps({"question": q, "context": ctx}, default=str)
    provider = llm.model or "unconfigured"
    try:
        obj, raw = llm.chat_json(SYSTEM, prompt)
    except LlmError as e:
        c.llm_audit.record(case["id"], "copilot", provider, q, None, f"error: {e}")
        raise
    try:
        ans = CopilotAnswer.model_validate(obj)
    except ValidationError as e:
        c.llm_audit.record(case["id"], "copilot", provider, q, raw, "invalid_schema")
        raise LlmError(f"LLM output failed schema validation: {e.errors()[:2]}") from e
    blob = json.dumps(ans.model_dump()).lower()
    if any(re.search(rf"\b{w}\b", blob) for w in BANNED):
        c.llm_audit.record(case["id"], "copilot", provider, q, raw, "guardrail_refused")
        raise LlmError("LLM output was refused by the guardrail (banned wording). Ask again or rephrase.")
    rejected: list[str] = []
    claims = []
    for cl in ans.claims:
        bad = [i for i in cl.evidence_ids + cl.record_ids if i not in allowed]
        rejected += bad
        cl.evidence_ids = [i for i in cl.evidence_ids if i in allowed]
        cl.record_ids = [i for i in cl.record_ids if i in allowed]
        claims.append({**cl.model_dump(), "cited": bool(cl.evidence_ids or cl.record_ids)})
    c.audit.append(case["id"], user, "copilot_query", {"question": q, "model": llm.model,
                                                      "rejected_citations": sorted(set(rejected))})
    c.llm_audit.record(case["id"], "copilot", provider, q, raw, "ok")
    out = ans.model_dump()
    out.update({"claims": claims, "rejected_citations": sorted(set(rejected)), "model": llm.model,
                "uncited_claims": sum(1 for x in claims if not x["cited"]),
                "disclaimer": "AI-generated explanation of the supplied evidence. Decision support only; a human "
                              "investigator makes the final decision."})
    return out
