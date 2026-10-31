"""Deterministic evidence descriptions from finding details. Wording is guardrail-safe."""

from __future__ import annotations

from typing import Any

from trace.domain.guardrails.policy import assert_clean
from trace.domain.model.findings import Finding


def _n(x: Any) -> str:
    try:
        return f"{float(x):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(x)


def describe(f: Finding) -> str:
    d = f.details
    t = f.type
    if t == "rapid_pass_through":
        s = (f"Account {d['account']} forwarded {_n(d['forwarded_total'])} of {_n(d['inflow_total'])} received "
             f"across {d['events']} inflow(s), on average {d['mean_forward_ratio']:.0%} within {_n(d['max_gap_minutes'])} minutes.")
    elif t == "cycle":
        s = (f"Funds moved in a {d['length']}-account loop ({' -> '.join(map(str, d['accounts']))} -> {d['accounts'][0]}) "
             f"within {_n(d['span_minutes'])} minutes, hop amounts within {d['amount_spread']:.0%} of each other.")
    elif t in ("fan_in", "fan_out"):
        role = "payers into" if t == "fan_in" else "payees from"
        s = (f"{d['distinct_counterparties']} distinct {role} account {d['account']} in a {_n(d['window_days'])}-day window "
             f"starting {d['window_start']} (dataset threshold {_n(d['threshold'])}).")
    elif t == "burst_velocity":
        s = (f"Account {d['account']} sent {d['txns_in_window']} transactions within {_n(d['window_minutes'])} minutes "
             f"(dataset threshold {_n(d['threshold'])}).")
    elif t == "new_account_large_inflow":
        s = (f"Account {d['account']} (opened {d['open_date']}) received {d['inflows']} inflow(s) totalling "
             f"{_n(d['inflow_total'])} within {_n(d['new_account_days'])} days of opening; largest {_n(d['largest_inflow'])}.")
    elif t == "structuring":
        s = (f"Account {d['account']} sent {d['near_threshold_txns']} transactions just below {_n(d['threshold'])} "
             f"in a {_n(d['window_days'])}-day window ({d['threshold_source']}).")
    elif t == "regular_cadence":
        s = (f"{d['payments']} payments from {d['src']} to {d['dst']} roughly every {_n(d['mean_interval_days'])} days "
             f"with similar amounts (mean {_n(d['mean_amount'])}).")
    elif t in ("shared_device_unrelated", "shared_ip"):
        what = "device" if t == "shared_device_unrelated" else "IP address"
        key = "device" if t == "shared_device_unrelated" else "ip"
        s = (f"{what.capitalize()} {d[key]} is used by {d['n_accounts']} accounts of {d['n_holders']} different holders"
             + (" (holders derived one-per-account)" if d.get("holders_derived") else "") + "; possible related link only.")
    elif t == "flagged_merchant":
        s = f"Account {d['account']} made {d['payments']} payment(s) totalling {_n(d['amount_total'])} to flagged merchant(s)."
    elif t == "complaint_cluster":
        cats = f" ({', '.join(map(str, d['categories']))})" if d.get("categories") else ""
        s = (f"{d['complaints']} complaints{cats} about {d['subject']} within one window "
             f"(dataset threshold {_n(d['threshold'])}).")
    elif t == "prior_escalation":
        rules = f" (alert rules: {', '.join(map(str, d['rules']))})" if d.get("rules") else ""
        s = f"{d['subject']} has {len(d['alerts'])} prior alert(s){rules}: {'; '.join(map(str, d['reasons']))}."
    elif t == "sanctions_potential_match" and "entity" in d:
        conf = f", highest confidence {d['max_confidence']:.2f}" if d.get("max_confidence") is not None else ""
        s = (f"{d['entity']} has {len(d['matches'])} screening hit(s) on {', '.join(map(str, d['list_types']))} "
             f"(match type {', '.join(map(str, d['match_types'])) or 'n/a'}{conf}); potential match requiring human review.")
    elif t == "sanctions_potential_match":
        s = (f"Customer {d['customer']} name is a potential match (score {d['name_score']:.0f}) to watchlist entry "
             f"{d['watchlist_entry']}; potential match requiring human review.")
    elif t == "possible_same_entity":
        s = (f"Customers {d['customers'][0]} and {d['customers'][1]} may be the same person "
             f"({'; '.join(d['reasons'])}; confidence {d['confidence']:.2f}). Records are not merged.")
    elif t == "isolation_forest":
        feats = ", ".join(f"{x['feature']} at p{x['population_percentile']:g}" for x in d["top_features"])
        s = f"Model signal: account {d['account']} behaviour is unusual for this dataset ({feats})."
    else:
        s = f"{t} finding."
    return assert_clean(s)
