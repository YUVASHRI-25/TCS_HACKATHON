"""Canonical data model: the entity types and fields TRACE reasons about.

This is the schema the ingestion layer maps any dataset onto. It contains no dataset-specific
names or values. Pure Python, no framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FieldKind(str, Enum):
    ID = "id"
    STRING = "string"
    NUMBER = "number"
    TIMESTAMP = "timestamp"
    DATE = "date"
    BOOLEAN = "boolean"
    TEXT = "text"
    CURRENCY = "currency"


class MappingStatus(str, Enum):
    DIRECT = "direct"
    DERIVED = "derived"
    ABSENT = "absent"


@dataclass(frozen=True)
class CanonicalField:
    name: str
    kind: FieldKind
    pii: bool = False
    # FK target as "Entity.field"
    references: str | None = None


@dataclass(frozen=True)
class CanonicalEntity:
    name: str
    key: str
    fields: tuple[CanonicalField, ...]

    def field(self, name: str) -> CanonicalField:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(f"{self.name}.{name} is not a canonical field")

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


F = CanonicalField
K = FieldKind

CANONICAL_MODEL: dict[str, CanonicalEntity] = {
    e.name: e
    for e in [
        CanonicalEntity("Customer", "customer_id", (
            F("customer_id", K.ID),
            F("name", K.STRING, pii=True),
            F("date_of_birth", K.DATE, pii=True),
            F("phone", K.STRING, pii=True),
            F("email", K.STRING, pii=True),
            F("address", K.STRING, pii=True),
            F("national_id", K.STRING, pii=True),
            F("customer_type", K.STRING),
            F("nationality", K.STRING),
            F("occupation", K.STRING),
            F("risk_rating", K.STRING),
            F("kyc_status", K.STRING),
            F("kyc_date", K.DATE),
            F("location_id", K.ID, references="Location.location_id"),
        )),
        CanonicalEntity("Account", "account_id", (
            F("account_id", K.ID, pii=True),
            F("customer_id", K.ID, references="Customer.customer_id"),
            F("bank_id", K.ID),
            F("branch_id", K.ID),
            F("account_type", K.STRING),
            F("status", K.STRING),
            F("open_date", K.TIMESTAMP),
            F("currency", K.CURRENCY),
            F("location_id", K.ID, references="Location.location_id"),
        )),
        CanonicalEntity("Transaction", "txn_id", (
            F("txn_id", K.ID),
            F("ts", K.TIMESTAMP),
            F("src_account_id", K.ID, pii=True, references="Account.account_id"),
            F("dst_account_id", K.ID, pii=True, references="Account.account_id"),
            F("amount", K.NUMBER),
            F("currency", K.CURRENCY),
            F("amount_received", K.NUMBER),
            F("currency_received", K.CURRENCY),
            F("channel", K.STRING),
            F("txn_type", K.STRING),
            F("status", K.STRING),
            F("merchant_id", K.ID, references="Merchant.merchant_id"),
            F("device_id", K.ID, references="Device.device_id"),
            F("ip_id", K.ID, references="IP.ip_id"),
            F("location_id", K.ID, references="Location.location_id"),
            F("beneficiary_id", K.ID, references="Beneficiary.beneficiary_id"),
            F("label", K.BOOLEAN),  # dataset-provided ground truth, if any. Report-only, never tuned on.
        )),
        CanonicalEntity("Merchant", "merchant_id", (
            F("merchant_id", K.ID),
            F("name", K.STRING),
            F("category", K.STRING),
            F("flagged", K.BOOLEAN),
            F("registration_date", K.DATE),
            F("location_id", K.ID, references="Location.location_id"),
        )),
        CanonicalEntity("Device", "device_id", (
            F("device_id", K.ID),
            F("fingerprint", K.STRING),
            F("device_type", K.STRING),
            F("account_id", K.ID, references="Account.account_id"),
            F("customer_id", K.ID, references="Customer.customer_id"),
            F("first_seen", K.TIMESTAMP),
        )),
        CanonicalEntity("IP", "ip_id", (
            F("ip_id", K.ID),
            F("address", K.STRING, pii=True),
            F("isp", K.STRING),
            F("country", K.STRING),
            F("network_type", K.STRING),
            F("account_id", K.ID, references="Account.account_id"),
            F("customer_id", K.ID, references="Customer.customer_id"),
        )),
        # Digital sessions: who used which device / IP, and when.
        CanonicalEntity("Login", "login_id", (
            F("login_id", K.ID),
            F("customer_id", K.ID, references="Customer.customer_id"),
            F("account_id", K.ID, references="Account.account_id"),
            F("device_id", K.ID, references="Device.device_id"),
            F("ip_id", K.ID, references="IP.ip_id"),
            F("ts", K.TIMESTAMP),
            F("status", K.STRING),
        )),
        # Bridge table: a device observed in use by a holder.
        CanonicalEntity("DeviceUsage", "usage_id", (
            F("usage_id", K.ID),
            F("device_id", K.ID, references="Device.device_id"),
            F("customer_id", K.ID, references="Customer.customer_id"),
            F("account_id", K.ID, references="Account.account_id"),
            F("first_seen", K.TIMESTAMP),
            F("last_seen", K.TIMESTAMP),
        )),
        CanonicalEntity("Location", "location_id", (
            F("location_id", K.ID),
            F("city", K.STRING),
            F("region", K.STRING),
            F("country", K.STRING),
            F("latitude", K.NUMBER),
            F("longitude", K.NUMBER),
        )),
        CanonicalEntity("Beneficiary", "beneficiary_id", (
            F("beneficiary_id", K.ID),
            F("customer_id", K.ID, references="Customer.customer_id"),
            F("account_id", K.ID, references="Account.account_id"),
            F("name", K.STRING, pii=True),
            F("beneficiary_type", K.STRING),
            F("bank_id", K.ID),
            F("added_ts", K.TIMESTAMP),
        )),
        # Declared relationships between parties (e.g. family, employer). Used by alternative explanations.
        CanonicalEntity("Relationship", "relationship_id", (
            F("relationship_id", K.ID),
            F("entity_1_id", K.ID),
            F("entity_2_id", K.ID),
            F("relationship_type", K.STRING),
            F("source", K.STRING),
        )),
        CanonicalEntity("Complaint", "complaint_id", (
            F("complaint_id", K.ID),
            F("subject_type", K.STRING),
            F("subject_id", K.ID),
            F("ts", K.TIMESTAMP),
            F("category", K.STRING),
            F("status", K.STRING),
            F("text", K.TEXT, pii=True),
        )),
        CanonicalEntity("Alert", "alert_id", (
            F("alert_id", K.ID),
            F("subject_type", K.STRING),
            F("subject_id", K.ID),
            F("txn_id", K.ID),
            F("ts", K.TIMESTAMP),
            F("rule", K.STRING),
            F("severity", K.STRING),
            F("outcome", K.STRING),
        )),
        # Previous investigations opened from alerts.
        CanonicalEntity("PriorCase", "case_id", (
            F("case_id", K.ID),
            F("alert_id", K.ID, references="Alert.alert_id"),
            F("status", K.STRING),
            F("case_type", K.STRING),
            F("opened_at", K.TIMESTAMP),
        )),
        CanonicalEntity("WatchlistEntry", "entry_id", (
            F("entry_id", K.ID),
            F("name", K.STRING, pii=True),
            F("list_name", K.STRING),
            F("country", K.STRING),
            F("date_of_birth", K.DATE, pii=True),
        )),
        # Screening hits produced by an upstream screening system (already matched to an entity id).
        CanonicalEntity("ScreeningMatch", "match_id", (
            F("match_id", K.ID),
            F("entity_id", K.ID),
            F("list_type", K.STRING),
            F("match_type", K.STRING),
            F("confidence", K.NUMBER),
            F("source", K.STRING),
        )),
        # Dataset-provided ground truth at entity level. REPORT ONLY: never read by detectors or scoring.
        CanonicalEntity("LabelledMember", "label_id", (
            F("label_id", K.ID),
            F("entity_id", K.ID),
            F("group_id", K.ID),
            F("role", K.STRING),
            F("typology", K.STRING),
        )),
    ]
}


def canonical_ref(ref: str) -> tuple[CanonicalEntity, CanonicalField]:
    """Resolve "Entity.field" to its canonical definitions."""
    entity_name, field_name = ref.split(".", 1)
    entity = CANONICAL_MODEL[entity_name]
    return entity, entity.field(field_name)
