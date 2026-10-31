"""Derive detector thresholds from the dataset's own distributions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trace.domain.detectors.population import METRIC_DOC, METRICS


def derive_thresholds(detector_cfg: dict[str, dict[str, Any]], frames: dict[str, pd.DataFrame],
                      enabled: set[str], extra_populations: dict[str, np.ndarray] | None = None
                      ) -> tuple[dict[str, dict[str, Any]], dict[str, np.ndarray]]:
    """Returns ({detector: {param: {value, derivation, population_size}}}, {pop_key: sorted population}).

    Detectors that are disabled are skipped. A threshold whose population is empty is recorded with
    value None and the reason, and its detector will not run.
    """
    out: dict[str, dict[str, Any]] = {}
    pops: dict[str, np.ndarray] = {}
    for det, spec in detector_cfg.items():
        if det not in enabled:
            continue
        params = spec.get("params") or {}
        for pname, d in (spec.get("derive") or {}).items():
            mname, pct = d["metric"], float(d["percentile"])
            if extra_populations and mname in extra_populations:
                pop = extra_populations[mname]
            elif mname in METRICS:
                pop = METRICS[mname](frames, params)
            else:
                continue  # model-produced metric not yet available; derived later by its producer
            pop = np.sort(pop[np.isfinite(pop)])
            pops[f"{det}.{pname}"] = pop
            entry: dict[str, Any] = {"metric": mname, "percentile": pct, "population_size": int(len(pop))}
            if len(pop) == 0:
                entry |= {"value": None, "derivation": f"population '{mname}' is empty on this dataset"}
            else:
                value = float(np.percentile(pop, pct))
                mult = d.get("multiply_by_param")
                note = f"p{pct:g} of {mname} ({METRIC_DOC.get(mname, mname)}; n={len(pop):,})"
                if value == pop[-1]:
                    note += "; percentile equals the population maximum, so nothing on this dataset exceeds it"
                if mult:
                    value *= float(params[mult])
                    note += f" x {mult}={params[mult]}"
                entry |= {"value": value, "derivation": note}
            out.setdefault(det, {})[pname] = entry
    return out, pops


def merged_params(detector_cfg: dict[str, dict[str, Any]], derived: dict[str, dict[str, Any]]) -> dict[str, dict]:
    merged = {}
    for det, spec in detector_cfg.items():
        p = dict(spec.get("params") or {})
        for pname, entry in derived.get(det, {}).items():
            p[pname] = entry["value"]
            p[f"_{pname}_percentile"] = entry["percentile"]
        merged[det] = p
    return merged
