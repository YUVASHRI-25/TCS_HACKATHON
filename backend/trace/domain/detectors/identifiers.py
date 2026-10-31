"""Detectors over shared identifiers and side tables (devices, IPs, merchants, complaints, alerts).

Shared identifiers never merge holders: each shared identifier yields a finding plus
`possible_related` links whose confidence falls as more accounts share the identifier (1/n).
"""

from __future__ import annotations


from trace.domain.detectors.base import (DetectorContext, DetectorResult, cap_list, fmt_cypher, register,
                                         tail_strength, ts_seconds)
from trace.domain.detectors.population import identifier_account_pairs
from trace.domain.model.findings import Finding, Link, node_id

CYPHER_SHARED = {
    "device": ("MATCH (a:Account)-[:USES_DEVICE]->(d:Device {id:$ident})<-[:USES_DEVICE]-(b:Account)\n"
               "MATCH (ca:Customer)-[:OWNS]->(a), (cb:Customer)-[:OWNS]->(b) WHERE ca <> cb\n"
               "RETURN d, collect(DISTINCT a) AS accounts"),
    "ip": ("MATCH (a:Account)-[:LOGGED_FROM_IP]->(i:IP {id:$ident})<-[:LOGGED_FROM_IP]-(b:Account)\n"
           "MATCH (ca:Customer)-[:OWNS]->(a), (cb:Customer)-[:OWNS]->(b) WHERE ca <> cb\n"
           "RETURN i, collect(DISTINCT a) AS accounts"),
}


def _holders(ctx: DetectorContext) -> tuple[dict, bool]:
    acc = ctx.frames.get("Account")
    if acc is None or "customer_id" not in acc.columns:
        return {}, True
    derived = "customer_id" in acc.attrs.get("derived_fields", [])
    return dict(zip(acc["account_id"], acc["customer_id"])), derived


def _shared(ctx: DetectorContext, ident: str, det: str, ftype: str) -> DetectorResult:
    p = ctx.p(det)
    pairs = identifier_account_pairs(ctx.frames, ident)
    if pairs.empty:
        return DetectorResult([])
    holders, holder_derived = _holders(ctx)
    pairs = pairs.assign(holder=pairs["account_id"].map(holders).fillna(pairs["account_id"]))
    stats = pairs.groupby("ident").agg(n_accounts=("account_id", "nunique"), n_holders=("holder", "nunique"))
    hits = stats[(stats["n_accounts"] >= p["min_accounts"]) & (stats["n_holders"] >= 2)]
    pop = ctx.populations.get(f"{det}.large_share_accounts")
    large = p.get("large_share_accounts")
    grouped = pairs[pairs["ident"].isin(hits.index)].groupby("ident")
    findings, links = [], []
    for ident_val, r in hits.iterrows():
        g = grouped.get_group(ident_val)
        accounts = sorted(g["account_id"].unique())
        conf = 1.0 / r["n_accounts"]
        for i, a in enumerate(accounts):
            for b in accounts[i + 1:]:
                links.append(Link(node_id("account", a), node_id("account", b), "possible_related", conf,
                                  [f"share {ident} {ident_val} (used by {r['n_accounts']} accounts)"]))
        findings.append(Finding(
            type=ftype, detector=det, subjects=tuple(node_id("account", a) for a in accounts),
            related=(node_id(ident, ident_val),), txn_ids=tuple(x for x in g["txn_id"].dropna().unique()),
            strength=tail_strength(r["n_accounts"], pop, p.get("_large_share_accounts_percentile")),
            details={ident: ident_val, "accounts": accounts, "n_accounts": int(r["n_accounts"]),
                     "n_holders": int(r["n_holders"]), "holders_derived": holder_derived,
                     "large_share": bool(large is not None and r["n_accounts"] > large),
                     "large_share_threshold": large, "link_confidence": conf,
                     "source_rows": g[["_source_table", "_source_row"]].head(50).to_dict("records")},
            cypher_used=fmt_cypher(CYPHER_SHARED[ident], ident=str(ident_val))))
    notes = ["holders are derived (one per account), so 'different holders' means different accounts"] \
        if holder_derived else []
    return DetectorResult(findings, notes, links)


@register("shared_device", "shared_device_unrelated")
def shared_device(ctx: DetectorContext) -> DetectorResult:
    return _shared(ctx, "device", "shared_device", "shared_device_unrelated")


@register("shared_ip")
def shared_ip(ctx: DetectorContext) -> DetectorResult:
    return _shared(ctx, "ip", "shared_ip", "shared_ip")


CYPHER_MERCHANT = ("MATCH (a:Account)-[t:PAID_MERCHANT]->(m:Merchant {flagged:true})\n"
                   "WHERE a.id = $account RETURN a, m, collect(t)")


@register("flagged_merchant")
def flagged_merchant(ctx: DetectorContext) -> DetectorResult:
    m = ctx.frames["Merchant"]
    flagged = set(m.loc[m["flagged"].fillna(False).astype(bool), "merchant_id"])
    t = ctx.txns.dropna(subset=["merchant_id"])
    hits = t[t["merchant_id"].isin(flagged)]
    findings = []
    for a, g in hits.groupby("src_account_id"):
        findings.append(Finding(
            type="flagged_merchant", detector="flagged_merchant", subjects=(node_id("account", a),),
            related=tuple(node_id("merchant", x) for x in cap_list(g["merchant_id"])), txn_ids=tuple(g["txn_id"]),
            strength=min(1.0, len(g) / max(1, len(t[t["src_account_id"] == a]))) * 0.5 + 0.5,
            details={"account": a, "flagged_merchants": sorted(g["merchant_id"].unique()), "payments": int(len(g)),
                     "amount_total": float(g["amount"].sum())},
            cypher_used=fmt_cypher(CYPHER_MERCHANT, account=str(a))))
    return DetectorResult(findings)


def _subject_node(stype, sid) -> str:
    return node_id(str(stype).lower() if isinstance(stype, str) and stype else "entity", sid)


CYPHER_COMPLAINT = "MATCH (c:Complaint)-[:COMPLAINT_ABOUT]->(s {id:$subject}) RETURN s, collect(c)"


@register("complaint_cluster")
def complaint_cluster(ctx: DetectorContext) -> DetectorResult:
    p = ctx.p("complaint_cluster")
    if p.get("min_complaints") is None:
        return DetectorResult([], ["threshold min_complaints could not be derived from this dataset"])
    c = ctx.frames["Complaint"].dropna(subset=["ts", "subject_id"])
    w = int(p["window_days"] * 86400)
    c = c.assign(b=ts_seconds(c["ts"]) // w)
    counts = c.groupby(["subject_id", "b"]).size().rename("n").reset_index()
    hits = counts[counts["n"] > p["min_complaints"]].sort_values("n", ascending=False).drop_duplicates("subject_id")
    pop = ctx.populations.get("complaint_cluster.min_complaints")
    findings = []
    for _, r in hits.iterrows():
        g = c[(c["subject_id"] == r["subject_id"]) & (c["b"] == r["b"])]
        stype = g["subject_type"].iloc[0] if "subject_type" in g.columns else None
        findings.append(Finding(
            type="complaint_cluster", detector="complaint_cluster", subjects=(_subject_node(stype, r["subject_id"]),),
            txn_ids=(), strength=tail_strength(r["n"], pop, p.get("_min_complaints_percentile")),
            details={"subject": r["subject_id"], "complaints": int(r["n"]), "threshold": p["min_complaints"],
                     "complaint_ids": list(g["complaint_id"]),
                     "source_rows": g[["_source_table", "_source_row"]].to_dict("records")},
            cypher_used=fmt_cypher(CYPHER_COMPLAINT, subject=str(r["subject_id"]))))
    return DetectorResult(findings)


CYPHER_ALERT = "MATCH (al:PriorAlert)-[:PRIOR_ALERT_ON]->(s {id:$subject}) WHERE al.outcome IN $outcomes RETURN s, al"


@register("prior_escalation")
def prior_escalation(ctx: DetectorContext) -> DetectorResult:
    p = ctx.p("prior_escalation")
    outcomes = set(p.get("escalated_outcomes") or [])
    if not outcomes:
        return DetectorResult([], ["Not evaluated: prior_escalation.escalated_outcomes is not configured "
                                   "(which Alert.outcome values mean 'escalated' must come from the data owner)"])
    a = ctx.frames["Alert"]
    hits = a[a["outcome"].isin(outcomes)]
    findings = []
    for sid, g in hits.groupby("subject_id"):
        stype = g["subject_type"].iloc[0] if "subject_type" in g.columns else None
        findings.append(Finding(
            type="prior_escalation", detector="prior_escalation", subjects=(_subject_node(stype, sid),), txn_ids=(),
            strength=1.0, details={"subject": sid, "alerts": list(g["alert_id"]), "outcomes": sorted(g["outcome"].unique()),
                                   "source_rows": g[["_source_table", "_source_row"]].to_dict("records")},
            cypher_used=fmt_cypher(CYPHER_ALERT, subject=str(sid), outcomes=sorted(outcomes))))
    return DetectorResult(findings)
