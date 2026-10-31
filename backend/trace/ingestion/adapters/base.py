"""Source adapter port: load named raw tables as DataFrames, untouched."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class SourceAdapter(ABC):
    def __init__(self, tables: dict[str, dict[str, Any]], base_dir: Path, **source_opts: Any) -> None:
        self.tables = tables
        self.base_dir = base_dir
        self.source_opts = source_opts

    def table_names(self) -> list[str]:
        return list(self.tables)

    @abstractmethod
    def load(self, table: str, nrows: int | None = None) -> pd.DataFrame:
        """Return raw rows with every column as read. Adds `_source_row` (0-based row number in source)."""

    def load_all(self, nrows: int | None = None) -> dict[str, pd.DataFrame]:
        return {t: self.load(t, nrows=nrows) for t in self.tables}

    def _path(self, table: str) -> Path:
        p = Path(self.tables[table]["path"])
        return p if p.is_absolute() else self.base_dir / p

    @staticmethod
    def _with_row_ref(df: pd.DataFrame) -> pd.DataFrame:
        df = df.reset_index(drop=True)
        df.insert(0, "_source_row", range(len(df)))
        return df
