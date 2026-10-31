"""Detector plumbing: context, registry, time helpers and data-derived strength.

Detectors are deterministic functions of the canonical frames and their (merged) parameters.
Parameters = analyst params from config + thresholds derived from the data (see thresholds.py).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from trace.domain.model.findings import Finding, Link, node_id

EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


@dataclass
class DetectorContext:
    frames: dict[str, pd.DataFrame]
    params: dict[str, dict[str, Any]]
    links: list[Link] = field(default_factory=list)
    populations: dict[str, np.ndarray] = field(default_factory=dict)  # sorted metric populations
    _owner: dict | None = field(default=None, repr=False)
    _acct_ids: set = field(default_factory=set, repr=False)
    _cust_ids: set = field(default_factory=set, repr=False)

    @property
    def txns(self) -> pd.DataFrame:
        return self.frames["Transaction"]

    def p(self, detector: str) -> dict[str, Any]:
        return self.params.get(detector, {})

    def entity_nodes(self, raw_id: Any, kind_hint: str | None = None) -> tuple[str, ...]:
        """Resolve any entity id to network nodes: an account stays an account; a customer becomes the
        customer's accounts (via Account.customer_id); anything else stays as its own node."""
        if self._owner is None:
            acc = self.frames.get("Account")
            self._acct_ids = set(acc["account_id"]) if acc is not None else set()
            self._owner = {}
            if acc is not None and "customer_id" in acc.columns:
                for a, c in zip(acc["account_id"], acc["customer_id"]):
                    if pd.notna(c):
                        self._owner.setdefault(c, []).append(a)
            cust = self.frames.get("Customer")
            self._cust_ids = set(cust["customer_id"]) if cust is not None else set(self._owner)
        if raw_id in self._acct_ids or kind_hint == "account":
            return (node_id("account", raw_id),)
        if raw_id in self._owner:
            return tuple(node_id("account", a) for a in sorted(self._owner[raw_id]))
        if raw_id in self._cust_ids or kind_hint == "customer":
            return (node_id("customer", raw_id),)
        return (node_id(kind_hint or "entity", raw_id),)

    def has(self, entity: str, *fields: str) -> bool:
        df = self.frames.get(entity)
        return df is not None and all(f in df.columns and df[f].notna().any() for f in fields)


@dataclass
class DetectorResult:
    findings: list[Finding]
    notes: list[str] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


DetectorFn = Callable[[DetectorContext], DetectorResult]


@dataclass(frozen=True)
class DetectorSpec:
    id: str
    finding_type: str
    fn: DetectorFn


REGISTRY: dict[str, DetectorSpec] = {}


def register(detector_id: str, finding_type: str | None = None) -> Callable[[DetectorFn], DetectorFn]:
    def deco(fn: DetectorFn) -> DetectorFn:
        REGISTRY[detector_id] = DetectorSpec(detector_id, finding_type or detector_id, fn)
        return fn
    return deco


def ts_seconds(s: pd.Series) -> np.ndarray:
    return ((s - EPOCH) // pd.Timedelta("1s")).to_numpy(dtype=np.int64)


def tail_strength(value: float, population: np.ndarray | None, percentile: float | None) -> float:
    """Strength in [0.5, 1] from where `value` sits in the data's own population above the
    threshold percentile. 0.5 = just at the threshold, 1 = top of the observed distribution."""
    if population is None or len(population) == 0 or percentile is None:
        return 0.5
    q = percentile / 100.0
    rank = np.searchsorted(population, value, side="right") / len(population)
    if q >= 1:
        return 1.0
    return float(0.5 + 0.5 * np.clip((rank - q) / (1 - q), 0, 1))


def cap_list(values, n: int = 50) -> list:
    out = list(dict.fromkeys(values))
    return out[:n]


def fmt_cypher(template: str, **params: Any) -> str:
    rendered = template
    for k, v in params.items():
        rendered = rendered.replace(f"${k}", repr(v) if isinstance(v, str) else f"{v}")
    return rendered
