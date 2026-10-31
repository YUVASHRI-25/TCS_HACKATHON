"""Read-side use cases for the API. Everything is computed from persisted pipeline output."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trace.infrastructure.container import Container

MAX_GRAPH_EDGES = 2000


def _evidence_index(case: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, float]]:
    by_txn: dict[str, list[str]] = {}
    by_node: dict[str, list[str]] = {}
    risk: dict[str, float] = {}
    for e in case["evidence"]:
        for t in e["txn_ids"]:
            by_txn.setdefault(str(t), []).append(e["id"])
        for n in e["entities"]:
            by_node.setdefault(n, []).append(e["id"])
            if e["finding_type"] != "regular_cadence":
                risk[n] = max(risk.get(n, 0.0), e["strength"])
    return by_txn, by_node, risk


def case_graph(c: Container, case: dict[str, Any]) -> dict[str, Any]:
    by_txn, by_node, risk = _evidence_index(case)
    subjects = {n for e in case["evidence"] if e["finding_type"] != "regular_cadence" for n in e["entities"]}
    ents = {e["id"]: e for e in case["entities"]}
    nodes = {nid: {"id": nid, "type": e["type"], "label": e["raw_id"], "role": e["role"], "derived": e["derived"],
                   "risk": round(risk.get(nid, 0.0), 3), "suspicious": nid in subjects and e["role"] == "member",
                   "evidence_ids": by_node.get(nid, [])} for nid, e in ents.items()}
    edges: list[dict[str, Any]] = []
    frames = c.frames()
    t = frames.get("Transaction")
    members = {e["raw_id"] for e in case["entities"] if e["type"] == "account"}
    truncated = False
    if t is not None and members:
        sub = t[t["src_account_id"].isin(members) & t["dst_account_id"].isin(members)].sort_values("ts")
        sus = sub["txn_id"].astype(str).isin(by_txn)
        sub = pd.concat([sub[sus], sub[~sus]])
        if len(sub) > MAX_GRAPH_EDGES:
            truncated, sub = True, sub.head(MAX_GRAPH_EDGES)
        for r in sub.to_dict("records"):
            tid = str(r["txn_id"])
            edges.append({"id": f"t:{tid}", "source": f"account:{r['src_account_id']}", "target": f"account:{r['dst_account_id']}",
                          "type": "TRANSFERS_TO", "suspicious": tid in by_txn, "evidence_ids": by_txn.get(tid, []),
                          "txn_id": tid, "ts": str(r["ts"]), "amount": float(r["amount"])})
    g = c.graph.tg
    if g is not None:
        for u, v, k, d in g.g.edges(keys=True, data=True):
            if d["type"] == "TRANSFERS_TO" or u not in nodes or v not in nodes:
                continue
            ev = sorted(set(by_node.get(u, [])) & set(by_node.get(v, [])))
            edges.append({"id": f"{d['type']}:{u}:{v}:{k}", "source": u, "target": v, "type": d["type"],
                          "suspicious": bool(ev) and d["type"] not in ("OWNS",), "evidence_ids": ev,
                          "confidence": d.get("confidence")})
    return {"nodes": list(nodes.values()), "edges": edges, "truncated": truncated}


def case_flow(c: Container, case: dict[str, Any]) -> dict[str, Any]:
    by_txn, _, _ = _evidence_index(case)
    t = c.frames().get("Transaction")
    members = {e["raw_id"] for e in case["entities"] if e["type"] == "account" and e["role"] == "member"}
    if t is None or not members:
        return {"nodes": [], "links": [], "currency_note": None}
    sub = t[t["src_account_id"].isin(members) | t["dst_account_id"].isin(members)].copy()
    sub["s"] = np.where(sub["src_account_id"].isin(members), "account:" + sub["src_account_id"].astype(str), "external:sources")
    sub["d"] = np.where(sub["dst_account_id"].isin(members), "account:" + sub["dst_account_id"].astype(str), "external:destinations")
    sub = sub[sub["s"] != sub["d"]]
    sub["sus_amt"] = np.where(sub["txn_id"].astype(str).isin(by_txn), sub["amount"], 0.0)
    agg = sub.groupby(["s", "d"]).agg(amount=("amount", "sum"), n_txns=("txn_id", "size"), suspicious_amount=("sus_amt", "sum")).reset_index()
    ids = sorted(set(agg["s"]) | set(agg["d"]))
    kind = {"external:sources": "external_sources", "external:destinations": "external_destinations"}
    nodes = [{"id": i, "label": {"external:sources": "Counterparties outside network (in)",
                                 "external:destinations": "Counterparties outside network (out)"}.get(i, i.split(":", 1)[1]),
              "kind": kind.get(i, "member")} for i in ids]
    links = [{"source": r["s"], "target": r["d"], "amount": float(r["amount"]), "n_txns": int(r["n_txns"]),
              "suspicious_amount": float(r["suspicious_amount"])} for r in agg.to_dict("records")]
    cur = None
    if "currency" in sub.columns and sub["currency"].nunique() > 1:
        cur = "Multiple currencies; amounts are summed without FX conversion."
    return {"nodes": nodes, "links": links, "currency_note": cur}


def evidence_detail(c: Container, case: dict[str, Any], eid: str) -> dict[str, Any] | None:
    ev = next((e for e in case["evidence"] if e["id"] == eid), None)
    if ev is None:
        return None
    raw_rows: list[dict[str, Any]] = []
    refs: dict[str, list[int]] = {}
    for r in ev["source_rows"]:
        table = r.get("_source_table") or r.get("table")
        row = r.get("_source_row", r.get("row"))
        if table is not None and row is not None:
            refs.setdefault(table, []).append(int(row))
    for table, rows in refs.items():
        raw = c.raw_table(table)
        if raw is None:
            continue
        hit = raw[raw["_source_row"].isin(rows)]
        raw_rows += [{"_table": table, **{k: (None if pd.isna(v) else v) for k, v in rec.items()}} for rec in hit.to_dict("records")]
    return {**ev, "raw_rows": raw_rows}


def _caps_with_status(run: dict[str, Any] | None, cap_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status = (run or {}).get("detector_status", {})
    return [{**cr, "run_status": status.get(cr["id"], {}).get("status"), "findings": status.get(cr["id"], {}).get("findings"),
             "notes": status.get(cr["id"], {}).get("notes", [])} for cr in cap_rows]


DATA_STATEMENT = ("All figures are computed by the TRACE pipeline from the configured dataset. Priority scores rank "
                  "where to look first; they are not probabilities of wrongdoing, and no determination has been made.")


def dashboard(c: Container, cap_rows: list[dict[str, Any]]) -> dict[str, Any]:
    run = c.cases.latest_run()
    rows = c.cases.all_rows() if run else []
    scores = [r["priority_score"] for r in rows]
    hist = [{"bin": f"{b}-{b + 9}", "count": int(sum(1 for s in scores if b <= s < b + 10 or (b == 90 and s == 100)))}
            for b in range(0, 100, 10)]
    warnings = []
    if run and run.get("too_few_cases_warning"):
        warnings.append(run["too_few_cases_warning"])
    if run:
        for det, st in run.get("detector_status", {}).items():
            if st.get("status") == "error":
                warnings.append(f"detector {det} failed: {'; '.join(st.get('notes', []))}")
    kpis = {}
    if run:
        tx_rc = run["row_counts"].get("Transaction", {})
        kpis = {"transactions_processed": tx_rc.get("kept"), "transactions_quarantined": tx_rc.get("quarantined"),
                "cases": len(rows),
                "pending_review": sum(1 for r in rows if r["tier"] == "HIGH" and r["status"] == "open"),
                "under_review": sum(1 for r in rows if r["status"] == "under_review"),
                "escalated": sum(1 for r in rows if r["status"] == "escalated"),
                "resolved": sum(1 for r in rows if r["status"] == "resolved"),
                "investigator_cases": sum(1 for r in rows if r.get("origin") == "investigator"),
                "exposure_surfaced": run.get("exposure_total"),
                "accounts_in_cases": sum(r["n_members"] for r in rows),
                "findings": sum(run.get("finding_counts", {}).values())}
    return {"pipeline_run": run is not None, "run_at": run and run["created_at"], "kpis": kpis,
            "tiers": {t: sum(1 for r in rows if r["tier"] == t) for t in ("HIGH", "MEDIUM", "LOW")},
            "score_histogram": hist, "capabilities": _caps_with_status(run, cap_rows),
            "grouping": run and run.get("grouping"), "warnings": warnings, "data_statement": DATA_STATEMENT}
