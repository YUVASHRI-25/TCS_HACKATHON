"""Tiny hand-built canonical frames for pure domain tests. Never imported by app code."""

import pandas as pd


def txns(rows):
    """rows: (txn_id, iso_ts, src, dst, amount[, extra dict])"""
    recs = []
    for i, r in enumerate(rows):
        rec = {"txn_id": r[0], "ts": pd.Timestamp(r[1], tz="UTC"), "src_account_id": r[2], "dst_account_id": r[3],
               "amount": float(r[4]), "_source_table": "tx", "_source_row": i}
        if len(r) > 5:
            rec.update(r[5])
        recs.append(rec)
    return pd.DataFrame(recs)
