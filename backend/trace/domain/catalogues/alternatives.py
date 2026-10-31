"""Rule-based fit (0-1) for legitimate alternative explanations.

Each rule declares what it needs. If the data cannot evaluate it, the result is
status="cannot_evaluate" with the reason and a next-step action. Never a guess.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from trace.domain.model.findings import DETERMINISTIC, AlternativeResult, Finding


@dataclass
class AltContext:
    members: set[str]                      # node ids
    findings: list[Finding]                # risk + model findings of the network
    context: list[Finding]                 # context findings (e.g. regular_cadence)
    evidence_of: dict[int, str]            # id(finding) -> evidence id
    frames: dict[str, pd.DataFrame]
    derived_fields: dict[str, list[str]]   # entity -> derived field names
    capabilities: dict[str, bool]
    params: dict[str, Any]                 # catalogues.alternative_params
    txn_amount: dict[str, float]           # txn_id -> amount for the network's transactions

    def has_direct(self, entity: str, fld: str) -> bool:
        df = self.frames.get(entity)
        return (df is not None and fld in df.columns and df[fld].notna().any()
                and fld not in self.derived_fields.get(entity, []))

    def of_type(self, *types: str) -> list[Finding]:
        return [f for f in self.findings if f.type in types]

    def risk_txns(self) -> set[str]:
        return {t for f in self.findings if f.source == DETERMINISTIC for t in f.txn_ids}

    def member_accounts(self) -> list[str]:
        return [m.split(":", 1)[1] for m in self.members if m.startswith("account:")]

    def member_holders(self) -> list[str]:
        acc = self.frames.get("Account")
        if acc is None or "customer_id" not in acc.columns:
            return []
        return sorted(acc.loc[acc["account_id"].isin(self.member_accounts()), "customer_id"].dropna().unique())

    def related_holders(self, types_param: str) -> tuple[set[str], list[dict]] | None:
        """Member holders that have a declared relationship of the configured types with another member
        holder. None when relationships or the type vocabulary are unavailable."""
        types = {str(t).upper() for t in (self.params.get(types_param) or [])}
        rel = self.frames.get("Relationship")
        if not types or rel is None or "relationship_type" not in rel.columns:
            return None
        holders = set(self.member_holders())
        r = rel[rel["relationship_type"].astype(str).str.upper().isin(types)
                & rel["entity_1_id"].isin(holders) & rel["entity_2_id"].isin(holders)]
        return set(r["entity_1_id"]) | set(r["entity_2_id"]), r[["_source_table", "_source_row"]].to_dict("records")


Rule = Callable[[AltContext, dict[str, Any]], AlternativeResult]
RULES: dict[str, Rule] = {}


def rule(alt_id: str):
    def deco(fn: Rule) -> Rule:
        RULES[alt_id] = fn
        return fn
    return deco


def _res(alt_id, spec, status, fit, reason, ev=None):
    return AlternativeResult(alt_id, spec["label"], status, None if fit is None else round(float(fit), 3), reason,
                             ev or [], spec.get("next_step_if_unknown") if status != "not_applicable" else None)


@rule("PAYROLL")
def payroll(ctx: AltContext, spec):
    if not ctx.capabilities.get("regular_cadence"):
        return _res("PAYROLL", spec, "cannot_evaluate", None, "regular-cadence detection is not available on this data")
    risk = ctx.risk_txns()
    if not risk:
        return _res("PAYROLL", spec, "not_applicable", None, "network has no flagged transactions")
    cad = [f for f in ctx.context if f.type == "regular_cadence"]
    cad_txns = {t for f in cad for t in f.txn_ids} & risk
    total = sum(ctx.txn_amount.get(t, 0) for t in risk)
    fit = sum(ctx.txn_amount.get(t, 0) for t in cad_txns) / total if total else 0.0
    ev = [ctx.evidence_of[id(f)] for f in cad if id(f) in ctx.evidence_of]
    return _res("PAYROLL", spec, "evaluated", fit,
                f"{len(cad_txns)} of {len(risk)} flagged transactions are part of regular periodic payment series", ev)


@rule("FAMILY_HOUSEHOLD")
def household(ctx: AltContext, spec):
    if not ctx.has_direct("Account", "customer_id"):
        return _res("FAMILY_HOUSEHOLD", spec, "cannot_evaluate", None, "account ownership is not in the data")
    holders = ctx.member_holders()
    if len(holders) < 2:
        return _res("FAMILY_HOUSEHOLD", spec, "not_applicable", None, "the network has fewer than two holders")
    reasons, related = [], set()
    rel = ctx.related_holders("family_relationship_types")
    if rel is not None:
        related |= rel[0]
        reasons.append(f"{len(rel[0])} of {len(holders)} holders have a declared family relationship with another member")
    if ctx.has_direct("Customer", "address"):
        cust = ctx.frames["Customer"]
        addr = cust[cust["customer_id"].isin(holders)].dropna(subset=["address"])
        shared = addr[addr["address"].str.lower().duplicated(keep=False)]
        related |= set(shared["customer_id"])
        reasons.append(f"{shared['customer_id'].nunique()} of {len(holders)} holders share an address")
    if not reasons:
        return _res("FAMILY_HOUSEHOLD", spec, "cannot_evaluate", None,
                    "the data has neither declared family relationships nor comparable holder addresses")
    return _res("FAMILY_HOUSEHOLD", spec, "evaluated", len(related) / len(holders), "; ".join(reasons))


@rule("OFFICE_NETWORK")
def office(ctx: AltContext, spec):
    ips = ctx.of_type("shared_ip")
    if not ips:
        return _res("OFFICE_NETWORK", spec, "not_applicable", None, "no shared IP in this network")
    office_types = {str(t).upper() for t in (ctx.params.get("office_network_types") or [])}
    ipf = ctx.frames.get("IP")
    typed = {}
    if office_types and ipf is not None and "network_type" in ipf.columns:
        typed = dict(zip(ipf["ip_id"], ipf["network_type"].astype(str).str.upper()))
    hits, reasons = [], []
    for f in ips:
        ip = f.details.get("ip")
        if typed and typed.get(ip) in office_types:
            hits.append(f)
        elif not typed and f.details.get("large_share"):
            hits.append(f)
    ev = [ctx.evidence_of[id(f)] for f in ips if id(f) in ctx.evidence_of]
    if typed:
        reasons.append(f"{len(hits)} of {len(ips)} shared IPs are recorded as {'/'.join(sorted(office_types))} networks")
    else:
        reasons.append(f"{len(hits)} of {len(ips)} shared IPs are used by unusually many accounts for this dataset; "
                       "the network type is not in the data")
    r = _res("OFFICE_NETWORK", spec, "evaluated", len(hits) / len(ips), "; ".join(reasons), ev)
    r.next_step = spec.get("next_step_if_unknown")
    return r


def _business_accounts(ctx: AltContext) -> tuple[set[str] | None, str]:
    vals = {str(v).lower() for v in (ctx.params.get("business_type_values") or [])}
    if not vals:
        return None, "business_type_values not configured (which account/customer types are businesses must come from the data owner)"
    out: set[str] = set()
    acc = ctx.frames.get("Account")
    if ctx.has_direct("Account", "account_type"):
        out |= set(acc.loc[acc["account_type"].str.lower().isin(vals), "account_id"])
    if ctx.has_direct("Customer", "customer_type") and ctx.has_direct("Account", "customer_id"):
        cust = ctx.frames["Customer"]
        biz = set(cust.loc[cust["customer_type"].str.lower().isin(vals), "customer_id"])
        out |= set(acc.loc[acc["customer_id"].isin(biz), "account_id"])
    if not ctx.has_direct("Account", "account_type") and not ctx.has_direct("Customer", "customer_type"):
        return None, "the data has no direct account_type / customer_type field"
    return out, ""


@rule("LEGITIMATE_SUPPLIER_TRADE")
def supplier(ctx: AltContext, spec):
    biz, why = _business_accounts(ctx)
    if biz is None:
        return _res("LEGITIMATE_SUPPLIER_TRADE", spec, "cannot_evaluate", None, why)
    t = ctx.frames["Transaction"]
    risk = t[t["txn_id"].isin(ctx.risk_txns())]
    if risk.empty:
        return _res("LEGITIMATE_SUPPLIER_TRADE", spec, "not_applicable", None, "network has no flagged transactions")
    both = risk["src_account_id"].isin(biz) & risk["dst_account_id"].isin(biz)
    fit = risk.loc[both, "amount"].sum() / risk["amount"].sum() if risk["amount"].sum() else 0.0
    return _res("LEGITIMATE_SUPPLIER_TRADE", spec, "evaluated", fit,
                f"{int(both.sum())} of {len(risk)} flagged transactions are between business accounts")


@rule("SHARED_BUSINESS")
def shared_business(ctx: AltContext, spec):
    biz, why = _business_accounts(ctx)
    if biz is None:
        return _res("SHARED_BUSINESS", spec, "cannot_evaluate", None, why)
    if not ctx.has_direct("Account", "customer_id"):
        return _res("SHARED_BUSINESS", spec, "cannot_evaluate", None, "account ownership is not in the data")
    acc = ctx.frames["Account"]
    n = len(ctx.member_accounts())
    mem = acc[acc["account_id"].isin(ctx.member_accounts()) & acc["account_id"].isin(biz)]
    top = int(mem["customer_id"].value_counts().iloc[0]) if not mem.empty else 0
    fit, reasons = top / n if n else 0.0, [f"{top} of {n} member accounts are business accounts of one holder"]
    rel = ctx.related_holders("business_relationship_types")
    holders = ctx.member_holders()
    if rel is not None and holders:
        reasons.append(f"{len(rel[0])} of {len(holders)} holders have a declared business relationship with another member")
        fit = max(fit, len(rel[0]) / len(holders))
    return _res("SHARED_BUSINESS", spec, "evaluated", fit, "; ".join(reasons))


@rule("COMMON_NAME_COINCIDENCE")
def common_name(ctx: AltContext, spec):
    names = ctx.of_type("possible_same_entity", "sanctions_potential_match")
    if not names:
        return _res("COMMON_NAME_COINCIDENCE", spec, "not_applicable", None, "no name-based link in this network")
    name_only = [f for f in names if f.type == "sanctions_potential_match" or f.details.get("name_only")]
    ev = [ctx.evidence_of[id(f)] for f in name_only if id(f) in ctx.evidence_of]
    return _res("COMMON_NAME_COINCIDENCE", spec, "evaluated", len(name_only) / len(names),
                f"{len(name_only)} of {len(names)} identity links rest on a name match without a corroborating identifier", ev)


def evaluate_all(ctx: AltContext, catalogue: dict[str, dict[str, Any]]) -> list[AlternativeResult]:
    out = []
    for alt_id, spec in catalogue.items():
        fn = RULES.get(alt_id)
        if fn is None:
            out.append(AlternativeResult(alt_id, spec["label"], "cannot_evaluate", None, "no fit rule implemented",
                                         [], spec.get("next_step_if_unknown")))
        else:
            out.append(fn(ctx, spec))
    return out
