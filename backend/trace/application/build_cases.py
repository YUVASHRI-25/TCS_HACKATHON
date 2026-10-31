"""Case engine: networks -> explainable cases. Everything here is deterministic."""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from trace.domain.catalogues.alternatives import AltContext, evaluate_all
from trace.domain.catalogues.evidence_text import describe
from trace.domain.catalogues.hypotheses import build_hypotheses, build_next_steps
from trace.domain.guardrails.policy import GUARDRAIL_NOTICE, assert_clean
from trace.domain.model.findings import (DETERMINISTIC, MODEL, Case, Evidence, Finding, split_node_id)
from trace.domain.scoring.score import ScoreInputs, ScoringConfig, SignalInput, counterfactuals, score
from trace.intelligence.graph_analytics.networks import Network

MAX_ROWS_PER_EVIDENCE = 25


def case_id(members: set[str]) -> str:
    return "C-" + hashlib.sha1("|".join(sorted(members)).encode()).hexdigest()[:10].upper()


class TxnIndex:
    def __init__(self, txns: pd.DataFrame | None):
        if txns is None or txns.empty:
            self.df = pd.DataFrame()
            return
        cols = [c for c in ("txn_id", "ts", "src_account_id", "dst_account_id", "amount", "currency",
                            "_source_table", "_source_row") if c in txns.columns]
        self.df = txns[cols].drop_duplicates("txn_id").set_index("txn_id", drop=False)

    def rows(self, ids) -> pd.DataFrame:
        if self.df.empty:
            return self.df
        ids = [i for i in dict.fromkeys(ids) if i in self.df.index]
        return self.df.loc[ids]


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for r in df.head(MAX_ROWS_PER_EVIDENCE).to_dict("records"):
        out.append({k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in r.items()})
    return out


def _order_key(f: Finding, weights: dict[str, float]) -> tuple:
    return (f.source != DETERMINISTIC, -weights.get(f.type, 0), -f.strength, f.type, f.subjects)


def _exposure(findings: list[Finding], tx: TxnIndex) -> dict[str, Any]:
    ids = {t for f in findings if f.source == DETERMINISTIC for t in f.txn_ids}
    rows = tx.rows(ids)
    throughput = max((float(f.details.get("throughput", 0) or 0) for f in findings), default=0.0)
    if rows.empty:
        return {"suspicious_txns": 0, "total": 0.0, "by_currency": {}, "max_chain_throughput": throughput}
    by_cur = ({str(k): float(v) for k, v in rows.groupby(rows["currency"].fillna("UNKNOWN"))["amount"].sum().items()}
              if "currency" in rows.columns else {})
    return {"suspicious_txns": int(len(rows)), "total": float(rows["amount"].sum()), "by_currency": by_cur,
            "currency_known": "currency" in rows.columns, "max_chain_throughput": throughput,
            "note": None if len(by_cur) <= 1 else "multiple currencies: totals are not FX-converted"}


def build_case(net: Network, frames: dict[str, pd.DataFrame], tx: TxnIndex, cfg: ScoringConfig,
               catalogues: dict[str, Any], capabilities: list[dict[str, Any]], derived_fields: dict[str, list[str]],
               graph_node=None) -> Case:
    roles = {k: v["role"] for k, v in catalogues["signals"].items()}
    findings = sorted(net.findings, key=lambda f: _order_key(f, cfg.weights))
    context = sorted(net.context, key=lambda f: (-f.strength, f.subjects))

    evidence: list[Evidence] = []
    ev_of: dict[int, str] = {}
    for f in findings + context:
        eid = f"E{len(evidence) + 1:02d}"
        ev_of[id(f)] = eid
        rows = tx.rows(f.txn_ids)
        extra = f.details.get("source_rows") or []
        ts = rows["ts"] if "ts" in rows.columns and not rows.empty else pd.Series(dtype="datetime64[ns, UTC]")
        evidence.append(Evidence(
            id=eid, finding_type=f.type, description=describe(f), source=f.source, entities=list(f.subjects) + list(f.related),
            txn_ids=list(f.txn_ids), source_rows=_records(rows) + extra[:MAX_ROWS_PER_EVIDENCE],
            n_source_rows=int(len(rows)) + len(extra), ts_min=str(ts.min()) if len(ts) else None,
            ts_max=str(ts.max()) if len(ts) else None, cypher_used=f.cypher_used, strength=round(f.strength, 3),
            details={k: v for k, v in f.details.items() if k != "source_rows"}))

    sig_ev: dict[str, list[str]] = {}
    sig_strength: dict[str, float] = {}
    ml: dict[str, list] = {}
    for f in findings:
        if f.source == MODEL:
            ml.setdefault(f.type, []).append(f)
        elif roles.get(f.type) == "risk":
            sig_ev.setdefault(f.type, []).append(ev_of[id(f)])
            sig_strength[f.type] = max(sig_strength.get(f.type, 0), f.strength)

    txn_amount = {}
    if not tx.df.empty:
        all_ids = {t for f in findings + context for t in f.txn_ids}
        r = tx.rows(all_ids)
        txn_amount = dict(zip(r["txn_id"], r["amount"].astype(float)))
    caps = {c["id"]: c["enabled"] for c in capabilities}
    alt_ctx = AltContext(members=net.members, findings=findings, context=context, evidence_of=ev_of, frames=frames,
                         derived_fields=derived_fields, capabilities=caps,
                         params=catalogues.get("alternative_params") or {}, txn_amount=txn_amount)
    alternatives = evaluate_all(alt_ctx, catalogues["alternatives"])

    inputs = ScoreInputs(
        signals={k: SignalInput(sig_strength[k], tuple(v)) for k, v in sig_ev.items()},
        ml_signals={k: SignalInput(max(f.strength for f in v), tuple(ev_of[id(f)] for f in v)) for k, v in ml.items()},
        alternative_fits={a.id: a.fit for a in alternatives if a.status == "evaluated" and a.fit is not None})
    breakdown = score(inputs, cfg)
    cfs = counterfactuals(inputs, cfg)

    hyps = build_hypotheses(sig_ev, sig_strength, alternatives, catalogues["typologies"], cfg.weights)
    steps = build_next_steps(hyps, alternatives, catalogues["typologies"], catalogues["next_steps"])

    entities = []
    related = {r for f in findings for r in f.related} - net.members
    for nid in sorted(net.members) + sorted(related):
        kind, raw = split_node_id(nid)
        node = graph_node(nid) if graph_node else None
        entities.append({"id": nid, "type": kind, "raw_id": raw, "role": "member" if nid in net.members else "related",
                         "derived": bool(node and node.get("derived"))})

    labels = {k: v["label"] for k, v in catalogues["signals"].items()}
    n_acc = sum(1 for m in net.members if m.startswith("account:"))
    top = hyps[0].label if hyps else "no catalogued typology"
    summary = assert_clean(
        f"Network of {n_acc} account(s) with {len(sig_ev)} independent deterministic signal type(s) "
        f"({', '.join(labels.get(s, s) for s in sorted(sig_ev))}). Leading hypothesis: {top}. "
        f"Priority score {breakdown.total:g} ({breakdown.tier}). Requires human investigation.")

    key_questions = {
        "why_suspicious": [{"signal": s, "label": labels.get(s, s), "evidence_ids": sig_ev[s]}
                           for s in sorted(sig_ev, key=lambda s: -cfg.weights.get(s, 0))],
        "evidence": [e.id for e in evidence],
        "legitimate_explanations": [{"id": a.id, "label": a.label, "status": a.status, "fit": a.fit, "reason": a.reason}
                                    for a in alternatives if a.status != "not_applicable"],
        "next_steps": [s.label for s in steps],
    }
    disabled = [{"id": c["id"], "reason": c["reason"]} for c in capabilities if not c["enabled"]]
    return Case(
        id=case_id(net.members), summary=summary, tier=breakdown.tier, priority_score=breakdown.total,
        status="pending_review" if breakdown.tier == "HIGH" else "open", entities=entities, hypotheses=hyps,
        alternatives=alternatives, evidence=evidence, score_breakdown=breakdown, counterfactuals=cfs, next_steps=steps,
        exposure=_exposure(findings, tx), key_questions=key_questions,
        capabilities_used=sorted({f.detector for f in findings + context}), capabilities_disabled=disabled,
        guardrail_notice=GUARDRAIL_NOTICE, finding_types=sorted({f.type for f in findings}))


def score_inputs_from_case(case: dict[str, Any]) -> ScoreInputs:
    """Rebuild deterministic scoring inputs from a persisted case (used by what-if)."""
    sb = case["score_breakdown"]
    return ScoreInputs(
        signals={s["signal"]: SignalInput(s["strength"], tuple(s["evidence_ids"])) for s in sb["signals"]},
        ml_signals={s["signal"]: SignalInput(s["strength"], tuple(s["evidence_ids"])) for s in sb["ml_signals"]},
        alternative_fits={a["id"]: a["fit"] for a in case["alternatives"] if a["status"] == "evaluated" and a["fit"] is not None})
