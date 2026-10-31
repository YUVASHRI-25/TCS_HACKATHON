"""Circular flows of length min_length..max_length that are time-respecting and amount-similar."""

from __future__ import annotations

import networkx as nx
import numpy as np

from trace.domain.detectors.base import DetectorContext, DetectorResult, fmt_cypher, register, ts_seconds
from trace.domain.model.findings import Finding, node_id

CYPHER_CYCLE = ("MATCH p=(a:Account {id:$start})-[:TRANSFERS_TO*$min_length..$max_length]->(a)\n"
                "WHERE all(i IN range(0, size(relationships(p))-2)\n"
                "      WHERE relationships(p)[i].ts <= relationships(p)[i+1].ts)\n"
                "  AND last(relationships(p)).ts - head(relationships(p)).ts <= duration({minutes:$max_span_minutes})\n"
                "RETURN p")

_MAX_STARTS = 50  # earliest candidate start transactions tried per cycle


@register("cycle")
def cycle(ctx: DetectorContext) -> DetectorResult:
    p = ctx.p("cycle")
    if p.get("max_span_minutes") is None:
        return DetectorResult([], ["threshold max_span_minutes could not be derived from this dataset"])
    t = ctx.txns
    t = t[t["src_account_id"] != t["dst_account_id"]]
    pairs = t[["src_account_id", "dst_account_id"]].drop_duplicates()
    g = nx.DiGraph()
    g.add_edges_from(pairs.itertuples(index=False, name=None))
    sccs = [c for c in nx.strongly_connected_components(g) if len(c) >= p["min_length"]]
    if not sccs:
        return DetectorResult([])
    in_scc = set().union(*sccs)
    sub_t = t[t["src_account_id"].isin(in_scc) & t["dst_account_id"].isin(in_scc)].sort_values("ts")
    secs = ts_seconds(sub_t["ts"])
    edge_txns: dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for key, idx in sub_t.groupby(["src_account_id", "dst_account_id"]).indices.items():
        edge_txns[key] = (secs[idx], sub_t["amount"].to_numpy(dtype=float)[idx], sub_t["txn_id"].to_numpy()[idx])

    span = p["max_span_minutes"] * 60
    findings, notes, enumerated = [], [], 0
    for comp in sccs:
        for cyc in nx.simple_cycles(g.subgraph(comp), length_bound=p["max_length"]):
            if len(cyc) < p["min_length"]:
                continue
            enumerated += 1
            if enumerated > p["max_cycles"]:
                notes.append(f"cycle enumeration stopped at max_cycles={p['max_cycles']}; results are partial")
                break
            hit = _time_respecting(cyc, edge_txns, span, p["amount_tolerance"])
            if hit is None:
                continue
            txn_ids, amounts, t0, t1, cyc = hit
            spread = (max(amounts) - min(amounts)) / max(amounts) if max(amounts) > 0 else 0.0
            findings.append(Finding(
                type="cycle", detector="cycle", subjects=tuple(node_id("account", a) for a in cyc),
                txn_ids=tuple(txn_ids), strength=1 - 0.5 * (spread / p["amount_tolerance"] if p["amount_tolerance"] else 0),
                details={"accounts": list(cyc), "length": len(cyc), "amounts": amounts,
                         "amount_spread": spread, "span_minutes": (t1 - t0) / 60,
                         "max_span_minutes": p["max_span_minutes"], "throughput": min(amounts)},
                cypher_used=fmt_cypher(CYPHER_CYCLE, start=str(cyc[0]), min_length=p["min_length"],
                                       max_length=p["max_length"], max_span_minutes=round(p["max_span_minutes"], 2))))
        else:
            continue
        break
    return DetectorResult(findings, notes)


def _time_respecting(cyc, edge_txns, span, tol):
    """Try every rotation: the enumerator may start the loop at any node, the money may start at any hop."""
    for r in range(len(cyc)):
        hit = _from_start(cyc[r:] + cyc[:r], edge_txns, span, tol)
        if hit is not None:
            return hit
    return None


def _from_start(cyc, edge_txns, span, tol):
    edges = [(cyc[i], cyc[(i + 1) % len(cyc)]) for i in range(len(cyc))]
    if any(e not in edge_txns for e in edges):
        return None
    first_ts, first_amt, first_ids = edge_txns[edges[0]]
    for s in range(min(len(first_ts), _MAX_STARTS)):
        t_cur, chosen_ids, chosen_amt = first_ts[s], [first_ids[s]], [first_amt[s]]
        ok = True
        for e in edges[1:]:
            ts, amt, ids = edge_txns[e]
            j = np.searchsorted(ts, t_cur, side="left")
            if j >= len(ts) or ts[j] - first_ts[s] > span:
                ok = False
                break
            t_cur = ts[j]
            chosen_ids.append(ids[j])
            chosen_amt.append(float(amt[j]))
        if not ok:
            continue
        hi = max(chosen_amt)
        if hi > 0 and (hi - min(chosen_amt)) / hi <= tol:
            return chosen_ids, chosen_amt, first_ts[s], t_cur, list(cyc)
    return None
