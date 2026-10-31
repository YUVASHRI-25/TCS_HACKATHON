import numpy as np
import pandas as pd

import trace.domain.detectors.cycles  # noqa: F401
import trace.domain.detectors.flow  # noqa: F401
import trace.domain.detectors.identifiers  # noqa: F401
from trace.domain.detectors.base import REGISTRY, DetectorContext, tail_strength
from trace.domain.detectors.thresholds import derive_thresholds

from .helpers import txns


def run(det, frames, params):
    return REGISTRY[det].fn(DetectorContext(frames=frames, params={det: params}))


def test_rapid_pass_through_flags_forwarding_within_window_only():
    t = txns([("t1", "2024-01-01 10:00", "A", "M", 1000),
              ("t2", "2024-01-01 10:05", "M", "B", 950),     # forwarded 95% within 5 min
              ("t3", "2024-01-02 10:00", "C", "N", 1000),
              ("t4", "2024-01-05 10:00", "N", "D", 1000)])   # forwarded, but 3 days later
    res = run("rapid_pass_through", {"Transaction": t}, {"max_gap_minutes": 10, "min_forward_ratio": 0.8})
    assert [f.subjects for f in res.findings] == [("account:M",)]
    f = res.findings[0]
    assert set(f.txn_ids) == {"t1", "t2"} and abs(f.details["mean_forward_ratio"] - 0.95) < 1e-9


def test_rapid_pass_through_ignores_self_transfers():
    t = txns([("t1", "2024-01-01 10:00", "M", "M", 1000)])
    assert run("rapid_pass_through", {"Transaction": t}, {"max_gap_minutes": 10, "min_forward_ratio": 0.8}).findings == []


def test_cycle_requires_time_order_and_similar_amounts():
    ok = txns([("a", "2024-01-01 10:00", "A", "B", 1000), ("b", "2024-01-01 10:10", "B", "C", 980),
               ("c", "2024-01-01 10:20", "C", "A", 960)])
    p = {"min_length": 3, "max_length": 6, "amount_tolerance": 0.1, "max_cycles": 100, "max_span_minutes": 60}
    res = run("cycle", {"Transaction": ok}, p)
    assert len(res.findings) == 1 and set(res.findings[0].subjects) == {"account:A", "account:B", "account:C"}

    backwards = txns([("a", "2024-01-01 10:20", "A", "B", 1000), ("b", "2024-01-01 10:10", "B", "C", 980),
                      ("c", "2024-01-01 10:00", "C", "A", 960)])
    assert run("cycle", {"Transaction": backwards}, p).findings == []
    dissimilar = txns([("a", "2024-01-01 10:00", "A", "B", 1000), ("b", "2024-01-01 10:10", "B", "C", 300),
                       ("c", "2024-01-01 10:20", "C", "A", 960)])
    assert run("cycle", {"Transaction": dissimilar}, p).findings == []


def test_fan_in_counts_distinct_payers_in_window():
    rows = [(f"t{i}", f"2024-01-0{1 + i % 3} 10:00", f"P{i}", "H", 10) for i in range(6)]
    rows += [("x", "2024-01-01 11:00", "P0", "H", 10)]  # repeat payer: not distinct
    res = run("fan_in", {"Transaction": txns(rows)}, {"window_days": 7, "min_counterparties": 5})
    assert len(res.findings) == 1 and res.findings[0].details["distinct_counterparties"] == 6
    assert run("fan_in", {"Transaction": txns(rows)}, {"window_days": 7, "min_counterparties": 6}).findings == []


def test_disabled_threshold_reports_reason_instead_of_guessing():
    res = run("fan_in", {"Transaction": txns([("t", "2024-01-01", "A", "B", 1)])}, {"window_days": 7, "min_counterparties": None})
    assert res.findings == [] and "could not be derived" in res.notes[0]


def test_structuring_uses_configured_threshold_band():
    rows = [(f"s{i}", f"2024-01-01 1{i}:00", "S", f"D{i}", 950 + i) for i in range(5)]
    rows += [("big", "2024-01-01 10:30", "S", "D9", 5000)]
    p = {"reporting_threshold": 1000, "band": 0.1, "min_clustering_ratio": 2, "window_days": 7, "min_count": 4}
    res = run("structuring", {"Transaction": txns(rows)}, p)
    assert len(res.findings) == 1 and res.findings[0].details["near_threshold_txns"] == 5
    assert "big" not in res.findings[0].txn_ids


def test_structuring_not_evaluated_without_threshold_signal():
    rows = [(f"s{i}", "2024-01-01", "S", "D", 10 + i) for i in range(5)]
    p = {"reporting_threshold": None, "band": 0.1, "min_clustering_ratio": 2, "window_days": 7, "min_count": 1}
    res = run("structuring", {"Transaction": txns(rows)}, p)
    assert res.findings == [] and res.notes[0].startswith("Not evaluated")


def test_new_account_large_inflow_needs_open_date_window():
    t = txns([("t1", "2024-01-05", "X", "N", 5000), ("t2", "2024-06-01", "X", "O", 5000)])
    acc = pd.DataFrame({"account_id": ["N", "O"], "open_date": pd.to_datetime(["2024-01-01", "2024-01-01"], utc=True)})
    res = run("new_account_large_inflow", {"Transaction": t, "Account": acc}, {"new_account_days": 30, "min_amount": 1000})
    assert [f.subjects for f in res.findings] == [("account:N",)]


def test_regular_cadence_detects_periodic_similar_payments():
    rows = [(f"p{i}", (pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i)).isoformat(), "EMP", "W", 2000) for i in range(5)]
    res = run("regular_cadence", {"Transaction": txns(rows)}, {"min_occurrences": 4, "max_interval_cv": 0.15, "max_amount_cv": 0.1})
    assert len(res.findings) == 1 and res.findings[0].details["payments"] == 5


def test_shared_device_links_but_never_merges():
    t = txns([("t1", "2024-01-01", "A", "X", 1, {"device_id": "D1"}), ("t2", "2024-01-01", "B", "X", 1, {"device_id": "D1"}),
              ("t3", "2024-01-01", "C", "X", 1, {"device_id": "D2"})])
    res = run("shared_device", {"Transaction": t}, {"min_accounts": 2})
    assert len(res.findings) == 1 and res.findings[0].type == "shared_device_unrelated"
    assert set(res.findings[0].subjects) == {"account:A", "account:B"}
    assert len(res.links) == 1 and res.links[0].kind == "possible_related" and res.links[0].confidence == 0.5


def test_prior_escalation_requires_configured_vocabulary():
    alerts = pd.DataFrame({"alert_id": ["a"], "subject_id": ["A"], "outcome": ["x"], "_source_table": "al", "_source_row": [0]})
    res = run("prior_escalation", {"Transaction": txns([]), "Alert": alerts}, {"escalated_outcomes": []})
    assert res.findings == [] and "not configured" in res.notes[0]


def test_thresholds_are_percentiles_of_population_with_derivation():
    rows = [(f"t{i}", f"2024-01-{1 + i:02d}", f"P{i}", "H", float(i + 1)) for i in range(20)]
    cfg = {"new_account_large_inflow": {"params": {"new_account_days": 30},
                                        "derive": {"min_amount": {"metric": "inflow_amount", "percentile": 50}}}}
    derived, pops = derive_thresholds(cfg, {"Transaction": txns(rows)}, {"new_account_large_inflow"})
    entry = derived["new_account_large_inflow"]["min_amount"]
    assert entry["value"] == np.percentile(np.arange(1, 21), 50)
    assert "p50 of inflow_amount" in entry["derivation"] and entry["population_size"] == 20


def test_tail_strength_is_bounded_and_monotonic():
    pop = np.arange(100, dtype=float)
    vals = [tail_strength(v, pop, 90) for v in (50, 90, 95, 99, 1000)]
    assert vals == sorted(vals) and 0.5 <= vals[0] and vals[-1] == 1.0
