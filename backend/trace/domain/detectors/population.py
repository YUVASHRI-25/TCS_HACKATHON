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


def identifier_account_pairs(frames: dict[str, pd.DataFrame], ident: str) -> pd.DataFrame:
    """(identifier, account, _source_table, _source_row) pairs for 'device' or 'ip'."""
    tx_col, ent, ent_col = {"device": ("device_id", "Device", "device_id"),
                            "ip": ("ip_address", "IP", "ip_address")}[ident]
    parts = []
    t = frames.get("Transaction")
    if t is not None and tx_col in t.columns:
        p = t[[tx_col, "src_account_id", "_source_table", "_source_row", "txn_id"]].dropna(subset=[tx_col])
        parts.append(p.rename(columns={tx_col: "ident", "src_account_id": "account_id"}))
    e = frames.get(ent)
    if e is not None and ent_col in e.columns and "account_id" in e.columns:
        p = e[[ent_col, "account_id", "_source_table", "_source_row"]].dropna(subset=[ent_col, "account_id"])
        parts.append(p.rename(columns={ent_col: "ident"}).assign(txn_id=None))
    if not parts:
        return pd.DataFrame(columns=["ident", "account_id", "_source_table", "_source_row", "txn_id"])
    return pd.concat(parts, ignore_index=True)


@metric("accounts_per_device", "distinct accounts per device identifier")
def _apd(frames, params):
    return identifier_account_pairs(frames, "device").groupby("ident")["account_id"].nunique().to_numpy(dtype=float)


@metric("accounts_per_ip", "distinct accounts per IP address")
def _api(frames, params):
    return identifier_account_pairs(frames, "ip").groupby("ident")["account_id"].nunique().to_numpy(dtype=float)


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


def structuring_threshold(frames: dict[str, pd.DataFrame], params: dict[str, Any]) -> tuple[float | None, str]:
    if params.get("reporting_threshold"):
        return float(params["reporting_threshold"]), "configured reporting_threshold"
    amounts = frames["Transaction"]["amount"].to_numpy(dtype=float)
    cands = [c for c in threshold_clustering(amounts, params["band"])
             if c["ratio_below_above"] and c["ratio_below_above"] >= params["min_clustering_ratio"]]
    if not cands:
        return None, (f"no round mark with below/above ratio >= {params['min_clustering_ratio']} "
                      f"in the amount distribution")
    best = cands[0]
    return float(best["mark"]), (f"detected from amount distribution: {best['below']} txns just below vs "
                                 f"{best['above']} just above {best['mark']:g} (ratio {best['ratio_below_above']})")


def near_threshold_counts(frames: dict[str, pd.DataFrame], params: dict[str, Any], threshold: float) -> pd.DataFrame:
    t = frames["Transaction"]
    near = t[(t["amount"] >= threshold * (1 - params["band"])) & (t["amount"] < threshold)]
    w = int(params["window_days"] * 86400)
    df = pd.DataFrame({"k": near["src_account_id"].to_numpy(), "b": ts_seconds(near["ts"]) // w,
                       "txn_id": near["txn_id"].to_numpy()})
    return df


@metric("near_threshold_count_per_window", "transactions per sending account per window within the band just "
                                           "below the structuring threshold (account-windows with >=1 such txn)")
def _near(frames, params):
    thr, _ = structuring_threshold(frames, params)
    if thr is None:
        return np.array([], dtype=float)
    return near_threshold_counts(frames, params, thr).groupby(["k", "b"]).size().to_numpy(dtype=float)
