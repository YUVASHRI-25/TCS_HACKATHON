"""Hypotheses from the fixed typology catalogue, each with evidence for and against."""

from __future__ import annotations

from typing import Any

from trace.domain.model.findings import AlternativeResult, Hypothesis, NextStep


def build_hypotheses(signal_evidence: dict[str, list[str]], signal_strength: dict[str, float],
                     alternatives: list[AlternativeResult], typologies: dict[str, dict[str, Any]],
                     weights: dict[str, float]) -> list[Hypothesis]:
    against = sorted({e for a in alternatives if a.status == "evaluated" and (a.fit or 0) > 0 for e in a.evidence_ids})
    out = []
    for tid, spec in typologies.items():
        sup = spec["supporting_signals"]
        present = [s for s in sup if s in signal_evidence]
        # A typology is only proposed when at least one of its defining signals is present.
        if not present or not any(s in signal_evidence for s in spec.get("requires_any", sup)):
            continue
        denom = sum(weights.get(s, 0) for s in sup) or 1
        support = sum(weights.get(s, 0) * signal_strength.get(s, 0) for s in present) / denom
        out.append(Hypothesis(id=tid, label=spec["label"], description=spec["description"], support=round(support, 3),
                              evidence_for=sorted({e for s in present for e in signal_evidence[s]}),
                              evidence_against=against, missing_signals=[s for s in sup if s not in signal_evidence]))
    return sorted(out, key=lambda h: -h.support)


def build_next_steps(hypotheses: list[Hypothesis], alternatives: list[AlternativeResult],
                     typologies: dict[str, dict[str, Any]], catalogue: dict[str, dict[str, Any]]) -> list[NextStep]:
    steps: dict[str, NextStep] = {}

    def add(sid: str, reason: str, hyp: str | None = None):
        spec = catalogue[sid]
        st = steps.setdefault(sid, NextStep(sid, spec["label"], spec["description"], reason, []))
        if hyp and hyp not in st.related_hypotheses:
            st.related_hypotheses.append(hyp)

    for h in hypotheses:
        for sid in typologies[h.id].get("next_steps", []):
            add(sid, f"tests hypothesis {h.label}", h.id)
    for a in alternatives:
        if a.next_step and a.status in ("cannot_evaluate", "evaluated"):
            why = (f"the data cannot evaluate '{a.label}': {a.reason}" if a.status == "cannot_evaluate"
                   else f"confirms or rules out '{a.label}'")
            add(a.next_step, why)
    return list(steps.values())
