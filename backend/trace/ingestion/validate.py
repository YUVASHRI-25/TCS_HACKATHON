"""Validation of normalised canonical frames.

Produces a report and a quarantine set. Rows are only excluded when a key field the canonical
model needs is unusable (null key, unparseable required value, exact duplicate), and every excluded
row is listed with its reason and raw source reference. Nothing is dropped silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from trace.domain.model.canonical import CANONICAL_MODEL
from trace.ingestion.normalise import NormaliseIssue


@dataclass
class Check:
    entity: str
    check: str
    status: str  # pass | warn | fail
    detail: str
    count: int = 0


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    quarantined: dict[str, pd.DataFrame] = field(default_factory=dict)
    row_counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, *a, **kw) -> None:
        self.checks.append(Check(*a, **kw))

    @property
    def ok(self) -> bool:
        return not any(c.status == "fail" for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "row_counts": self.row_counts,
            "checks": [asdict(c) for c in self.checks],
            "quarantined": {e: int(len(q)) for e, q in self.quarantined.items()},
        }

    def to_markdown(self) -> str:
        lines = ["| Entity | Check | Status | Count | Detail |", "|---|---|---|---|---|"]
        for c in self.checks:
            lines.append(f"| {c.entity} | {c.check} | {c.status} | {c.count} | {c.detail} |")
        return "\n".join(lines)


def _quarantine(report: ValidationReport, entity: str, rows: pd.DataFrame, reason: str) -> None:
    if rows.empty:
        return
    q = rows[["_source_table", "_source_row"]].copy()
    q["reason"] = reason
    prev = report.quarantined.get(entity)
    report.quarantined[entity] = q if prev is None else pd.concat([prev, q], ignore_index=True)


def validate(frames: dict[str, pd.DataFrame], issues: list[NormaliseIssue]) -> tuple[dict[str, pd.DataFrame],
                                                                                    ValidationReport]:
    report = ValidationReport()
    for iss in issues:
        report.add(iss.entity, f"parse:{iss.field}", "warn", iss.problem, iss.count)

    clean: dict[str, pd.DataFrame] = {}
    for entity, df in frames.items():
        attrs = dict(df.attrs)
        spec = CANONICAL_MODEL[entity]
        n_in = len(df)
        key = spec.key

        if key in df.columns:
            null_key = df[key].isna()
            report.add(entity, "key_not_null", "warn" if null_key.any() else "pass",
                       f"{key} null", int(null_key.sum()))
            _quarantine(report, entity, df[null_key], f"null {key}")
            df = df[~null_key]

            data_cols = [c for c in df.columns if not c.startswith("_")]
            exact_dup = df.duplicated(subset=data_cols, keep="first")
            report.add(entity, "exact_duplicates", "warn" if exact_dup.any() else "pass",
                       "identical rows (first kept)", int(exact_dup.sum()))
            _quarantine(report, entity, df[exact_dup], "exact duplicate")
            df = df[~exact_dup]

            key_dup = df[key].duplicated(keep=False)
            # Conflicting rows sharing a key are reported, not resolved by guessing which is right.
            report.add(entity, "key_unique", "warn" if key_dup.any() else "pass",
                       f"rows sharing {key} with differing values", int(key_dup.sum()))

        if entity == "Transaction":
            for req in ("ts", "src_account_id", "dst_account_id", "amount"):
                if req in df.columns:
                    bad = df[req].isna()
                    report.add(entity, f"required:{req}", "warn" if bad.any() else "pass",
                               f"{req} null/unparseable", int(bad.sum()))
                    _quarantine(report, entity, df[bad], f"null {req}")
                    df = df[~bad]
            if "amount" in df.columns:
                neg = df["amount"] < 0
                report.add(entity, "amount_non_negative", "warn" if neg.any() else "pass",
                           "negative amounts (kept, flagged)", int(neg.sum()))
            if "ts" in df.columns and len(df):
                ordered = bool(df["ts"].is_monotonic_increasing)
                report.add(entity, "time_ordering", "pass" if ordered else "warn",
                           "source rows in timestamp order" if ordered else "source rows not in timestamp order "
                           "(sorted downstream; source order preserved via _source_row)")

        df.attrs = attrs
        clean[entity] = df
        report.row_counts[entity] = {"in": n_in, "kept": len(df), "quarantined": n_in - len(df)}

    # Referential integrity across canonical entities (reported; dangling refs are not invented).
    for entity, df in clean.items():
        for f in CANONICAL_MODEL[entity].fields:
            if not f.references or f.name not in df.columns:
                continue
            tgt_entity, tgt_field = f.references.split(".", 1)
            tgt = clean.get(tgt_entity)
            if tgt is None or tgt_field not in tgt.columns:
                report.add(entity, f"fk:{f.name}", "pass", f"{f.references} not mapped; FK not checkable", 0)
                continue
            vals = df[f.name].dropna()
            missing = ~vals.isin(set(tgt[tgt_field].dropna()))
            report.add(entity, f"fk:{f.name}", "warn" if missing.any() else "pass",
                       f"values with no matching {f.references}", int(missing.sum()))
    return clean, report
