"""Relationship graph over the canonical frames.

Nodes: one per entity present in the data (account, customer, merchant, device, ip, location,
beneficiary, complaint, watchlist_entry, prior_alert). Edges: OWNS, USES_DEVICE, LOGGED_FROM_IP,
TRANSFERS_TO (aggregated per pair; txn-level rows stay in the Transaction frame), PAID_MERCHANT,
LOCATED_IN, COMPLAINT_ABOUT, PRIOR_ALERT_ON, POSSIBLE_SAME_ENTITY, SCREENED_AGAINST, POSSIBLE_RELATED.
Every node/edge carries a reference to a raw source record (`source`).
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from trace.domain.detectors.population import identifier_account_pairs
from trace.domain.model.findings import Link, node_id

_ENTITY_NODES = {
    "Customer": ("customer", "customer_id"),
    "Account": ("account", "account_id"),
    "Merchant": ("merchant", "merchant_id"),
    "Device": ("device", "device_id"),
    "IP": ("ip", "ip_id"),
    "Location": ("location", "location_id"),
    "Beneficiary": ("beneficiary", "beneficiary_id"),
    "Complaint": ("complaint", "complaint_id"),
    "WatchlistEntry": ("watchlist_entry", "entry_id"),
    "Alert": ("prior_alert", "alert_id"),
    "PriorCase": ("prior_case", "case_id"),
}


def _src(row) -> dict[str, Any]:
    return {"table": row["_source_table"], "row": int(row["_source_row"])}


class TraceGraph:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.g = nx.MultiDiGraph()
        self._build()

    # ----------------------------------------------------------------------------------- build
    def _add_node(self, nid: str, kind: str, source: dict, derived: bool, **attrs) -> None:
        if nid not in self.g:
            self.g.add_node(nid, type=kind, source=source, derived=derived, **attrs)

    def _build(self) -> None:
        f = self.frames
        for ent, (kind, key) in _ENTITY_NODES.items():
            df = f.get(ent)
            if df is None or key not in df.columns:
                continue
            derived = bool(df.attrs.get("derived_entity"))
            for row in df.dropna(subset=[key]).drop_duplicates(subset=[key]).to_dict("records"):
                self._add_node(node_id(kind, row[key]), kind, _src(row), derived)

        acc = f.get("Account")
        if acc is not None and "customer_id" in acc.columns:
            for r in acc.dropna(subset=["customer_id"]).to_dict("records"):
                self.g.add_edge(node_id("customer", r["customer_id"]), node_id("account", r["account_id"]),
                                type="OWNS", source=_src(r),
                                derived="customer_id" in acc.attrs.get("derived_fields", []))

        t = f.get("Transaction")
        if t is not None:
            agg = t.groupby(["src_account_id", "dst_account_id"]).agg(
                n=("txn_id", "size"), amount=("amount", "sum"), first_ts=("ts", "min"), last_ts=("ts", "max"),
                _source_table=("_source_table", "first"), _source_row=("_source_row", "first")).reset_index()
            for r in agg.to_dict("records"):
                a, b = node_id("account", r["src_account_id"]), node_id("account", r["dst_account_id"])
                for n in (a, b):
                    self._add_node(n, "account", _src(r), True)
                self.g.add_edge(a, b, type="TRANSFERS_TO", n_txns=int(r["n"]), amount=float(r["amount"]),
                                first_ts=str(r["first_ts"]), last_ts=str(r["last_ts"]), source=_src(r))
            for col, kind, etype in (("merchant_id", "merchant", "PAID_MERCHANT"), ("location_id", "location", "LOCATED_IN"),
                                     ("beneficiary_id", "beneficiary", "TRANSFERS_TO_BENEFICIARY")):
                if col not in t.columns:
                    continue
                pairs = t.dropna(subset=[col]).drop_duplicates(subset=["src_account_id", col])
                for r in pairs.to_dict("records"):
                    other = node_id(kind, r[col])
                    self._add_node(other, kind, _src(r), False)
                    self.g.add_edge(node_id("account", r["src_account_id"]), other, type=etype, source=_src(r))

        # Device / IP usage at account level (customer-level usage expanded through account ownership).
        for ident, kind, etype in (("device", "device", "USES_DEVICE"), ("ip", "ip", "LOGGED_FROM_IP")):
            pairs = identifier_account_pairs(f, ident).drop_duplicates(subset=["ident", "account_id", "_source_table"])
            for r in pairs.to_dict("records"):
                target = node_id(kind, r["ident"])
                self._add_node(target, kind, _src(r), False)
                self.g.add_edge(node_id("account", r["account_id"]), target, type=etype, source=_src(r),
                                via=r["_source_table"])

        acc_of: dict = {}
        if acc is not None and "customer_id" in acc.columns:
            for a, c in zip(acc["account_id"], acc["customer_id"]):
                acc_of.setdefault(c, []).append(a)

        def subject_nodes(raw, stype=None):
            kind = str(stype).lower() if isinstance(stype, str) and stype else None
            if kind in (None, "account") and node_id("account", raw) in self.g:
                return [node_id("account", raw)]
            if raw in acc_of:
                return [node_id("customer", raw)]
            return [node_id(kind or "entity", raw)] if node_id(kind or "entity", raw) in self.g else []

        for ent, kind, etype in (("Complaint", "complaint", "COMPLAINT_ABOUT"), ("Alert", "prior_alert", "PRIOR_ALERT_ON")):
            df = f.get(ent)
            key = _ENTITY_NODES[ent][1]
            if df is not None and "subject_id" in df.columns:
                for r in df.dropna(subset=[key, "subject_id"]).to_dict("records"):
                    for target in subject_nodes(r["subject_id"], r.get("subject_type")):
                        self.g.add_edge(node_id(kind, r[key]), target, type=etype, source=_src(r))

        pc = f.get("PriorCase")
        if pc is not None and "alert_id" in pc.columns:
            for r in pc.dropna(subset=["alert_id"]).to_dict("records"):
                if node_id("prior_alert", r["alert_id"]) in self.g:
                    self.g.add_edge(node_id("prior_case", r["case_id"]), node_id("prior_alert", r["alert_id"]),
                                    type="OPENED_FROM", source=_src(r), status=r.get("status"))

        rel = f.get("Relationship")
        if rel is not None:
            for r in rel.dropna(subset=["entity_1_id", "entity_2_id"]).to_dict("records"):
                a, b = subject_nodes(r["entity_1_id"]), subject_nodes(r["entity_2_id"])
                if a and b:
                    self.g.add_edge(a[0], b[0], type="DECLARED_RELATIONSHIP", source=_src(r),
                                    relationship_type=r.get("relationship_type"))

        sm = f.get("ScreeningMatch")
        if sm is not None:
            for r in sm.dropna(subset=["entity_id"]).to_dict("records"):
                target = node_id("watchlist_entry", r["entity_id"])
                self._add_node(target, "watchlist_entry", _src(r), False, list_type=r.get("list_type"))
                for n in subject_nodes(r["entity_id"]):
                    self.g.add_edge(n, target, type="SCREENED_AGAINST", source=_src(r), match_type=r.get("match_type"))

    def add_links(self, links: list[Link]) -> None:
        for ln in links:
            etype = "POSSIBLE_SAME_ENTITY" if ln.kind == "possible_same_entity" else "POSSIBLE_RELATED"
            if ln.a in self.g and ln.b in self.g:
                self.g.add_edge(ln.a, ln.b, type=etype, confidence=ln.confidence, reasons=ln.reasons,
                                source=ln.source_rows[0] if ln.source_rows else None)

    # --------------------------------------------------------------------------------- helpers
    def neighbors(self, nid: str, hops: int = 1) -> set[str]:
        if nid not in self.g:
            return set()
        und = self.g.to_undirected(as_view=True)
        return set(nx.single_source_shortest_path_length(und, nid, cutoff=hops))

    def get_transactions(self, accounts: set[str] | list[str], internal_only: bool = True) -> pd.DataFrame:
        t = self.frames.get("Transaction")
        if t is None:
            return pd.DataFrame()
        raw = {a.split(":", 1)[1] for a in accounts}
        if internal_only:
            return t[t["src_account_id"].isin(raw) & t["dst_account_id"].isin(raw)]
        return t[t["src_account_id"].isin(raw) | t["dst_account_id"].isin(raw)]

    def shared_identifiers(self, nid: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for _, ident, d in self.g.out_edges(nid, data=True):
            if d["type"] in ("USES_DEVICE", "LOGGED_FROM_IP"):
                others = [u for u, _, dd in self.g.in_edges(ident, data=True) if dd["type"] == d["type"] and u != nid]
                if others:
                    out[ident] = sorted(set(others))
        return out

    def node(self, nid: str) -> dict[str, Any] | None:
        return dict(self.g.nodes[nid]) if nid in self.g else None

    def account_pairs(self) -> set[tuple[str, str]]:
        return {(u, v) for u, v, d in self.g.edges(data=True) if d["type"] == "TRANSFERS_TO"}
