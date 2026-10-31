"""Population metrics: the distributions thresholds are derived from.

Each metric returns the raw (unsorted) population for the dataset at hand. thresholds.py takes the
configured percentile of it. Nothing here contains a dataset value.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from trace.domain.detectors.base import ts_seconds

MetricFn = Callable[[dict[str, pd.DataFrame], dict[str, Any]], np.ndarray]
METRICS: dict[str, MetricFn] = {}
METRIC_DOC: dict[str, str] = {}


def metric(name: str, doc: str):
    def deco(fn: MetricFn) -> MetricFn:
        METRICS[name] = fn
        METRIC_DOC[name] = doc
        return fn
    return deco


def hold_times_minutes(txns: pd.DataFrame) -> pd.DataFrame:
    """For every inflow into an account, minutes until that account's next outflow (NaN if none)."""
    inflow = txns[["txn_id", "ts", "dst_account_id", "amount"]].rename(columns={"dst_account_id": "acct"})
    outflow = txns[["ts", "src_account_id"]].rename(columns={"src_account_id": "acct", "ts": "out_ts"})
    inflow = inflow.sort_values("ts")
    outflow = outflow.sort_values("out_ts")
    m = pd.merge_asof(inflow, outflow, left_on="ts", right_on="out_ts", by="acct", direction="forward",
                      allow_exact_matches=True)
    m["hold_minutes"] = (m["out_ts"] - m["ts"]).dt.total_seconds() / 60.0
    return m


class PassThroughEvents:
    """Per inflow: how much of it the receiving account forwarded (same currency) within the gap."""

    def __init__(self, t, hit, order, lo, hi, forwarded, ratio):
        self.t, self.hit, self.order, self.lo, self.hi, self.forwarded, self.ratio = t, hit, order, lo, hi, forwarded, ratio


def pass_through_events(txns: pd.DataFrame, max_gap_minutes: float, min_forward_ratio: float) -> PassThroughEvents:
    gap = int(round(max_gap_minutes * 60))
    t = txns[txns["src_account_id"] != txns["dst_account_id"]]
    codes, _ = pd.factorize(pd.concat([t["src_account_id"], t["dst_account_id"]], ignore_index=True))
    src_code, dst_code = codes[: len(t)].astype(np.int64), codes[len(t):].astype(np.int64)
    if "currency" in t.columns:
        # Amounts are only comparable within one currency (no FX rates are assumed).
        cur, cur_uniq = pd.factorize(t["currency"].fillna("?"))
        n_cur = max(1, len(cur_uniq))
        src_code = src_code * n_cur + cur
        dst_code = dst_code * n_cur + cur
    secs = ts_seconds(t["ts"])
    rel = secs - (secs.min() if len(secs) else 0)
    shift = np.int64(1) << np.int64(34)  # > any relative span in seconds (~544 years)
    out_key = src_code * shift + rel
    order = np.argsort(out_key, kind="stable")
    out_key_sorted = out_key[order]
    amounts = t["amount"].to_numpy(dtype=float)
    cum = np.concatenate([[0.0], np.cumsum(amounts[order])])
    in_key = dst_code * shift + rel
    lo = np.searchsorted(out_key_sorted, in_key, side="left")       # outflows at/after the inflow
    hi = np.searchsorted(out_key_sorted, in_key + gap, side="right")
    forwarded = cum[hi] - cum[lo]
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(amounts > 0, np.minimum(forwarded / amounts, 1.0), 0.0)
    return PassThroughEvents(t, ratio >= min_forward_ratio, order, lo, hi, forwarded, ratio)


@metric("pass_through_events_per_account", "rapid pass-through events per account, over all accounts that "
                                          "receive funds (uses the derived max_gap_minutes)")
def _pass_events(frames, params):
    ev = pass_through_events(frames["Transaction"], params["max_gap_minutes"], params["min_forward_ratio"])
    receivers = pd.Index(ev.t["dst_account_id"].unique())
    counts = pd.Series(ev.t["dst_account_id"].to_numpy()[ev.hit]).value_counts()
    return counts.reindex(receivers, fill_value=0).to_numpy(dtype=float)


@metric("hold_time_minutes", "minutes from each inflow into an account to that account's next outflow "
                             "(inflows with a later outflow only)")
def _hold(frames, params):
    h = hold_times_minutes(frames["Transaction"])["hold_minutes"].to_numpy(dtype=float)
    return h[np.isfinite(h)]


def _window_counts(txns: pd.DataFrame, key: str, other: str, window_days: float) -> pd.DataFrame:
    w = int(window_days * 86400)
    df = pd.DataFrame({"k": txns[key].to_numpy(), "o": txns[other].to_numpy(),
                       "b": ts_seconds(txns["ts"]) // w})
    return df.groupby(["k", "b"])["o"].nunique().rename("n").reset_index()


@metric("distinct_payers_per_window", "distinct payers per receiving account per tumbling window "
                                      "(fan_in.window_days), over all account-windows with activity")
def _payers(frames, params):
    return _window_counts(frames["Transaction"], "dst_account_id", "src_account_id",
                          params["window_days"])["n"].to_numpy(dtype=float)


@metric("distinct_payees_per_window", "distinct payees per sending account per tumbling window "
                                      "(fan_out.window_days), over all account-windows with activity")
def _payees(frames, params):
    return _window_counts(frames["Transaction"], "src_account_id", "dst_account_id",
                          params["window_days"])["n"].to_numpy(dtype=float)


@metric("txns_per_account_window", "transactions sent per account per tumbling window "
                                   "(burst_velocity.window_minutes), over all account-windows with activity")
def _burst(frames, params):
    t = frames["Transaction"]
    w = int(params["window_minutes"] * 60)
    df = pd.DataFrame({"k": t["src_account_id"].to_numpy(), "b": ts_seconds(t["ts"]) // w})
    return df.groupby(["k", "b"]).size().to_numpy(dtype=float)


@metric("inflow_amount", "amount of every transaction (as an inflow to its receiver)")
def _inflow(frames, params):
    a = frames["Transaction"]["amount"].to_numpy(dtype=float)
    return a[np.isfinite(a)]


# (entity, identifier column) for each place a device / IP can be observed in use.
USAGE_SOURCES = {
    "device": {"Transaction": "device_id", "Device": "device_id", "DeviceUsage": "device_id", "Login": "device_id"},
    "ip": {"Transaction": "ip_id", "IP": "ip_id", "Login": "ip_id"},
}


def identifier_account_pairs(frames: dict[str, pd.DataFrame], ident: str,
                             sources: list[str] | None = None) -> pd.DataFrame:
    """(ident, account_id, holder, _source_table, _source_row, txn_id) for 'device' or 'ip'.

    Customer-level usage (e.g. logins) is expanded to that customer's accounts via Account.customer_id.
    `sources` restricts which canonical entities are read (detector parameter `usage_sources`).
    """
    cols = ["ident", "account_id", "holder", "_source_table", "_source_row", "txn_id"]
    acc = frames.get("Account")
    owner = acc[["account_id", "customer_id"]].dropna() if acc is not None and "customer_id" in acc.columns else None
    parts = []
    for ent, col in USAGE_SOURCES[ident].items():
        if sources is not None and ent not in sources:
            continue
        df = frames.get(ent)
        if df is None or col not in df.columns:
            continue
        df = df.dropna(subset=[col])
        if ent == "Transaction":
            p = df[[col, "src_account_id", "_source_table", "_source_row", "txn_id"]].rename(
                columns={col: "ident", "src_account_id": "account_id"})
            parts.append(p.assign(holder=None))
        elif "account_id" in df.columns and df["account_id"].notna().any():
            p = df.dropna(subset=["account_id"])[[col, "account_id", "_source_table", "_source_row"]]
            parts.append(p.rename(columns={col: "ident"}).assign(holder=None, txn_id=None))
        elif "customer_id" in df.columns and owner is not None:
            p = df.dropna(subset=["customer_id"])[[col, "customer_id", "_source_table", "_source_row"]]
            p = p.merge(owner, on="customer_id").rename(columns={col: "ident", "customer_id": "holder"})
            parts.append(p.assign(txn_id=None))
    if not parts:
        return pd.DataFrame(columns=cols)
    out = pd.concat(parts, ignore_index=True)
    if owner is not None:
        out["holder"] = out["holder"].fillna(out["account_id"].map(dict(zip(owner["account_id"], owner["customer_id"]))))
    out["holder"] = out["holder"].fillna(out["account_id"])
    return out[cols]


@metric("accounts_per_device", "distinct accounts per device identifier (shared_device.usage_sources)")
def _apd(frames, params):
    pairs = identifier_account_pairs(frames, "device", params.get("usage_sources"))
    return pairs.groupby("ident")["account_id"].nunique().to_numpy(dtype=float)


@metric("accounts_per_ip", "distinct accounts per IP identifier (shared_ip.usage_sources)")
def _api(frames, params):
    pairs = identifier_account_pairs(frames, "ip", params.get("usage_sources"))
    return pairs.groupby("ident")["account_id"].nunique().to_numpy(dtype=float)


@metric("complaints_per_subject_window", "complaints per subject per tumbling window "
                                         "(complaint_cluster.window_days), subjects with >=1 complaint")
def _complaints(frames, params):
    c = frames["Complaint"].dropna(subset=["ts", "subject_id"])
    w = int(params["window_days"] * 86400)
    df = pd.DataFrame({"k": c["subject_id"].to_numpy(), "b": ts_seconds(c["ts"]) // w})
    return df.groupby(["k", "b"]).size().to_numpy(dtype=float)


# --------------------------------------------------------------------- threshold clustering

def threshold_clustering(x: np.ndarray, band: float = 0.1) -> list[dict[str, Any]]:
    """For round marks inside the observed range (1, 2, 5 x 10^k), compare the count just below the
    mark ([T*(1-band), T)) with just above ([T, T*(1+band))). A high below/above ratio is a candidate
    structuring threshold for human review; nothing is assumed about any jurisdiction."""
    x = x[np.isfinite(x) & (x > 0)]
    if x.size < 100:
        return []
    lo, hi = np.percentile(x, 5), np.percentile(x, 99.5)
    marks = sorted({m * 10 ** k for k in range(int(math.floor(math.log10(lo))), int(math.ceil(math.log10(hi))) + 1)
                    for m in (1, 2, 5) if lo <= m * 10 ** k <= hi})
    res = []
    for t in marks:
        below = int(((x >= t * (1 - band)) & (x < t)).sum())
        above = int(((x >= t) & (x < t * (1 + band))).sum())
        res.append({"mark": t, "below": below, "above": above,
                    "ratio_below_above": round(below / above, 3) if above else None})
    return sorted(res, key=lambda r: -(r["ratio_below_above"] or 0))[:8]


def structuring_threshold(frames: dict[str, pd.DataFrame], params: dict[str, Any]
                          ) -> dict[str, tuple[float | None, str]]:
    """Per currency (amounts in different currencies are never compared): {currency: (threshold, how)}.
    Currency key "" when the data has no currency field."""
    t = frames["Transaction"]
    groups = t.groupby(t["currency"].fillna("")) if "currency" in t.columns else [("", t)]
    out: dict[str, tuple[float | None, str]] = {}
    configured = params.get("reporting_threshold")
    for cur, g in groups:
        if configured:
            val = configured.get(cur) if isinstance(configured, dict) else configured
            if val:
                out[cur] = (float(val), "configured reporting_threshold")
                continue
        cands = [c for c in threshold_clustering(g["amount"].to_numpy(dtype=float), params["band"])
                 if c["ratio_below_above"] and c["ratio_below_above"] >= params["min_clustering_ratio"]]
        if not cands:
            out[cur] = (None, f"no round mark with below/above ratio >= {params['min_clustering_ratio']} in the "
                              f"{cur or 'amount'} distribution")
            continue
        best = cands[0]
        out[cur] = (float(best["mark"]), f"detected from the {cur or 'amount'} distribution: {best['below']} txns just "
                                         f"below vs {best['above']} just above {best['mark']:g} "
                                         f"(ratio {best['ratio_below_above']})")
    return out


def near_threshold_counts(frames: dict[str, pd.DataFrame], params: dict[str, Any],
                          thresholds: dict[str, tuple[float, str]]) -> pd.DataFrame:
    t = frames["Transaction"]
    cur = t["currency"].fillna("") if "currency" in t.columns else pd.Series("", index=t.index)
    w = int(params["window_days"] * 86400)
    parts = []
    for c, (thr, _) in thresholds.items():
        m = (cur == c) & (t["amount"] >= thr * (1 - params["band"])) & (t["amount"] < thr)
        near = t[m]
        parts.append(pd.DataFrame({"k": near["src_account_id"].to_numpy(), "cur": c, "b": ts_seconds(near["ts"]) // w,
                                   "txn_id": near["txn_id"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["k", "cur", "b", "txn_id"])


@metric("near_threshold_count_per_window", "transactions per sending account per window within the band just "
                                           "below the structuring threshold (account-windows with >=1 such txn)")
def _near(frames, params):
    found = {c: v for c, v in structuring_threshold(frames, params).items() if v[0] is not None}
    if not found:
        return np.array([], dtype=float)
    return near_threshold_counts(frames, params, found).groupby(["k", "cur", "b"]).size().to_numpy(dtype=float)
