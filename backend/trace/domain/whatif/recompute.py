"""What-if: recompute a case's score under investigator-supplied facts. Pure; never persists.

Facts come from catalogues.whatif_facts. Each fact state is unknown | confirmed | refuted, and each
outcome lists effects: remove_signal [..] and/or set_alternative_fit {ALT: fit}.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from trace.domain.scoring.score import ScoreInputs, ScoringConfig, opens_case, score

STATES = ("unknown", "confirmed", "refuted")


def apply_facts(inputs: ScoreInputs, adjudications: dict[str, str], facts: dict[str, dict[str, Any]]
                ) -> tuple[ScoreInputs, list[dict[str, Any]]]:
    changes: list[dict[str, Any]] = []
    removed: set[str] = set()
    fits = dict(inputs.alternative_fits)
    for fact, state in sorted(adjudications.items()):
        if state not in STATES:
            raise ValueError(f"{fact}: state must be one of {STATES}")
        if fact not in facts:
            raise KeyError(f"unknown fact {fact!r}")
        if state == "unknown":
            continue
        eff = facts[fact].get(f"on_{state}") or {}
        for sig in eff.get("remove_signal", []):
            if sig in inputs.signals or sig in inputs.ml_signals:
                removed.add(sig)
                changes.append({"fact": fact, "state": state, "change": "remove_signal", "target": sig})
        for alt, fit in (eff.get("set_alternative_fit") or {}).items():
            changes.append({"fact": fact, "state": state, "change": "set_alternative_fit", "target": alt,
                            "from": fits.get(alt), "to": fit})
            fits[alt] = fit
    return replace(inputs.without(removed), alternative_fits=fits), changes


def recompute(inputs: ScoreInputs, adjudications: dict[str, str], facts: dict[str, dict[str, Any]],
              cfg: ScoringConfig) -> dict[str, Any]:
    new_inputs, changes = apply_facts(inputs, adjudications, facts)
    s = score(new_inputs, cfg)
    return {"score": s.total, "tier": s.tier, "still_opens_case": opens_case(new_inputs, cfg),
            "changes": changes, "breakdown": s}


def next_best_actions(inputs: ScoreInputs, adjudications: dict[str, str], facts: dict[str, dict[str, Any]],
                      cfg: ScoringConfig, relevant: set[str] | None = None) -> list[dict[str, Any]]:
    """For each unverified fact: score/tier if confirmed and if refuted, and the expected shift.

    Expected shift = mean |delta| over the two outcomes (equal weighting: an ASSUMPTION, no outcome
    probabilities are known). Ranked by shift per effort minute when effort is configured, else by shift.
    """
    base = recompute(inputs, adjudications, facts, cfg)
    out = []
    for fact, spec in facts.items():
        if adjudications.get(fact, "unknown") != "unknown" or (relevant is not None and fact not in relevant):
            continue
        outcomes = {}
        for st in ("confirmed", "refuted"):
            r = recompute(inputs, {**adjudications, fact: st}, facts, cfg)
            outcomes[st] = {"score": r["score"], "tier": r["tier"], "delta": round(r["score"] - base["score"], 2)}
        shift = round(sum(abs(o["delta"]) for o in outcomes.values()) / 2, 2)
        if shift == 0:
            continue
        effort = spec.get("effort_minutes")
        rationale = (f"If confirmed the priority score moves {outcomes['confirmed']['delta']:+g} "
                     f"({outcomes['confirmed']['tier']}); if refuted {outcomes['refuted']['delta']:+g} "
                     f"({outcomes['refuted']['tier']}).")
        out.append({"fact": fact, "label": spec.get("label", fact), "outcomes": outcomes, "expected_shift": shift,
                    "effort_minutes": effort, "effort_is_assumption": True,
                    "shift_per_minute": round(shift / effort, 3) if effort else None, "rationale": rationale})
    out.sort(key=lambda a: (-(a["shift_per_minute"] or 0), -a["expected_shift"]))
    return out
