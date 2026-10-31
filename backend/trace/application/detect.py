"""Detection use case: derive thresholds, run every ENABLED detector, resolver and model."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

import trace.domain.detectors.cycles  # noqa: F401  (registers detectors)
import trace.domain.detectors.flow  # noqa: F401
import trace.domain.detectors.identifiers  # noqa: F401
from trace.domain.detectors.base import REGISTRY, DetectorContext
from trace.domain.detectors.thresholds import derive_thresholds, merged_params
from trace.domain.model.findings import Finding, Link
from trace.intelligence.ml.anomaly import anomaly_findings, score_accounts
from trace.intelligence.resolution.resolver import (accounts_by_customer, links_to_findings, resolve,
                                                    sanctions_matches)

log = logging.getLogger(__name__)


@dataclass
class DetectionOutput:
    findings: list[Finding] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    status: dict[str, dict[str, Any]] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    populations: dict[str, np.ndarray] = field(default_factory=dict)


def run_detection(frames: dict[str, pd.DataFrame], det_cfg: dict[str, Any], enabled: set[str]) -> DetectionOutput:
    out = DetectionOutput()
    dcfg = det_cfg.get("detectors") or {}
    out.thresholds, out.populations = derive_thresholds(dcfg, frames, enabled)
    params = merged_params(dcfg, out.thresholds)
    ctx = DetectorContext(frames=frames, params=params, populations=out.populations)

    def record(det: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001 - one detector failing must be visible, not fatal
            log.exception("detector %s failed", det)
            out.status[det] = {"status": "error", "findings": 0, "notes": [f"{type(e).__name__}: {e}"]}
            return
        findings, notes, links = res
        out.findings += findings
        out.links += links
        out.status[det] = {"status": "ran", "findings": len(findings), "notes": notes,
                           "seconds": round(time.perf_counter() - t0, 2)}

    for det, spec in REGISTRY.items():
        if det not in enabled:
            out.status[det] = {"status": "disabled", "findings": 0, "notes": []}
            continue
        record(det, lambda spec=spec: (lambda r: (r.findings, r.notes, r.links))(spec.fn(ctx)))

    accounts_of = accounts_by_customer(frames.get("Account"))
    if "entity_resolution" in enabled:
        def _er():
            links, notes = resolve(frames["Customer"], det_cfg["resolution"])
            return links_to_findings(links, accounts_of), notes, links
        record("entity_resolution", _er)
    wl = frames.get("WatchlistEntry")
    if "sanctions_potential_match" in enabled and wl is not None and "name" in wl.columns and \
            "name" in frames.get("Customer", pd.DataFrame()).columns:
        p = params.get("sanctions_potential_match", {})
        record("sanctions_name_match", lambda: (
            sanctions_matches(frames["Customer"], wl, p["min_name_score"], accounts_of), [], []))
    if "isolation_forest" in enabled:
        p = params.get("isolation_forest", {})
        spec = (dcfg.get("isolation_forest", {}).get("derive") or {}).get("min_score")

        def _if():
            scored, pop = score_accounts(frames["Transaction"], p)
            thr = float(np.percentile(pop, spec["percentile"]))
            out.thresholds.setdefault("isolation_forest", {})["min_score"] = {
                "metric": "anomaly_score", "percentile": spec["percentile"], "population_size": int(len(pop)),
                "value": thr, "derivation": f"p{spec['percentile']:g} of IsolationForest anomaly scores over "
                                            f"{len(pop):,} accounts (unsupervised, fitted on the full dataset)"}
            out.populations["isolation_forest.min_score"] = pop
            return anomaly_findings(scored, pop, thr, spec["percentile"]), [], []
        record("isolation_forest", _if)
    return out
