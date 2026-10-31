"""Load config/mapping.yaml and apply it: raw tables -> canonical frames.

Rules:
- `direct` fields copy a source column.
- `derived` fields use one of the named DERIVATIONS below; the resulting frame carries
  `_derived_fields` metadata and derived entities get a `derived` column set to True.
- `absent` (or unlisted) fields are not created. Nothing is imputed.
- Every canonical row keeps `_source_table` and `_source_row` back to the raw record.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import yaml
from pydantic import BaseModel, Field, model_validator

from trace.domain.model.canonical import CANONICAL_MODEL, MappingStatus
from trace.ingestion.adapters.base import SourceAdapter
from trace.ingestion.adapters.file_adapters import ADAPTERS


class FieldMapping(BaseModel):
    status: MappingStatus
    column: str | None = None
    derivation: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> FieldMapping:
        if self.status is MappingStatus.DIRECT and not self.column:
            raise ValueError("direct mapping requires `column`")
        if self.status is MappingStatus.DERIVED and self.derivation not in DERIVATIONS:
            raise ValueError(f"derived mapping requires a known `derivation` ({sorted(DERIVATIONS)})")
        return self


class EntityMapping(BaseModel):
    table: str | None = None
    # Entity built from distinct values of other entities' fields (e.g. Account from txn endpoints)
    derived_from: list[str] | None = None
    fields: dict[str, FieldMapping] = Field(default_factory=dict)

    def status_of(self, field: str) -> MappingStatus:
        fm = self.fields.get(field)
        return fm.status if fm else MappingStatus.ABSENT


class SourceConfig(BaseModel):
    adapter: Literal["csv", "parquet", "sql"] | None = None
    timezone: str | None = None
    url: str | None = None
    tables: dict[str, dict[str, Any]] = Field(default_factory=dict)


class MappingConfig(BaseModel):
    source: SourceConfig = Field(default_factory=SourceConfig)
    entities: dict[str, EntityMapping] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_entities(self) -> MappingConfig:
        for name, em in self.entities.items():
            if name not in CANONICAL_MODEL:
                raise ValueError(f"Unknown canonical entity {name!r}")
            unknown = set(em.fields) - set(CANONICAL_MODEL[name].field_names)
            if unknown:
                raise ValueError(f"{name}: unknown canonical fields {sorted(unknown)}")
            if em.table and em.table not in self.source.tables:
                raise ValueError(f"{name}: table {em.table!r} not declared under source.tables")
        return self

    @property
    def is_empty(self) -> bool:
        return not self.source.tables or not self.entities

    def status(self, ref: str) -> MappingStatus:
        entity, field = ref.split(".", 1)
        em = self.entities.get(entity)
        return em.status_of(field) if em else MappingStatus.ABSENT


def load_mapping(path: str | Path) -> MappingConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return MappingConfig.model_validate(raw)


def build_adapter(cfg: MappingConfig, base_dir: Path) -> SourceAdapter:
    if not cfg.source.adapter:
        raise ValueError("mapping.yaml: source.adapter must be declared")
    return ADAPTERS[cfg.source.adapter](cfg.source.tables, base_dir, url=cfg.source.url)


# ---------------------------------------------------------------------------------------------
# Derivations: named, generic, documented. They never invent values; they only restate data that
# exists elsewhere in the dataset (and the output is tagged derived).
# ---------------------------------------------------------------------------------------------

Derivation = Callable[[pd.DataFrame, dict[str, Any]], pd.Series]


def _concat_columns(df: pd.DataFrame, p: dict[str, Any]) -> pd.Series:
    """Composite identifier from several columns, e.g. bank + account number. params: columns, sep."""
    cols = p["columns"]
    sep = p.get("sep", ":")
    out = df[cols[0]].astype("string")
    for c in cols[1:]:
        out = out + sep + df[c].astype("string")
    return out


def _row_number(df: pd.DataFrame, p: dict[str, Any]) -> pd.Series:
    """Surrogate key from source row position (when the source has no id). params: prefix."""
    return p.get("prefix", "") + df["_source_row"].astype("string")


def _same_as(df: pd.DataFrame, p: dict[str, Any]) -> pd.Series:
    """Reuse another column under a different canonical meaning (e.g. customer_id := account_id when
    the data has no customer table - one derived customer per account). params: column."""
    return df[p["column"]]


DERIVATIONS: dict[str, Derivation] = {
    "concat_columns": _concat_columns,
    "row_number": _row_number,
    "same_as": _same_as,
}


def _entity_from_table(name: str, em: EntityMapping, raw: pd.DataFrame, table: str) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    derived_fields: list[str] = []
    for fname, fm in em.fields.items():
        if fm.status is MappingStatus.DIRECT:
            if fm.column not in raw.columns:
                raise KeyError(f"{name}.{fname}: column {fm.column!r} not in table {table!r}")
            out[fname] = raw[fm.column]
        elif fm.status is MappingStatus.DERIVED:
            out[fname] = DERIVATIONS[fm.derivation](raw, fm.params)  # type: ignore[index]
            derived_fields.append(fname)
    out["_source_table"] = table
    out["_source_row"] = raw["_source_row"].to_numpy()
    out.attrs["derived_fields"] = derived_fields
    out.attrs["derived_entity"] = False
    return out


def _entity_from_refs(name: str, em: EntityMapping, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build an entity from distinct values of other canonical fields (e.g. Account from
    Transaction.src_account_id + Transaction.dst_account_id). Tagged derived=True."""
    key = CANONICAL_MODEL[name].key
    parts = []
    for ref in em.derived_from or []:
        ent, fld = ref.split(".", 1)
        src = frames.get(ent)
        if src is None or fld not in src.columns:
            raise KeyError(f"{name}: derived_from {ref} is not available")
        parts.append(pd.DataFrame({key: src[fld], "_source_table": src["_source_table"],
                                   "_source_row": src["_source_row"], "_derived_from": ref}))
    allrefs = pd.concat(parts, ignore_index=True).dropna(subset=[key])
    # Keep the first raw record each id was seen in as its source reference.
    out = allrefs.drop_duplicates(subset=[key], keep="first").reset_index(drop=True)
    for fname, fm in em.fields.items():
        if fm.status is MappingStatus.DERIVED and fname != key:
            out[fname] = DERIVATIONS[fm.derivation](out, fm.params)  # type: ignore[index]
    out["derived"] = True
    out.attrs["derived_fields"] = [key] + [f for f, fm in em.fields.items()
                                            if fm.status is MappingStatus.DERIVED and f != key]
    out.attrs["derived_entity"] = True
    return out


def apply_mapping(cfg: MappingConfig, raw_tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    # Table-backed entities first, then entities derived from their fields.
    for name, em in cfg.entities.items():
        if em.table:
            frames[name] = _entity_from_table(name, em, raw_tables[em.table], em.table)
    for name, em in cfg.entities.items():
        if not em.table and em.derived_from:
            frames[name] = _entity_from_refs(name, em, frames)
    return frames
