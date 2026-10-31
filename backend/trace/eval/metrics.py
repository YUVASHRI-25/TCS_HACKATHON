"""Success measures from the brief, computed from persisted cases. Phase 8 extends this."""

from __future__ import annotations

from typing import Any

DOES_NOT_PROVE = [
    "A high priority score does not show that anyone did anything wrong; it ranks where a human should look first.",
    "Coverage metrics show that explanations exist and resolve to source rows, not that the explanations are correct.",
    "Without independently verified outcomes, false-positive control is measured as downgrades by legitimate "
    "alternatives, not as a confirmed false-positive rate.",
]


def compute(cases: list[dict[str, Any]], run: dict[str, Any] | None, tiers: dict[str, float]) -> dict[str, Any]:
    if not run:
        return {"computed": False, "measures": [], "label_report": None, "does_not_prove": DOES_NOT_PROVE}
    n = len(cases)

    def pct(k: int) -> float | None:
        return round(k / n, 4) if n else None

    evaluated_2 = sum(1 for c in cases if sum(1 for a in c["alternatives"] if a["status"] == "evaluated") >= 2)
    explained = sum(1 for c in cases if c["score_breakdown"]["signals"] and c["counterfactuals"])
    resolving = 0
    for c in cases:
        ids = {e["id"] for e in c["evidence"]}
        cited = {e for q in c["key_questions"]["why_suspicious"] for e in q["evidence_ids"]}
        if cited <= ids and all(e["n_source_rows"] > 0 or e["source"] == "model" for e in c["evidence"]):
            resolving += 1
    downgraded, reasons = 0, {}
    for c in cases:
        pens = c["score_breakdown"]["penalties"]
        if pens:
            pre = c["score_breakdown"]["total"] - sum(p["points"] for p in pens)
            tier_pre = "HIGH" if pre >= tiers["high"] else "MEDIUM" if pre >= tiers["medium"] else "LOW"
            if tier_pre != c["tier"]:
                downgraded += 1
                for p in pens:
                    reasons[p["alternative"]] = reasons.get(p["alternative"], 0) + 1
    g = run.get("grouping", {})
    measures = [
        {"id": "network_discovery", "label": "Network discovery", "value": n,
         "detail": {"candidate_networks": g.get("candidate_networks"), "kept": g.get("kept"),
                    "dropped_too_few_types": g.get("dropped_too_few_types"), "dropped_model_only": g.get("dropped_model_only")},
         "note": "Networks with at least the configured number of independent deterministic signal types."},
        {"id": "evidence_traceability", "label": "Evidence traceability", "value": pct(resolving),
         "note": "Share of cases whose cited evidence IDs all exist and resolve to source rows. Narrative-sentence "
                 "traceability is added with the narrative (Phase 5)."},
        {"id": "false_positive_control", "label": "False-positive control", "value": pct(downgraded),
         "detail": {"downgraded_by_alternative": downgraded, "reasons": reasons},
         "note": "Share of cases whose tier was lowered by a legitimate-alternative penalty."},
        {"id": "alternative_reasoning", "label": "Alternative-hypothesis reasoning", "value": pct(evaluated_2),
         "note": "Share of cases with at least two alternatives actually evaluated (not 'cannot evaluate')."},
        {"id": "explainability", "label": "Explainability", "value": pct(explained),
         "note": "Share of cases with a score waterfall and counterfactuals. Faithful narrative is added in Phase 5."},
    ]
    return {"computed": True, "measures": measures, "label_report": run.get("label_report"), "does_not_prove": DOES_NOT_PROVE}
