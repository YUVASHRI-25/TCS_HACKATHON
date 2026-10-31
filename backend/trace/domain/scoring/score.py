"""Explainable priority score (0-100). Deterministic. NOT a probability of fraud.

total = sum(weight[signal] x strength[signal])            deterministic risk signals
      + bonus_per_extra_signal_type x max(0, n_types - 2)
      + min(ml_cap, sum(ml_weight x strength))             model signals, capped
      - sum(penalty[alternative] x fit[alternative])       evaluated alternatives only
clipped to [0, 100]. Tier from configured cut-offs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import combinations
from typing import Any

from trace.domain.model.findings import (MODEL, Counterfactual, PenaltyContribution, ScoreBreakdown,
                                         SignalContribution)


@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]
    ml_weights: dict[str, float]
    penalties: dict[str, float]
    bonus_per_extra_signal_type: float
    ml_cap: float
    min_types: int
    tier_high: float
    tier_medium: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScoringConfig:
        cr = d["case_rules"]
        return cls(weights=dict(d.get("weights") or {}), ml_weights=dict(d.get("ml_weights") or {}),
                   penalties=dict(d.get("penalties") or {}), bonus_per_extra_signal_type=cr["bonus_per_extra_signal_type"],
                   ml_cap=cr["ml_cap"], min_types=cr["min_deterministic_finding_types"],
                   tier_high=d["tiers"]["high"], tier_medium=d["tiers"]["medium"])


@dataclass(frozen=True)
class SignalInput:
    strength: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScoreInputs:
    signals: dict[str, SignalInput]                       # deterministic risk signal -> max strength
    ml_signals: dict[str, SignalInput] = field(default_factory=dict)
    alternative_fits: dict[str, float] = field(default_factory=dict)  # evaluated alternatives only

    def without(self, removed: set[str]) -> ScoreInputs:
        return replace(self, signals={k: v for k, v in self.signals.items() if k not in removed},
                       ml_signals={k: v for k, v in self.ml_signals.items() if k not in removed})


def tier_of(score: float, cfg: ScoringConfig) -> str:
    if score >= cfg.tier_high:
        return "HIGH"
    if score >= cfg.tier_medium:
        return "MEDIUM"
    return "LOW"


TIER_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def score(inputs: ScoreInputs, cfg: ScoringConfig) -> ScoreBreakdown:
    sig = []
    for name, s in sorted(inputs.signals.items()):
        if name not in cfg.weights:
            raise KeyError(f"no weight configured for signal {name!r} (config/detectors.yaml weights)")
        w = float(cfg.weights[name])
        sig.append(SignalContribution(name, w, s.strength, round(w * s.strength, 2), list(s.evidence_ids)))
    ml = []
    for name, s in sorted(inputs.ml_signals.items()):
        w = float(cfg.ml_weights.get(name, 0))
        ml.append(SignalContribution(name, w, s.strength, round(w * s.strength, 2), list(s.evidence_ids), MODEL))
    ml_raw = sum(m.points for m in ml)
    ml_capped = min(cfg.ml_cap, ml_raw)
    bonus = cfg.bonus_per_extra_signal_type * max(0, len(sig) - 2)
    pens = [PenaltyContribution(a, fit, float(cfg.penalties.get(a, 0)), -round(fit * float(cfg.penalties.get(a, 0)), 2))
            for a, fit in sorted(inputs.alternative_fits.items()) if fit and cfg.penalties.get(a)]
    total = sum(s.points for s in sig) + bonus + ml_capped + sum(p.points for p in pens)
    total = round(max(0.0, min(100.0, total)), 2)
    return ScoreBreakdown(signals=sig, ml_signals=ml, ml_raw_total=round(ml_raw, 2), ml_capped_total=round(ml_capped, 2),
                          bonus=bonus, penalties=pens, total=total, tier=tier_of(total, cfg))


def opens_case(inputs: ScoreInputs, cfg: ScoringConfig) -> bool:
    """A case needs >= min_types independent deterministic signal types. ML never counts."""
    return len(inputs.signals) >= cfg.min_types


def counterfactuals(inputs: ScoreInputs, cfg: ScoringConfig, max_set: int = 4) -> list[Counterfactual]:
    base = score(inputs, cfg)
    names = sorted(inputs.signals) + sorted(inputs.ml_signals)
    out = []
    for n in names:
        alt = inputs.without({n})
        s = score(alt, cfg)
        out.append(Counterfactual([n], s.total, s.tier, opens_case(alt, cfg), TIER_RANK[s.tier] < TIER_RANK[base.tier]))
    if base.tier != "LOW":
        for k in range(1, min(max_set, len(names)) + 1):
            best = None
            for combo in combinations(names, k):
                alt = inputs.without(set(combo))
                s = score(alt, cfg)
                if TIER_RANK[s.tier] < TIER_RANK[base.tier] and (best is None or s.total < best[1].total):
                    best = (combo, s, opens_case(alt, cfg))
            if best:
                combo, s, still = best
                out.append(Counterfactual(list(combo), s.total, s.tier, still, True, minimal_tier_change=True))
                break
    return out
