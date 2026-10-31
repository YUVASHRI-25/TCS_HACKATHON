"""Unit tests for ingestion on tiny hand-built inputs (no dataset values)."""

import numpy as np
import pandas as pd
import pytest

from trace.ingestion import capabilities as caps
from trace.ingestion.mapping import MappingConfig, apply_mapping
from trace.ingestion.normalise import TimezoneRequired, normalise
from trace.ingestion.profile import degree_profile, profile_table, threshold_clustering
from trace.ingestion.validate import validate


def _raw():
    return pd.DataFrame({
        "_source_row": [0, 1, 2, 3, 4],
        "t": ["2024-01-01 10:00", "2024-01-01 09:00", "bad", "2024-01-02 00:00", "2024-01-02 00:00"],
        "a": ["A1", "A2", "A3", None, None],
        "b": ["A2", "A3", "A1", "A1", "A1"],
        "amt": ["10", "20.5", "x", "5", "5"],
        "id": ["t1", "t2", "t3", "t4", "t4"],
    })


def _cfg(tz="UTC"):
    return MappingConfig.model_validate({
        "source": {"adapter": "csv", "timezone": tz, "tables": {"tx": {"path": "unused.csv"}}},
        "entities": {
            "Transaction": {"table": "tx", "fields": {
                "txn_id": {"status": "direct", "column": "id"},
                "ts": {"status": "direct", "column": "t"},
                "src_account_id": {"status": "direct", "column": "a"},
                "dst_account_id": {"status": "direct", "column": "b"},
                "amount": {"status": "direct", "column": "amt"},
            }},
            "Account": {"derived_from": ["Transaction.src_account_id", "Transaction.dst_account_id"],
                        "fields": {"account_id": {"status": "derived", "derivation": "same_as",
                                                  "params": {"column": "account_id"}}}},
        },
    })


def test_mapping_rejects_unknown_fields():
    with pytest.raises(ValueError):
        MappingConfig.model_validate({"source": {"tables": {"x": {"path": "p"}}},
                                      "entities": {"Transaction": {"table": "x", "fields": {"nope": {"status": "absent"}}}}})


def test_derived_entity_is_tagged_and_keeps_source_ref():
    frames = apply_mapping(_cfg(), {"tx": _raw()})
    acc = frames["Account"]
    assert acc.attrs["derived_entity"] is True
    assert acc["derived"].all()
    assert set(acc["account_id"]) == {"A1", "A2", "A3"}
    assert {"_source_table", "_source_row"} <= set(acc.columns)


def test_naive_timestamps_require_declared_timezone():
    frames = apply_mapping(_cfg(tz=None), {"tx": _raw()})
    with pytest.raises(TimezoneRequired):
        normalise(frames, None)


def test_normalise_records_parse_failures_and_validate_quarantines_with_reasons():
    frames = apply_mapping(_cfg(), {"tx": _raw()})
    frames, issues = normalise(frames, "UTC")
    assert str(frames["Transaction"]["ts"].dt.tz) == "UTC"
    problems = {(i.field, tuple(i.source_rows)) for i in issues}
    assert ("ts", (2,)) in problems and ("amount", (2,)) in problems
    clean, report = validate(frames, issues)
    tx = clean["Transaction"]
    q = report.quarantined["Transaction"]
    # every removed row is accounted for with a reason
    assert report.row_counts["Transaction"]["in"] == len(tx) + len(q)
    assert set(q["reason"]) >= {"exact duplicate"}
    assert q["reason"].notna().all()


def test_capabilities_disable_with_reason():
    rows = {r.id: r for r in caps.capability_table(_cfg())}
    assert rows["cycle"].enabled
    assert not rows["new_account_large_inflow"].enabled
    assert "Account.open_date" in rows["new_account_large_inflow"].reason
    assert not rows["shared_device"].enabled and rows["shared_device"].reason.startswith("Not evaluated")
    assert not rows["entity_resolution"].enabled


def test_capabilities_empty_mapping_disables_everything():
    assert not any(r.enabled for r in caps.capability_table(MappingConfig()))


def test_profile_flags_candidate_key_and_label():
    df = pd.DataFrame({"k": ["a", "b", "c"], "is_fraud": [0, 1, 0], "v": [1.0, 2.0, 3.0]})
    tp = profile_table("t", "p", df)
    assert "k" in tp.candidate_keys
    assert [c["column"] for c in tp.label_candidates] == ["is_fraud"]


def test_degree_profile_counts_distinct_counterparties():
    df = pd.DataFrame({"s": ["A", "A", "A", "B"], "d": ["B", "B", "C", "C"]})
    d = degree_profile(df, "s", "d")
    assert d["distinct_accounts"] == 3 and d["distinct_pairs"] == 3
    assert d["out_degree_distinct_counterparties"]["max"] == 2


def test_threshold_clustering_finds_spike_below_mark():
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.uniform(100, 100000, 5000), rng.uniform(9000, 9999, 800)])
    top = threshold_clustering(x)[0]
    assert top["mark"] == 10000 and top["ratio_below_above"] > 2
