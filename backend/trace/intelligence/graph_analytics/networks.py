"""Group findings into candidate networks.

Nodes are the SUBJECTS of risk and model findings. Two subjects are joined when they appear in the
same finding or when money moved directly between them. Connected components larger than
max_network_size are split with Louvain (seeded, deterministic). Context findings (e.g. regular
cadence) never join subjects; they are attached to networks they overlap, for alternative reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from trace.domain.model.findings import DETERMINISTIC, Finding


@dataclass
class Network:
    members: set[str]
    findings: list[Finding] = field(default_factory=list)
    context: list[Finding] = field(default_factory=list)

    def deterministic_types(self, roles: dict[str, str]) -> set[str]:
        return {f.type for f in self.findings if f.source == DETERMINISTIC and roles.get(f.type) == "risk"}


@dataclass
class GroupingReport:
    components: int
    split_components: int
    candidate_networks: int
    kept: int
    dropped_too_few_types: int
    dropped_model_only: int


def group(findings: list[Finding], transfer_pairs: set[tuple[str, str]], roles: dict[str, str],
          max_size: int, min_types: int, joins: set[str] | None = None
          ) -> tuple[list[Network], list[Network], GroupingReport]:
    """joins: signal types allowed to link accounts into a network (default: all risk/model signals).
    Other risk/model findings attach to the networks their subjects already belong to."""
    scored = [f for f in findings if roles.get(f.type) in ("risk", "model")]
    joining = [f for f in scored if joins is None or f.type in joins]
    attaching = [f for f in scored if joins is not None and f.type not in joins]
    context = [f for f in findings if roles.get(f.type) == "context"]
    # Built in sorted order so components and Louvain communities do not depend on hash ordering.
    edges: set[tuple[str, str]] = set()
    nodes: set[str] = set()
    for f in joining:
        subs = list(f.subjects)
        nodes.update(subs)
        edges.update(tuple(sorted((subs[0], x))) for x in subs[1:] if x != subs[0])
    edges.update(tuple(sorted((u, v))) for u, v in transfer_pairs if u in nodes and v in nodes and u != v)
    g = nx.Graph()
    g.add_nodes_from(sorted(nodes))
    g.add_edges_from(sorted(edges))

    groups: list[set[str]] = []
    comps = sorted((set(c) for c in nx.connected_components(g)), key=min)
    split = 0
    for comp in comps:
        if len(comp) > max_size:
            split += 1
            h = nx.Graph()
            h.add_nodes_from(sorted(comp))
            h.add_edges_from(sorted(e for e in edges if e[0] in comp))
            groups.extend(sorted((set(x) for x in nx.community.louvain_communities(h, seed=0)), key=min))
        else:
            groups.append(comp)

    nets = [Network(members=m) for m in groups]
    owner: dict[str, int] = {n: i for i, net in enumerate(nets) for n in net.members}
    for f in joining + attaching:
        for i in sorted({owner[s] for s in f.subjects if s in owner}):
            nets[i].findings.append(f)
    for f in context:
        for i in sorted({owner[s] for s in f.subjects if s in owner}):
            nets[i].context.append(f)

    kept, dropped = [], []
    model_only = 0
    for net in nets:
        n_types = len(net.deterministic_types(roles))
        if n_types >= min_types:
            kept.append(net)
        else:
            dropped.append(net)
            if n_types == 0:
                model_only += 1
    report = GroupingReport(components=len(comps), split_components=split, candidate_networks=len(nets),
                            kept=len(kept), dropped_too_few_types=len(dropped) - model_only, dropped_model_only=model_only)
    return kept, dropped, report
