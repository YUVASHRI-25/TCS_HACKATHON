"""Capability registry: which detectors/resolvers/models can run on this dataset, and why not."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from trace.domain.detectors.requirements import CAPABILITIES, Capability
from trace.domain.model.canonical import MappingStatus
from trace.ingestion.mapping import MappingConfig


@dataclass
class CapabilityStatus:
    id: str
    kind: str
    label: str
    enabled: bool
    deterministic: bool
    reason: str
    uses_derived: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _usable(cfg: MappingConfig, ref: str, allow_derived: bool) -> tuple[bool, str]:
    st = cfg.status(ref)
    if st is MappingStatus.DIRECT:
        return True, ""
    if st is MappingStatus.DERIVED:
        return (True, "") if allow_derived else (False, f"{ref} is only derived")
    return False, f"{ref} absent"


def evaluate(cap: Capability, cfg: MappingConfig) -> CapabilityStatus:
    req = cap.requirement
    missing: list[str] = []
    derived: list[str] = []
    for ref in req.all_of:
        ok, why = _usable(cfg, ref, req.allow_derived)
        if not ok:
            missing.append(why)
        elif cfg.status(ref) is MappingStatus.DERIVED:
            derived.append(ref)

    if req.any_of:
        satisfied = None
        for group in req.any_of:
            res = [_usable(cfg, r, req.allow_derived) for r in group]
            if all(ok for ok, _ in res):
                satisfied = group
                break
        if satisfied is None:
            missing.append("none of: " + " | ".join("+".join(g) for g in req.any_of))
        else:
            derived += [r for r in satisfied if cfg.status(r) is MappingStatus.DERIVED]

    enabled = not missing
    reason = "all required fields present" if enabled else "Not evaluated: " + "; ".join(missing)
    if req.note and not enabled:
        reason += f" ({req.note})"
    return CapabilityStatus(cap.id, cap.kind, cap.label, enabled, cap.deterministic, reason, derived)


def capability_table(cfg: MappingConfig) -> list[CapabilityStatus]:
    return [evaluate(c, cfg) for c in CAPABILITIES]


def to_markdown(rows: list[CapabilityStatus]) -> str:
    lines = ["| Capability | Kind | Status | Reason | Uses derived |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.id} | {r.kind} | {'ENABLED' if r.enabled else 'DISABLED'} | {r.reason} | "
                     f"{', '.join(r.uses_derived) or '-'} |")
    return "\n".join(lines)
