"""Field requirements each detector / resolver / alternative declares.

A requirement is satisfied only by fields the mapping marks `direct`, or `derived` when the
requirement allows derived inputs. Nothing here is dataset-specific: it states what canonical
data a technique needs in order to be evaluated at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Requirement:
    """all_of: every ref needed. any_of: groups where at least one group must be fully present."""

    all_of: tuple[str, ...] = ()
    any_of: tuple[tuple[str, ...], ...] = ()
    allow_derived: bool = True
    note: str = ""


@dataclass(frozen=True)
class Capability:
    id: str
    kind: str  # detector | resolver | alternative | model
    label: str
    requirement: Requirement
    deterministic: bool = True
    depends_on: tuple[str, ...] = field(default_factory=tuple)


_TXN_CORE = ("Transaction.txn_id", "Transaction.ts", "Transaction.src_account_id", "Transaction.dst_account_id")
_TXN_AMT = _TXN_CORE + ("Transaction.amount",)

CAPABILITIES: tuple[Capability, ...] = (
    # --- deterministic detectors -------------------------------------------------------------
    Capability("rapid_pass_through", "detector", "Rapid pass-through", Requirement(all_of=_TXN_AMT)),
    Capability("cycle", "detector", "Circular flows (length 3-6)", Requirement(all_of=_TXN_AMT)),
    Capability("fan_in", "detector", "Fan-in", Requirement(all_of=_TXN_CORE)),
    Capability("fan_out", "detector", "Fan-out", Requirement(all_of=_TXN_CORE)),
    Capability("structuring", "detector", "Structuring below threshold",
               Requirement(all_of=("Transaction.txn_id", "Transaction.ts", "Transaction.src_account_id",
                                   "Transaction.amount"))),
    Capability("new_account_large_inflow", "detector", "New account, large inflow",
               Requirement(all_of=_TXN_AMT + ("Account.open_date",), allow_derived=False,
                           note="A first-seen proxy for open date would be a guess, so derived is not accepted.")),
    Capability("burst_velocity", "detector", "Burst / velocity",
               Requirement(all_of=("Transaction.txn_id", "Transaction.ts", "Transaction.src_account_id"))),
    Capability("regular_cadence", "detector", "Regular cadence (periodic payments)", Requirement(all_of=_TXN_AMT)),
    Capability("flagged_merchant", "detector", "Flagged merchant",
               Requirement(all_of=("Transaction.merchant_id", "Merchant.merchant_id", "Merchant.flagged"),
                           allow_derived=False)),
    Capability("complaint_cluster", "detector", "Complaint cluster",
               Requirement(all_of=("Complaint.complaint_id", "Complaint.subject_id", "Complaint.ts"),
                           allow_derived=False)),
    Capability("sanctions_potential_match", "detector", "Sanctions potential match",
               Requirement(all_of=("WatchlistEntry.name", "Customer.name"), allow_derived=False)),
    Capability("prior_escalation", "detector", "Prior escalation",
               Requirement(all_of=("Alert.alert_id", "Alert.subject_id", "Alert.outcome"), allow_derived=False)),
    Capability("shared_device", "detector", "Shared device across unrelated holders",
               Requirement(any_of=(("Transaction.device_id",), ("Device.device_id", "Device.account_id"),
                                   ("Device.device_id", "Device.customer_id")), allow_derived=False)),
    Capability("shared_ip", "detector", "Shared IP across unrelated holders",
               Requirement(any_of=(("Transaction.ip_address",), ("IP.ip_address", "IP.account_id"),
                                   ("IP.ip_address", "IP.customer_id")), allow_derived=False)),
    # --- resolution ------------------------------------------------------------------------
    Capability("entity_resolution", "resolver", "Entity resolution (possible same entity)",
               Requirement(any_of=(("Customer.name",), ("Customer.phone",), ("Customer.email",),
                                   ("Customer.national_id",), ("Customer.address",)), allow_derived=False,
                           note="Needs at least one identifying attribute; account IDs alone cannot resolve people.")),
    # --- unsupervised model (capped signal) -------------------------------------------------
    Capability("isolation_forest", "model", "IsolationForest anomaly signal", Requirement(all_of=_TXN_AMT),
               deterministic=False),
)


def capability(cap_id: str) -> Capability:
    for c in CAPABILITIES:
        if c.id == cap_id:
            return c
    raise KeyError(cap_id)
