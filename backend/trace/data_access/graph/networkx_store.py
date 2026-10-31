"""NetworkX graph store (default backend). Neo4j can be added behind the same port."""

from __future__ import annotations

from typing import Any

import pandas as pd

from trace.data_access.ports import GraphStore
from trace.intelligence.graph_analytics.graph import TraceGraph


class NetworkxGraphStore(GraphStore):
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.tg = TraceGraph(frames) if "Transaction" in frames else None

    def neighbors(self, node_id: str, hops: int) -> dict[str, Any]:
        if self.tg is None or node_id not in self.tg.g:
            return {"nodes": [], "edges": []}
        ids = self.tg.neighbors(node_id, hops)
        sub = self.tg.g.subgraph(ids)
        nodes = [{"id": n, **{k: v for k, v in d.items()}} for n, d in sub.nodes(data=True)]
        edges = [{"source": u, "target": v, **d} for u, v, d in sub.edges(data=True)]
        return {"nodes": nodes, "edges": edges}

    def search(self, q: str, limit: int = 20) -> list[dict[str, Any]]:
        if self.tg is None:
            return []
        ql = q.lower()
        out = []
        for n, d in self.tg.g.nodes(data=True):
            if ql in n.lower():
                out.append({"id": n, "type": d.get("type"), "derived": d.get("derived", False)})
                if len(out) >= limit:
                    break
        return out
