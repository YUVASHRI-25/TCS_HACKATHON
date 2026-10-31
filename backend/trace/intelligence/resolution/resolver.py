"""Entity resolution: POSSIBLE_SAME_ENTITY links between customer records. Never merges.

Blocking:
  - exact identifiers (national_id, email, phone) after light normalisation
  - names: blocked on the sorted first letters of name tokens, compared with rapidfuzz token_sort_ratio
Blocks larger than resolution.max_block_size are skipped and reported (too generic to be informative).
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from trace.domain.model.findings import Finding, Link, node_id

_NON_DIGIT = re.compile(r"\D+")
_SPACE = re.compile(r"\s+")


def _norm(field: str, v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if field == "phone":
        s = _NON_DIGIT.sub("", s)
    elif field == "email":
        s = s.replace(" ", "")
    else:
        s = _SPACE.sub(" ", s)
    return s or None


def resolve(customers: pd.DataFrame, cfg: dict[str, Any]) -> tuple[list[Link], list[str]]:
    notes: list[str] = []
    links: dict[tuple[str, str], Link] = {}
    max_block = cfg["max_block_size"]

    def add(a, b, conf, reason, rows):
        if a == b:
            return
        key = tuple(sorted((a, b)))
        if key in links:
            ln = links[key]
            ln.reasons.append(reason)
            # independent agreeing identifiers: combine as 1 - prod(1 - c)
            ln.confidence = 1 - (1 - ln.confidence) * (1 - conf)
            ln.source_rows.extend(rows)
        else:
            links[key] = Link(node_id("customer", key[0]), node_id("customer", key[1]), "possible_same_entity",
                              conf, [reason], list(rows))

    ref = customers[["customer_id", "_source_table", "_source_row"]].set_index("customer_id")

    def rows_for(*ids):
        return [{"table": ref.loc[i, "_source_table"], "row": int(ref.loc[i, "_source_row"])}
                for i in ids if i in ref.index]

    for field, conf in (cfg.get("exact_identifier_confidence") or {}).items():
        if field not in customers.columns:
            continue
        vals = customers[["customer_id", field]].assign(k=customers[field].map(lambda v, f=field: _norm(f, v)))
        for k, g in vals.dropna(subset=["k"]).groupby("k"):
            ids = list(dict.fromkeys(g["customer_id"]))
            if len(ids) < 2:
                continue
            if len(ids) > max_block:
                notes.append(f"skipped {field} value shared by {len(ids)} records (> max_block_size)")
                continue
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    add(a, b, conf, f"same {field}", rows_for(a, b))

    if "name" in customers.columns:
        names = customers[["customer_id", "name"]].assign(n=customers["name"].map(lambda v: _norm("name", v)))
        names = names.dropna(subset=["n"])
        names["block"] = names["n"].map(lambda s: "".join(sorted(t[0] for t in s.split())))
        min_score, scale = cfg["name_min_score"], cfg["name_only_confidence_scale"]
        for _, g in names.groupby("block"):
            if len(g) < 2:
                continue
            if len(g) > max_block:
                notes.append(f"skipped a name block of {len(g)} records (> max_block_size)")
                continue
            recs = list(g[["customer_id", "n"]].itertuples(index=False, name=None))
            for i, (a, na) in enumerate(recs):
                for b, nb in recs[i + 1:]:
                    score = fuzz.token_sort_ratio(na, nb)
                    if score >= min_score:
                        add(a, b, score / 100 * scale, f"similar name (score {score:.0f})", rows_for(a, b))
    return list(links.values()), notes


def links_to_findings(links: list[Link], accounts_of: dict[str, list[str]]) -> list[Finding]:
    """One possible_same_entity finding per link, expressed on the customers' accounts."""
    out = []
    for ln in links:
        ca, cb = ln.a.split(":", 1)[1], ln.b.split(":", 1)[1]
        subjects = tuple(node_id("account", x) for x in accounts_of.get(ca, []) + accounts_of.get(cb, [])) or (ln.a, ln.b)
        name_only = all(r.startswith("similar name") for r in ln.reasons)
        out.append(Finding(
            type="possible_same_entity", detector="entity_resolution", subjects=subjects, related=(ln.a, ln.b),
            txn_ids=(), strength=ln.confidence,
            details={"customers": [ca, cb], "reasons": ln.reasons, "confidence": ln.confidence,
                     "name_only": name_only, "source_rows": ln.source_rows},
            cypher_used=f"MATCH (a:Customer {{id:'{ca}'}})-[r:POSSIBLE_SAME_ENTITY]-(b:Customer {{id:'{cb}'}}) RETURN a, r, b"))
    return out


def sanctions_matches(customers: pd.DataFrame, watchlist: pd.DataFrame, min_score: float,
                      accounts_of: dict[str, list[str]]) -> list[Finding]:
    """Potential watchlist name matches requiring human review. A name match is never a determination."""
    from rapidfuzz import process

    wl = watchlist.dropna(subset=["name"])
    choices = [str(n).lower() for n in wl["name"]]
    out = []
    for _, c in customers.dropna(subset=["name"]).iterrows():
        best = process.extractOne(str(c["name"]).lower(), choices, scorer=fuzz.token_sort_ratio, score_cutoff=min_score)
        if not best:
            continue
        _, score, idx = best
        w = wl.iloc[idx]
        cid = c["customer_id"]
        subjects = tuple(node_id("account", a) for a in accounts_of.get(cid, [])) or (node_id("customer", cid),)
        out.append(Finding(
            type="sanctions_potential_match", detector="sanctions_potential_match", subjects=subjects,
            related=(node_id("watchlist_entry", w["entry_id"]),), txn_ids=(), strength=score / 100,
            details={"customer": cid, "watchlist_entry": w["entry_id"], "list": w.get("list_name"),
                     "name_score": score, "note": "potential match requiring human review",
                     "source_rows": [{"table": c["_source_table"], "row": int(c["_source_row"])},
                                     {"table": w["_source_table"], "row": int(w["_source_row"])}]},
            cypher_used=(f"MATCH (c:Customer {{id:'{cid}'}})-[r:SCREENED_AGAINST]->(w:WatchlistEntry "
                         f"{{id:'{w['entry_id']}'}}) RETURN c, r, w")))
    return out


def accounts_by_customer(accounts: pd.DataFrame | None) -> dict[str, list[str]]:
    if accounts is None or "customer_id" not in accounts.columns:
        return {}
    d: dict[str, list[str]] = defaultdict(list)
    for a, c in zip(accounts["account_id"], accounts["customer_id"]):
        if pd.notna(c):
            d[c].append(a)
    return dict(d)
