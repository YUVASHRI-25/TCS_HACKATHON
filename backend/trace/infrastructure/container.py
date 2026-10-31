"""Dependency-injection container: binds data_access ports to concrete adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import pandas as pd

from trace.data_access.audit.chain import SqlAuditStore
from trace.data_access.relational.store import SqlCaseRepository, SqlLlmAudit, make_engine
from trace.infrastructure.config import TraceConfig, load_config
from trace.infrastructure.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    _frames: dict[str, pd.DataFrame] | None = field(default=None, repr=False)

    @cached_property
    def engine(self):
        return make_engine(self.settings.database_url)

    @cached_property
    def cases(self) -> SqlCaseRepository:
        return SqlCaseRepository(self.engine)

    @cached_property
    def audit(self) -> SqlAuditStore:
        return SqlAuditStore(self.engine)

    @cached_property
    def llm_audit(self) -> SqlLlmAudit:
        return SqlLlmAudit(self.engine)

    @property
    def config(self) -> TraceConfig:
        return load_config(self.settings)

    def frames(self) -> dict[str, pd.DataFrame]:
        """Canonical frames written by the pipeline (data/processed/*.parquet)."""
        if self._frames is None:
            d = self.settings.path(self.settings.trace_processed_dir)
            self._frames = {p.stem: pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))
                            if not p.stem.startswith("raw_")}
        return self._frames

    def raw_table(self, table: str) -> pd.DataFrame | None:
        p = self.settings.path(self.settings.trace_processed_dir) / f"raw_{table}.parquet"
        return pd.read_parquet(p) if p.exists() else None

    @cached_property
    def graph(self):
        from trace.data_access.graph.networkx_store import NetworkxGraphStore
        return NetworkxGraphStore(self.frames())

    def reset_cache(self) -> None:
        self._frames = None
        for k in ("graph",):
            self.__dict__.pop(k, None)


_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container(settings=get_settings())
    return _container


def build_container() -> Container:
    return get_container()
