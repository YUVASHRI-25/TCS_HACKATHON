"""Unsupervised IsolationForest over account-level behaviour features.

Output is a MODEL signal (source="model"): capped in scoring, never opens a case alone.
Per-feature explanation: for each flagged account, the features whose percentile rank in the
population is most extreme.

Features (all computed from Transaction only):
  out_count, in_count            number of sent / received transactions
  out_amount, in_amount          total sent / received
  out_degree, in_degree          distinct payees / payers
  mean_out_amount                average sent amount
  active_days                    distinct calendar days with activity
  in_out_ratio                   out_amount / in_amount (0 if no inflow)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from trace.domain.detectors.base import tail_strength
from trace.domain.model.findings import MODEL, Finding, node_id

FEATURES = ["out_count", "in_count", "out_amount", "in_amount", "out_degree", "in_degree",
            "mean_out_amount", "active_days", "in_out_ratio"]


def account_features(txns: pd.DataFrame) -> pd.DataFrame:
    out = txns.groupby("src_account_id").agg(out_count=("txn_id", "size"), out_amount=("amount", "sum"),
                                             out_degree=("dst_account_id", "nunique"))
    inn = txns.groupby("dst_account_id").agg(in_count=("txn_id", "size"), in_amount=("amount", "sum"),
                                             in_degree=("src_account_id", "nunique"))
    days = pd.concat([txns[["src_account_id", "ts"]].rename(columns={"src_account_id": "a"}),
                      txns[["dst_account_id", "ts"]].rename(columns={"dst_account_id": "a"})])
    active = days.assign(d=days["ts"].dt.normalize()).groupby("a")["d"].nunique().rename("active_days")
    f = out.join(inn, how="outer").join(active, how="outer").fillna(0.0)
    f["mean_out_amount"] = np.where(f["out_count"] > 0, f["out_amount"] / f["out_count"].replace(0, 1), 0.0)
    f["in_out_ratio"] = np.where(f["in_amount"] > 0, f["out_amount"] / f["in_amount"].replace(0, 1), 0.0)
    return f[FEATURES]


def score_accounts(txns: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.DataFrame, np.ndarray]:
    f = account_features(txns)
    model = IsolationForest(n_estimators=params["n_estimators"], max_samples=min(params["max_samples"], len(f)),
                            random_state=params["random_state"])
    x = np.log1p(f.to_numpy(dtype=float).clip(min=0))
    model.fit(x)
    scores = -model.score_samples(x)  # higher = more anomalous
    return f.assign(anomaly_score=scores), np.sort(scores)


def anomaly_findings(scored: pd.DataFrame, population: np.ndarray, threshold: float, percentile: float) -> list[Finding]:
    ranks = scored[FEATURES].rank(pct=True)
    out = []
    for acct, r in scored[scored["anomaly_score"] >= threshold].iterrows():
        dev = (ranks.loc[acct] - 0.5).abs().sort_values(ascending=False).head(3)
        expl = [{"feature": k, "value": float(r[k]), "population_percentile": round(float(ranks.loc[acct, k]) * 100, 1)}
                for k in dev.index]
        out.append(Finding(
            type="isolation_forest", detector="isolation_forest", source=MODEL, subjects=(node_id("account", acct),),
            txn_ids=(), strength=tail_strength(r["anomaly_score"], population, percentile),
            details={"account": acct, "anomaly_score": float(r["anomaly_score"]), "threshold": threshold,
                     "top_features": expl, "note": "unsupervised model signal; not evidence on its own"},
            cypher_used="// model signal: IsolationForest over account features (see intelligence/ml/anomaly.py)"))
    return out
