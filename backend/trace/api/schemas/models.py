"""API schemas. These drive /openapi.json, from which the frontend types are GENERATED."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Tier = Literal["HIGH", "MEDIUM", "LOW"]


class Health(BaseModel):
    status: str
    mapping_configured: bool
    pipeline_run: bool
    llm_provider: str
    graph_backend: str


class CapabilityOut(BaseModel):
    id: str
    kind: str
    label: str
    enabled: bool
    deterministic: bool
    reason: str
    uses_derived: list[str]
    run_status: str | None = None
    findings: int | None = None
    notes: list[str] = []


class EvidenceOut(BaseModel):
    id: str
    finding_type: str
    description: str
    source: Literal["deterministic", "model"]
    entities: list[str]
    txn_ids: list[str]
    source_rows: list[dict[str, Any]]
    n_source_rows: int
    ts_min: str | None
    ts_max: str | None
    cypher_used: str
    strength: float
    details: dict[str, Any]


class EvidenceDetail(EvidenceOut):
    raw_rows: list[dict[str, Any]]


class HypothesisOut(BaseModel):
    id: str
    label: str
    description: str
    support: float
    evidence_for: list[str]
    evidence_against: list[str]
    missing_signals: list[str]


class AlternativeOut(BaseModel):
    id: str
    label: str
    status: Literal["evaluated", "cannot_evaluate", "not_applicable"]
    fit: float | None
    reason: str
    evidence_ids: list[str]
    next_step: str | None


class SignalOut(BaseModel):
    signal: str
    weight: float
    strength: float
    points: float
    evidence_ids: list[str]
    source: str


class PenaltyOut(BaseModel):
    alternative: str
    fit: float
    weight: float
    points: float


class ScoreBreakdownOut(BaseModel):
    signals: list[SignalOut]
    ml_signals: list[SignalOut]
    ml_raw_total: float
    ml_capped_total: float
    bonus: float
    penalties: list[PenaltyOut]
    total: float
    tier: Tier


class CounterfactualOut(BaseModel):
    removed: list[str]
    score: float
    tier: Tier
    still_opens_case: bool
    lowers_tier: bool
    minimal_tier_change: bool


class NextStepOut(BaseModel):
    id: str
    label: str
    description: str
    reason: str
    related_hypotheses: list[str]


class EntityOut(BaseModel):
    id: str
    type: str
    raw_id: str
    role: Literal["member", "related"]
    derived: bool


class WhySuspicious(BaseModel):
    signal: str
    label: str
    evidence_ids: list[str]


class ExplanationConsidered(BaseModel):
    id: str
    label: str
    status: str
    fit: float | None
    reason: str


class KeyQuestions(BaseModel):
    """The brief's four questions, answered for every flagged network."""
    why_suspicious: list[WhySuspicious]
    evidence: list[str]
    legitimate_explanations: list[ExplanationConsidered]
    next_steps: list[str]


class Exposure(BaseModel):
    suspicious_txns: int
    total: float
    by_currency: dict[str, float]
    currency_known: bool = False
    max_chain_throughput: float
    note: str | None = None


class Adjudicated(BaseModel):
    score: float
    tier: Tier
    changes: list[dict[str, Any]]
    note: str


class DisabledCapability(BaseModel):
    id: str
    reason: str


class CaseSummary(BaseModel):
    id: str
    tier: Tier
    priority_score: float
    status: str
    summary: str
    n_members: int
    exposure_total: float
    finding_types: list[str]


class CaseOut(BaseModel):
    id: str
    summary: str
    tier: Tier
    priority_score: float
    status: str
    entities: list[EntityOut]
    hypotheses: list[HypothesisOut]
    alternatives: list[AlternativeOut]
    evidence: list[EvidenceOut]
    score_breakdown: ScoreBreakdownOut
    counterfactuals: list[CounterfactualOut]
    next_steps: list[NextStepOut]
    exposure: Exposure
    key_questions: KeyQuestions
    capabilities_used: list[str]
    capabilities_disabled: list[DisabledCapability]
    guardrail_notice: str
    finding_types: list[str]
    adjudications: dict[str, str] = {}
    adjudicated: Adjudicated | None = None


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    role: Literal["member", "related", "context"]
    derived: bool
    risk: float
    suspicious: bool
    evidence_ids: list[str]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    suspicious: bool
    evidence_ids: list[str]
    txn_id: str | None = None
    ts: str | None = None
    amount: float | None = None
    confidence: float | None = None


class CaseGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False


class FlowNode(BaseModel):
    id: str
    label: str
    kind: Literal["member", "external_sources", "external_destinations"]


class FlowLink(BaseModel):
    source: str
    target: str
    amount: float
    n_txns: int
    suspicious_amount: float


class CaseFlow(BaseModel):
    nodes: list[FlowNode]
    links: list[FlowLink]
    currency_note: str | None


class ReviewIn(BaseModel):
    action: Literal["confirm_for_investigation", "reject_false_positive", "request_more_info"]
    reviewer: str = Field(min_length=1)
    notes: str = Field(min_length=1)


class AuditEntry(BaseModel):
    seq: int
    case_id: str
    ts: str
    actor: str
    action: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class AuditOut(BaseModel):
    entries: list[AuditEntry]
    chain_valid: bool
    chain_entries: int
    broken_at_seq: int | None


class ReviewOut(BaseModel):
    case: CaseSummary
    audit_entry: AuditEntry


class WhatIfIn(BaseModel):
    adjudications: dict[str, Literal["unknown", "confirmed", "refuted"]]


class WhatIfOut(BaseModel):
    simulation: bool
    recorded: bool
    label: str
    baseline: dict[str, Any]
    score: float
    tier: Tier
    still_opens_case: bool
    changes: list[dict[str, Any]]
    breakdown: ScoreBreakdownOut


class AdjudicateIn(BaseModel):
    fact: str
    state: Literal["unknown", "confirmed", "refuted"]
    reviewer: str = Field(min_length=1)
    note: str = Field(min_length=1)


class NextBestAction(BaseModel):
    fact: str
    label: str
    outcomes: dict[str, dict[str, Any]]
    expected_shift: float
    effort_minutes: float | None
    effort_is_assumption: bool
    shift_per_minute: float | None
    rationale: str


class FactOut(BaseModel):
    id: str
    label: str
    state: Literal["unknown", "confirmed", "refuted"]
    effort_minutes: float | None


class EntityHit(BaseModel):
    id: str
    type: str | None
    derived: bool


class Dashboard(BaseModel):
    pipeline_run: bool
    run_at: str | None
    kpis: dict[str, Any]
    tiers: dict[str, int]
    score_histogram: list[dict[str, Any]]
    capabilities: list[CapabilityOut]
    grouping: dict[str, Any] | None
    warnings: list[str]
    data_statement: str


class Metrics(BaseModel):
    computed: bool
    measures: list[dict[str, Any]]
    label_report: dict[str, Any] | None
    does_not_prove: list[str]
