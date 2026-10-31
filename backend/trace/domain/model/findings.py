"""Findings and case structures. Pure data classes; no framework imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DETERMINISTIC = "deterministic"
MODEL = "model"


def node_id(kind: str, raw_id: Any) -> str:
    return f"{kind}:{raw_id}"


def split_node_id(nid: str) -> tuple[str, str]:
    kind, _, raw = nid.partition(":")
    return kind, raw


@dataclass
class Finding:
    """One detector hit.

    subjects: the entities the pattern is ABOUT (they form networks).
    related:  counterparties/context entities (shown, but do not glue networks together).
    """

    type: str
    subjects: tuple[str, ...]
    txn_ids: tuple[str, ...]
    strength: float
    details: dict[str, Any]
    cypher_used: str
    source: str = DETERMINISTIC
    related: tuple[str, ...] = ()
    detector: str = ""

    def __post_init__(self) -> None:
        self.strength = float(min(1.0, max(0.0, self.strength)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Link:
    """A possible relationship between two entities. NEVER a merge."""

    a: str
    b: str
    kind: str  # possible_same_entity | possible_related
    confidence: float
    reasons: list[str]
    source_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Evidence:
    id: str
    finding_type: str
    description: str
    source: str
    entities: list[str]
    txn_ids: list[str]
    source_rows: list[dict[str, Any]]
    n_source_rows: int
    ts_min: str | None
    ts_max: str | None
    cypher_used: str
    strength: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Hypothesis:
    id: str
    label: str
    description: str
    support: float
    evidence_for: list[str]
    evidence_against: list[str]
    missing_signals: list[str]


@dataclass
class AlternativeResult:
    id: str
    label: str
    status: str  # evaluated | cannot_evaluate | not_applicable
    fit: float | None
    reason: str
    evidence_ids: list[str] = field(default_factory=list)
    next_step: str | None = None


@dataclass
class SignalContribution:
    signal: str
    weight: float
    strength: float
    points: float
    evidence_ids: list[str]
    source: str = DETERMINISTIC


@dataclass
class PenaltyContribution:
    alternative: str
    fit: float
    weight: float
    points: float  # negative


@dataclass
class ScoreBreakdown:
    signals: list[SignalContribution]
    ml_signals: list[SignalContribution]
    ml_raw_total: float
    ml_capped_total: float
    bonus: float
    penalties: list[PenaltyContribution]
    total: float
    tier: str


@dataclass
class Counterfactual:
    removed: list[str]
    score: float
    tier: str
    still_opens_case: bool
    lowers_tier: bool
    minimal_tier_change: bool = False


@dataclass
class NextStep:
    id: str
    label: str
    description: str
    reason: str
    related_hypotheses: list[str] = field(default_factory=list)


@dataclass
class Case:
    id: str
    summary: str
    tier: str
    priority_score: float
    status: str
    entities: list[dict[str, Any]]
    hypotheses: list[Hypothesis]
    alternatives: list[AlternativeResult]
    evidence: list[Evidence]
    score_breakdown: ScoreBreakdown
    counterfactuals: list[Counterfactual]
    next_steps: list[NextStep]
    exposure: dict[str, Any]
    key_questions: dict[str, Any]
    capabilities_used: list[str]
    capabilities_disabled: list[dict[str, str]]
    guardrail_notice: str
    finding_types: list[str]
    adjudications: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
