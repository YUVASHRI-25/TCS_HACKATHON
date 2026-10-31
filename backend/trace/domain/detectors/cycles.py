"""Circular flows: time-respecting, same-currency, amount-similar loops of length min..max.

Searched along transactions (temporal DFS), not over the static graph: on dense transfer graphs the
number of static cycles explodes, while a loop of money must also move forward in time, stay in one
currency and keep similar amounts, which prunes the search sharply.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trace.domain.detectors.base import DetectorContext, DetectorResult, fmt_cypher, register, ts_seconds
from trace.domain.model.findings import Finding, node_id

CYPHER_CYCLE = ("MATCH p=(a:Account {id:$start})-[:TRANSFERS_TO*$min_length..$max_length]->(a)\n"
                "WHERE all(i IN range(0, size(relationships(p))-2)\n"
                "      WHERE relationships(p)[i].ts <= relationships(p)[i+1].ts)\n"
                "  AND all(r IN relationships(p) WHERE r.currency = head(relationships(p)).currency)\n"
                "  AND last(relationships(p)).ts - head(relationships(p)).ts <= duration({minutes:$max_span_minutes})\n"
                "RETURN p")


@register("cycle")
def cycle(ctx: DetectorContext) -> DetectorResult:
    p = ctx.p("cycle")
    if p.get("max_span_minutes") is None:
        return DetectorResult([], ["threshold max_span_minutes could not be derived from this dataset"])
    t = ctx.txns
    t = t[t["src_account_id"] != t["dst_account_id"]]
    cur = t["currency"].fillna("").to_numpy() if "currency" in t.columns else np.full(len(t), "")
    order = np.lexsort((ts_seconds(t["ts"]), cur, t["src_account_id"].to_numpy()))
    src = t["src_account_id"].to_numpy()[order]
    dst = t["dst_account_id"].to_numpy()[order]
    secs = ts_seconds(t["ts"])[order]
    amt = t["amount"].to_numpy(dtype=float)[order]
    ids = t["txn_id"].to_numpy()[order]
    cur = cur[order]
    # index: (account, currency) -> slice of its outgoing txns sorted by time
    out_idx: dict[tuple, tuple[int, int]] = {}
    keys = list(zip(src, cur))
    i = 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        out_idx[keys[i]] = (i, j)
        i = j

    span = p["max_span_minutes"] * 60
    tol, lo_len, hi_len, budget = p["amount_tolerance"], p["min_length"], p["max_length"], p["max_search_expansions"]
    seen: set[frozenset] = set()
    findings, notes = [], []
    expanded = 0

    for e0 in range(len(src)):
        start, t0, a0, c0 = src[e0], secs[e0], amt[e0], cur[e0]
        stack = [(dst[e0], t0, [e0], a0, a0)]
        while stack:
            node, t_cur, path, amin, amax = stack.pop()
            expanded += 1
            if expanded > budget:
                break
            sl = out_idx.get((node, c0))
            if sl is None:
                continue
            a, b = sl
            k = a + int(np.searchsorted(secs[a:b], t_cur, side="left"))
            visited = {src[x] for x in path}
            while k < b and secs[k] - t0 <= span:
                nmin, nmax = min(amin, amt[k]), max(amax, amt[k])
                if nmax > 0 and (nmax - nmin) / nmax <= tol:
                    nxt = dst[k]
                    if nxt == start and len(path) + 1 >= lo_len:
                        loop = path + [k]
                        key = frozenset(ids[x] for x in loop)
                        if key not in seen:
                            seen.add(key)
                            findings.append(_finding(loop, src, ids, amt, secs, c0, nmin, nmax, p))
                    elif nxt not in visited and nxt != start and len(path) + 1 < hi_len:
                        stack.append((nxt, secs[k], path + [k], nmin, nmax))
                k += 1
        if expanded > budget:
            notes.append(f"cycle search stopped after {budget:,} expansions (max_search_expansions); results are partial")
            break
    return DetectorResult(findings, notes)


def _finding(loop, src, ids, amt, secs, currency, amin, amax, p) -> Finding:
    accounts = [src[x] for x in loop]
    spread = (amax - amin) / amax if amax > 0 else 0.0
    amounts = [float(amt[x]) for x in loop]
    return Finding(
        type="cycle", detector="cycle", subjects=tuple(node_id("account", a) for a in accounts),
        txn_ids=tuple(ids[x] for x in loop),
        strength=1 - 0.5 * (spread / p["amount_tolerance"] if p["amount_tolerance"] else 0),
        details={"accounts": accounts, "length": len(loop), "amounts": amounts, "currency": currency or None,
                 "amount_spread": spread, "span_minutes": float(secs[loop[-1]] - secs[loop[0]]) / 60,
                 "max_span_minutes": p["max_span_minutes"], "throughput": min(amounts),
                 "start": str(pd.Timestamp(int(secs[loop[0]]), unit="s", tz="UTC"))},
        cypher_used=fmt_cypher(CYPHER_CYCLE, start=str(accounts[0]), min_length=p["min_length"],
                               max_length=p["max_length"], max_span_minutes=round(p["max_span_minutes"], 2)))
