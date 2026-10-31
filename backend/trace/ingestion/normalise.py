"""Type normalisation of canonical frames.

- Timestamps become timezone-aware UTC. Naive source timestamps require `source.timezone` in the
  mapping; without it we refuse rather than assume a timezone.
- Numbers are parsed with errors recorded, never silently zeroed.
- Currencies are upper-cased codes. No FX conversion is performed (no rates are assumed).
Values that fail to parse become null AND are recorded in the returned issues list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trace.domain.model.canonical import CANONICAL_MODEL, FieldKind

_TRUE = {"1", "true", "t", "yes", "y"}
_FALSE = {"0", "false", "f", "no", "n"}


@dataclass
class NormaliseIssue:
    entity: str
    field: str
    problem: str
    source_rows: list[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.source_rows)


class TimezoneRequired(ValueError):
    pass


def _record(issues: list[NormaliseIssue], entity: str, fname: str, problem: str,
            before: pd.Series, after: pd.Series, rows: pd.Series) -> None:
    bad = before.notna() & after.isna()
    if bad.any():
        issues.append(NormaliseIssue(entity, fname, problem, rows[bad].astype(int).tolist()))


def _to_ts(s: pd.Series, tz: str | None, entity: str, fname: str) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce", utc=False, format="mixed")
    if getattr(out.dt, "tz", None) is None:
        if out.notna().any() and not tz:
            raise TimezoneRequired(
                f"{entity}.{fname} has naive timestamps; declare source.timezone in mapping.yaml "
                "(TRACE will not assume one)")
        out = out.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT") if tz else out.dt.tz_localize("UTC")
    return out.dt.tz_convert("UTC")


def _to_bool(s: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(s):
        return s.astype("boolean")
    low = s.astype("string").str.strip().str.lower()
    return low.map(lambda v: True if v in _TRUE else False if v in _FALSE else pd.NA).astype("boolean")


def normalise(frames: dict[str, pd.DataFrame], timezone: str | None) -> tuple[dict[str, pd.DataFrame],
                                                                                list[NormaliseIssue]]:
    issues: list[NormaliseIssue] = []
    out: dict[str, pd.DataFrame] = {}
    for entity, df in frames.items():
        df = df.copy()
        attrs = dict(df.attrs)
        spec = CANONICAL_MODEL[entity]
        rows = df["_source_row"]
        for f in spec.fields:
            if f.name not in df.columns:
                continue
            before = df[f.name]
            if f.kind in (FieldKind.TIMESTAMP, FieldKind.DATE):
                after = _to_ts(before, timezone, entity, f.name)
                _record(issues, entity, f.name, "unparseable timestamp", before, after, rows)
            elif f.kind is FieldKind.NUMBER:
                after = pd.to_numeric(before, errors="coerce")
                _record(issues, entity, f.name, "unparseable number", before, after, rows)
            elif f.kind is FieldKind.BOOLEAN:
                after = _to_bool(before)
                _record(issues, entity, f.name, "unparseable boolean", before, after, rows)
            elif f.kind is FieldKind.CURRENCY:
                after = before.astype("string").str.strip().str.upper()
            else:
                after = before.astype("string").str.strip()
                after = after.mask(after == "")
            df[f.name] = after
        df.attrs = attrs
        out[entity] = df
    return out, issues
