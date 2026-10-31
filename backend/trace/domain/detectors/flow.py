"""Transaction-flow detectors. Vectorised over the canonical Transaction frame."""

from __future__ import annotations

import numpy as np
import pandas as pd

from trace.domain.detectors.base import (DetectorContext, DetectorResult, cap_list, fmt_cypher, register,
                                         tail_strength, ts_seconds)
from trace.domain.detectors.population import near_threshold_counts, structuring_threshold
from trace.domain.model.findings import Finding, node_id


def _acct(x) -> str:
    return node_id("account", x)


def _missing(ctx: DetectorContext, det: str, *names: str) -> str | None:
    p = ctx.p(det)
    gone = [n for n in names if p.get(n) is None]
    return f"threshold(s) {gone} could not be derived from this dataset" if gone else None


# ----------------------------------------------------------------------------- rapid pass-through

CYPHER_PASS = ("MATCH (a:Account)-[t1:TRANSFERS_TO]->(b:Account {id:$account})-[t2:TRANSFERS_TO]->(c:Account)\n"
               "WHERE t2.ts >= t1.ts AND t2.ts <= t1.ts + duration({minutes:$max_gap_minutes})\n"
               "WITH t1, sum(t2.amount) AS forwarded WHERE forwarded >= $min_forward_ratio * t1.amount\n"
               "RETURN t1, forwarded")


@register("rapid_pass_through")
def rapid_pass_through(ctx: DetectorContext) -> DetectorResult:
    det = "rapid_pass_through"
    if (why := _missing(ctx, det, "max_gap_minutes")):
        return DetectorResult([], [why])
    p = ctx.p(det)
    gap = int(round(p["max_gap_minutes"] * 60))
    t = ctx.txns
    t = t[t["src_account_id"] != t["dst_account_id"]]
    codes, uniq = pd.factorize(pd.concat([t["src_account_id"], t["dst_account_id"]], ignore_index=True))
    src_code, dst_code = codes[: len(t)], codes[len(t):]
    secs = ts_seconds(t["ts"])
    base = secs.min() if len(secs) else 0
    rel = secs - base
    shift = np.int64(1) << np.int64(34)  # > any relative span in seconds (~544 years)

    out_key = src_code.astype(np.int64) * shift + rel
    order = np.argsort(out_key, kind="stable")
    out_key_sorted = out_key[order]
    amounts = t["amount"].to_numpy(dtype=float)
    cum = np.concatenate([[0.0], np.cumsum(amounts[order])])

    in_key = dst_code.astype(np.int64) * shift + rel
    lo = np.searchsorted(out_key_sorted, in_key, side="left")      # outflows at/after inflow time
    hi = np.searchsorted(out_key_sorted, in_key + gap, side="right")
    forwarded = cum[hi] - cum[lo]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(amounts > 0, np.minimum(forwarded / amounts, 1.0), 0.0)
    hit = ratio >= p["min_forward_ratio"]
    if not hit.any():
        return DetectorResult([])

    txn_ids = t["txn_id"].to_numpy()
    dst = t["dst_account_id"].to_numpy()
    src = t["src_account_id"].to_numpy()
    by_acct: dict[str, dict] = {}
    for i in np.flatnonzero(hit):
        a = dst[i]
        out_idx = order[lo[i]:hi[i]]
        rec = by_acct.setdefault(a, {"in": [], "out": set(), "payers": set(), "payees": set(), "ratios": [],
                                     "inflow": 0.0, "forwarded": 0.0})
        rec["in"].append(txn_ids[i])
        rec["out"].update(txn_ids[out_idx])
        rec["payers"].add(src[i])
        rec["payees"].update(dst[out_idx])
        rec["ratios"].append(ratio[i])
        rec["inflow"] += amounts[i]
        rec["forwarded"] += min(forwarded[i], amounts[i])

    flagged = set(by_acct)
    findings = []
    for a, r in by_acct.items():
        chain_next = sorted(x for x in r["payees"] if x in flagged and x != a)
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(a),),
            related=tuple(_acct(x) for x in cap_list(r["payers"] | r["payees"])),
            txn_ids=tuple(r["in"]) + tuple(sorted(r["out"])),
            strength=float(np.mean(r["ratios"])),
            details={"account": a, "events": len(r["in"]), "inflow_total": r["inflow"],
                     "forwarded_total": r["forwarded"], "mean_forward_ratio": float(np.mean(r["ratios"])),
                     "max_gap_minutes": p["max_gap_minutes"], "chain_next_accounts": chain_next,
                     "throughput": r["forwarded"]},
            cypher_used=fmt_cypher(CYPHER_PASS, account=str(a), max_gap_minutes=round(p["max_gap_minutes"], 2),
                                   min_forward_ratio=p["min_forward_ratio"])))
    return DetectorResult(findings)


# ------------------------------------------------------------------------------------- fan in/out

CYPHER_FAN = {
    "fan_in": "MATCH (s:Account)-[t:TRANSFERS_TO]->(a:Account {id:$account})\n"
              "WHERE t.ts >= datetime($window_start) AND t.ts < datetime($window_end)\n"
              "WITH a, count(DISTINCT s) AS payers WHERE payers > $min_counterparties RETURN a, payers",
    "fan_out": "MATCH (a:Account {id:$account})-[t:TRANSFERS_TO]->(d:Account)\n"
               "WHERE t.ts >= datetime($window_start) AND t.ts < datetime($window_end)\n"
               "WITH a, count(DISTINCT d) AS payees WHERE payees > $min_counterparties RETURN a, payees",
}


def _fan(ctx: DetectorContext, det: str, hub_col: str, other_col: str) -> DetectorResult:
    if (why := _missing(ctx, det, "min_counterparties")):
        return DetectorResult([], [why])
    p = ctx.p(det)
    w = int(p["window_days"] * 86400)
    t = ctx.txns
    df = pd.DataFrame({"hub": t[hub_col].to_numpy(), "other": t[other_col].to_numpy(),
                       "b": ts_seconds(t["ts"]) // w, "txn_id": t["txn_id"].to_numpy()})
    counts = df.groupby(["hub", "b"])["other"].nunique().rename("n").reset_index()
    hits = counts[counts["n"] > p["min_counterparties"]]
    if hits.empty:
        return DetectorResult([])
    best = hits.sort_values("n", ascending=False).drop_duplicates("hub")
    pop = ctx.populations.get(f"{det}.min_counterparties")
    pct = p.get("_min_counterparties_percentile")
    sel = df.merge(best[["hub", "b"]], on=["hub", "b"])
    grouped = sel.groupby("hub")
    findings = []
    for _, row in best.iterrows():
        g = grouped.get_group(row["hub"])
        start = pd.Timestamp(int(row["b"]) * w, unit="s", tz="UTC")
        end = start + pd.Timedelta(seconds=w)
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(row["hub"]),),
            related=tuple(_acct(x) for x in cap_list(g["other"])), txn_ids=tuple(g["txn_id"]),
            strength=tail_strength(row["n"], pop, pct),
            details={"account": row["hub"], "distinct_counterparties": int(row["n"]),
                     "threshold": p["min_counterparties"], "window_start": str(start), "window_end": str(end),
                     "window_days": p["window_days"]},
            cypher_used=fmt_cypher(CYPHER_FAN[det], account=str(row["hub"]), window_start=str(start),
                                   window_end=str(end), min_counterparties=round(p["min_counterparties"], 2))))
    return DetectorResult(findings)


@register("fan_in")
def fan_in(ctx: DetectorContext) -> DetectorResult:
    return _fan(ctx, "fan_in", "dst_account_id", "src_account_id")


@register("fan_out")
def fan_out(ctx: DetectorContext) -> DetectorResult:
    return _fan(ctx, "fan_out", "src_account_id", "dst_account_id")


# ------------------------------------------------------------------------------------------ burst

CYPHER_BURST = ("MATCH (a:Account {id:$account})-[t:TRANSFERS_TO]->()\n"
                "WHERE t.ts >= datetime($window_start) AND t.ts < datetime($window_end)\n"
                "WITH a, count(t) AS n WHERE n > $min_txns RETURN a, n")


@register("burst_velocity")
def burst_velocity(ctx: DetectorContext) -> DetectorResult:
    det = "burst_velocity"
    if (why := _missing(ctx, det, "min_txns")):
        return DetectorResult([], [why])
    p = ctx.p(det)
    w = int(p["window_minutes"] * 60)
    t = ctx.txns
    df = pd.DataFrame({"a": t["src_account_id"].to_numpy(), "b": ts_seconds(t["ts"]) // w,
                       "txn_id": t["txn_id"].to_numpy(), "dst": t["dst_account_id"].to_numpy()})
    counts = df.groupby(["a", "b"]).size().rename("n").reset_index()
    hits = counts[counts["n"] > p["min_txns"]].sort_values("n", ascending=False).drop_duplicates("a")
    pop = ctx.populations.get(f"{det}.min_txns")
    sel = df.merge(hits[["a", "b"]], on=["a", "b"]).groupby("a")
    findings = []
    for _, row in hits.iterrows():
        g = sel.get_group(row["a"])
        start = pd.Timestamp(int(row["b"]) * w, unit="s", tz="UTC")
        end = start + pd.Timedelta(seconds=w)
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(row["a"]),),
            related=tuple(_acct(x) for x in cap_list(g["dst"])), txn_ids=tuple(g["txn_id"]),
            strength=tail_strength(row["n"], pop, p.get("_min_txns_percentile")),
            details={"account": row["a"], "txns_in_window": int(row["n"]), "threshold": p["min_txns"],
                     "window_minutes": p["window_minutes"], "window_start": str(start)},
            cypher_used=fmt_cypher(CYPHER_BURST, account=str(row["a"]), window_start=str(start), window_end=str(end),
                                   min_txns=round(p["min_txns"], 2))))
    return DetectorResult(findings)


# ------------------------------------------------------------------------ new account large inflow

CYPHER_NEW = ("MATCH (s:Account)-[t:TRANSFERS_TO]->(a:Account {id:$account})\n"
              "WHERE t.ts <= a.open_date + duration({days:$new_account_days}) AND t.amount > $min_amount\n"
              "RETURN a, t")


@register("new_account_large_inflow")
def new_account_large_inflow(ctx: DetectorContext) -> DetectorResult:
    det = "new_account_large_inflow"
    if (why := _missing(ctx, det, "min_amount")):
        return DetectorResult([], [why])
    p = ctx.p(det)
    acc = ctx.frames["Account"][["account_id", "open_date"]].dropna()
    t = ctx.txns.merge(acc, left_on="dst_account_id", right_on="account_id", how="inner")
    age_days = (t["ts"] - t["open_date"]).dt.total_seconds() / 86400
    hits = t[(age_days >= 0) & (age_days <= p["new_account_days"]) & (t["amount"] > p["min_amount"])]
    pop = ctx.populations.get(f"{det}.min_amount")
    findings = []
    for a, g in hits.groupby("dst_account_id"):
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(a),), related=tuple(_acct(x) for x in cap_list(g["src_account_id"])),
            txn_ids=tuple(g["txn_id"]), strength=tail_strength(g["amount"].max(), pop, p.get("_min_amount_percentile")),
            details={"account": a, "open_date": str(g["open_date"].iloc[0]), "inflows": int(len(g)),
                     "inflow_total": float(g["amount"].sum()), "largest_inflow": float(g["amount"].max()),
                     "min_amount": p["min_amount"], "new_account_days": p["new_account_days"]},
            cypher_used=fmt_cypher(CYPHER_NEW, account=str(a), new_account_days=p["new_account_days"],
                                   min_amount=round(p["min_amount"], 2))))
    return DetectorResult(findings)


# ------------------------------------------------------------------------------------ structuring

CYPHER_STRUCT = ("MATCH (a:Account {id:$account})-[t:TRANSFERS_TO]->()\n"
                 "WHERE t.amount >= $low AND t.amount < $threshold\n"
                 "  AND t.ts >= datetime($window_start) AND t.ts < datetime($window_end)\n"
                 "WITH a, count(t) AS n WHERE n > $min_count RETURN a, n")


@register("structuring")
def structuring(ctx: DetectorContext) -> DetectorResult:
    det = "structuring"
    p = ctx.p(det)
    thr, how = structuring_threshold(ctx.frames, p)
    if thr is None:
        return DetectorResult([], [f"Not evaluated: {how}"])
    if (why := _missing(ctx, det, "min_count")):
        return DetectorResult([], [why])
    near = near_threshold_counts(ctx.frames, p, thr)
    counts = near.groupby(["k", "b"]).size().rename("n").reset_index()
    hits = counts[counts["n"] > p["min_count"]].sort_values("n", ascending=False).drop_duplicates("k")
    w = int(p["window_days"] * 86400)
    pop = ctx.populations.get(f"{det}.min_count")
    sel = near.merge(hits[["k", "b"]], on=["k", "b"]).groupby("k")
    findings = []
    for _, row in hits.iterrows():
        g = sel.get_group(row["k"])
        start = pd.Timestamp(int(row["b"]) * w, unit="s", tz="UTC")
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(row["k"]),), txn_ids=tuple(g["txn_id"]),
            strength=tail_strength(row["n"], pop, p.get("_min_count_percentile")),
            details={"account": row["k"], "near_threshold_txns": int(row["n"]), "threshold": thr,
                     "threshold_source": how, "band": p["band"], "window_start": str(start),
                     "window_days": p["window_days"]},
            cypher_used=fmt_cypher(CYPHER_STRUCT, account=str(row["k"]), low=round(thr * (1 - p["band"]), 2),
                                   threshold=thr, window_start=str(start),
                                   window_end=str(start + pd.Timedelta(seconds=w)), min_count=p["min_count"])))
    return DetectorResult(findings, [f"structuring threshold: {how}"])


# -------------------------------------------------------------------------------- regular cadence

CYPHER_CADENCE = ("MATCH (a:Account {id:$src})-[t:TRANSFERS_TO]->(b:Account {id:$dst})\n"
                  "WITH a, b, collect(t) AS ts ORDER BY t.ts\n"
                  "// interval and amount coefficient of variation computed over ts\nRETURN a, b, ts")


@register("regular_cadence")
def regular_cadence(ctx: DetectorContext) -> DetectorResult:
    det = "regular_cadence"
    p = ctx.p(det)
    t = ctx.txns[["txn_id", "ts", "src_account_id", "dst_account_id", "amount"]]
    size = t.groupby(["src_account_id", "dst_account_id"])["txn_id"].transform("size")
    t = t[size >= p["min_occurrences"]].sort_values(["src_account_id", "dst_account_id", "ts"])
    if t.empty:
        return DetectorResult([])
    same = (t["src_account_id"].eq(t["src_account_id"].shift())) & (t["dst_account_id"].eq(t["dst_account_id"].shift()))
    t = t.assign(gap=np.where(same, t["ts"].diff().dt.total_seconds(), np.nan))
    agg = t.groupby(["src_account_id", "dst_account_id"]).agg(
        n=("txn_id", "size"), gap_mean=("gap", "mean"), gap_std=("gap", "std"),
        amt_mean=("amount", "mean"), amt_std=("amount", "std"))
    agg["gap_cv"] = agg["gap_std"] / agg["gap_mean"]
    agg["amt_cv"] = agg["amt_std"] / agg["amt_mean"]
    hits = agg[(agg["gap_mean"] > 0) & (agg["gap_cv"] <= p["max_interval_cv"]) & (agg["amt_cv"] <= p["max_amount_cv"])]
    if hits.empty:
        return DetectorResult([])
    ids = t.set_index(["src_account_id", "dst_account_id"])["txn_id"]
    findings = []
    for (s, d), r in hits.iterrows():
        findings.append(Finding(
            type=det, detector=det, subjects=(_acct(s), _acct(d)), txn_ids=tuple(ids.loc[(s, d)]),
            strength=float(1 - max(r["gap_cv"] / p["max_interval_cv"], r["amt_cv"] / p["max_amount_cv"]) / 2),
            details={"src": s, "dst": d, "payments": int(r["n"]), "mean_interval_days": r["gap_mean"] / 86400,
                     "interval_cv": float(r["gap_cv"]), "amount_cv": float(r["amt_cv"]),
                     "mean_amount": float(r["amt_mean"])},
            cypher_used=fmt_cypher(CYPHER_CADENCE, src=str(s), dst=str(d))))
    return DetectorResult(findings)
