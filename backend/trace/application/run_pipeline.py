"""Pipeline use case: ingest -> validate -> resolve -> graph -> detect -> cases -> persist.

Idempotent: processed outputs and the case table are fully rewritten each run; the audit log is
append-only and survives re-runs (case ids are deterministic, so review history stays attached).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import numpy as np
import pandas as pd

from trace.application.build_cases import TxnIndex, build_case
from trace.application.detect import run_detection
from trace.application.review import reapply_reviews
from trace.domain.scoring.score import ScoringConfig
from trace.infrastructure.config import load_config, write_thresholds
from trace.infrastructure.container import Container, get_container
from trace.infrastructure.settings import REPO_ROOT
from trace.ingestion import capabilities as caps
from trace.ingestion.mapping import apply_mapping, build_adapter, load_mapping
from trace.ingestion.normalise import normalise
from trace.ingestion.validate import validate
from trace.intelligence.graph_analytics.graph import TraceGraph
from trace.intelligence.graph_analytics.networks import group

log = logging.getLogger(__name__)


class MappingNotConfigured(RuntimeError):
    pass


class ConfigInvalid(RuntimeError):
    pass


def _label_report(frames: dict[str, pd.DataFrame], case_dicts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """REPORT ONLY. Never used to tune anything."""
    t = frames.get("Transaction")
    if t is None or "label" not in t.columns or not t["label"].notna().any():
        return None
    pos_txn = t[t["label"].fillna(False).astype(bool)]
    positives = set(pos_txn["src_account_id"]) | set(pos_txn["dst_account_id"])
    surfaced = [{e["raw_id"] for e in c["entities"] if e["role"] == "member" and e["type"] == "account"} for c in case_dicts]
    all_members = set().union(*surfaced) if surfaced else set()
    out: dict[str, Any] = {
        "note": "Report only. Labels were not used to set any threshold or weight.",
        "label_definition": "account appears as sender or receiver of at least one labelled-positive transaction",
        "labelled_positive_accounts": len(positives),
        "positive_accounts_in_surfaced_networks": len(positives & all_members),
        "share_of_positive_accounts_surfaced": round(len(positives & all_members) / len(positives), 4) if positives else None,
        "member_precision": round(len(positives & all_members) / len(all_members), 4) if all_members else None,
        "precision_at_k": {},
    }
    for k in (10, 25, 50, 100):
        top = surfaced[:k]
        if len(top) < k:
            break
        out["precision_at_k"][str(k)] = round(sum(1 for m in top if m & positives) / k, 4)
    return out


def suspicious_pairs(findings, tx: TxnIndex, roles: dict[str, str]) -> set[tuple[str, str]]:
    """Account pairs joined by a transaction that a deterministic risk finding cites. Ordinary history
    between two flagged accounts does not join them into one network."""
    ids = {t for f in findings if f.source == "deterministic" and roles.get(f.type) == "risk" for t in f.txn_ids}
    rows = tx.rows(ids)
    if rows.empty:
        return set()
    return {(f"account:{s}", f"account:{d}") for s, d in zip(rows["src_account_id"], rows["dst_account_id"])}


def run(container: Container | None = None) -> dict[str, Any]:
    c = container or get_container()
    s = c.settings
    t0 = time.perf_counter()
    mapping = load_mapping(s.path(s.trace_mapping_path))
    if mapping.is_empty:
        raise MappingNotConfigured(
            f"{s.trace_mapping_path} has no source tables/entities yet. Profile the dataset and fill the mapping first.")
    cfg = load_config(s)
    if (problems := cfg.validate()):
        raise ConfigInvalid("; ".join(problems))

    out_dir = s.path(s.trace_processed_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.parquet"):
        old.unlink()

    # ---- ingest / normalise / validate
    raw = build_adapter(mapping, REPO_ROOT).load_all()
    for name, df in raw.items():
        df.astype({c: "string" for c in df.columns if df[c].dtype == object}).to_parquet(out_dir / f"raw_{name}.parquet", index=False)
    frames = apply_mapping(mapping, raw)
    frames, issues = normalise(frames, mapping.source.timezone)
    frames, vreport = validate(frames, issues)
    if "Transaction" in frames:
        frames["Transaction"] = frames["Transaction"].sort_values(["ts", "_source_row"], kind="stable").reset_index(drop=True)
    derived_fields = {e: list(df.attrs.get("derived_fields", [])) for e, df in frames.items()}

    cap_rows = [r.to_dict() for r in caps.capability_table(mapping)]
    enabled = {r["id"] for r in cap_rows if r["enabled"]}
    (out_dir / "validation_report.json").write_text(json.dumps(vreport.to_dict(), indent=2), encoding="utf-8")
    (out_dir / "capabilities.json").write_text(json.dumps(cap_rows, indent=2), encoding="utf-8")
    for entity, q in vreport.quarantined.items():
        q.to_csv(out_dir / f"quarantine_{entity}.csv", index=False)
    for entity, df in frames.items():
        df.to_parquet(out_dir / f"{entity}.parquet", index=False)
    (out_dir / "derived_fields.json").write_text(json.dumps(derived_fields, indent=2), encoding="utf-8")
    if "Transaction" not in frames:
        raise MappingNotConfigured("mapping has no Transaction entity; TRACE needs transactions to build networks")

    # ---- detect (thresholds derived inside), resolve, graph
    det = run_detection(frames, cfg.detectors, enabled)
    write_thresholds(det.thresholds, s)
    tg = TraceGraph(frames)
    tg.add_links(det.links)

    # ---- networks and cases
    cr = cfg.detectors["case_rules"]
    tx = TxnIndex(frames["Transaction"])
    kept, dropped, grouping = group(det.findings, suspicious_pairs(det.findings, tx, cfg.roles), cfg.roles,
                                    cr["max_network_size"], cr["min_deterministic_finding_types"])
    scfg = ScoringConfig.from_dict(cfg.detectors)
    built = [build_case(n, frames, tx, scfg, cfg.catalogues, cap_rows, derived_fields, tg.node) for n in kept]
    built.sort(key=lambda x: -x.priority_score)
    case_dicts = [b.to_dict() for b in built]
    case_dicts = reapply_reviews(case_dicts, c.audit)

    scores = np.array([d["priority_score"] for d in case_dicts], dtype=float)
    finding_counts: dict[str, int] = {}
    for f in det.findings:
        finding_counts[f.type] = finding_counts.get(f.type, 0) + 1
    summary = {
        "row_counts": vreport.row_counts, "validation_ok": vreport.ok,
        "capabilities": cap_rows, "detector_status": det.status, "finding_counts": finding_counts,
        "thresholds": det.thresholds, "grouping": vars(grouping),
        "tiers": {t: int(sum(1 for d in case_dicts if d["tier"] == t)) for t in ("HIGH", "MEDIUM", "LOW")},
        "score_distribution": ({f"p{q}": float(np.percentile(scores, q)) for q in (0, 25, 50, 75, 90, 100)}
                               if len(scores) else {}),
        "exposure_total": float(sum(d["exposure"]["total"] for d in case_dicts)),
        "too_few_cases_warning": (None if case_dicts else
                                  f"No network met min_deterministic_finding_types={cr['min_deterministic_finding_types']}. "
                                  "Reported, not lowered."),
        "label_report": _label_report(frames, case_dicts),
        "seconds": round(time.perf_counter() - t0, 1),
    }
    run_id = c.cases.replace_all(summary, case_dicts)
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    c.reset_cache()
    return {"run_id": run_id, **{k: summary[k] for k in ("row_counts", "tiers", "grouping", "finding_counts",
                                                         "too_few_cases_warning", "seconds")}}
