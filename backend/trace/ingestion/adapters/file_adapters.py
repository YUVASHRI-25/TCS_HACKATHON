"""CSV, Parquet and SQL source adapters."""

from __future__ import annotations

import pandas as pd

from trace.ingestion.adapters.base import SourceAdapter


class CsvAdapter(SourceAdapter):
    def load(self, table: str, nrows: int | None = None) -> pd.DataFrame:
        opts = dict(self.tables[table].get("read_options") or {})
        # Read as strings so nothing is coerced before profiling/normalisation decides types.
        opts.setdefault("dtype", str)
        opts.setdefault("keep_default_na", False)
        opts.setdefault("na_values", [""])
        return self._with_row_ref(pd.read_csv(self._path(table), nrows=nrows, **opts))


class ParquetAdapter(SourceAdapter):
    def load(self, table: str, nrows: int | None = None) -> pd.DataFrame:
        df = pd.read_parquet(self._path(table), **(self.tables[table].get("read_options") or {}))
        if nrows is not None:
            df = df.head(nrows)
        return self._with_row_ref(df)


class SqlAdapter(SourceAdapter):
    def load(self, table: str, nrows: int | None = None) -> pd.DataFrame:
        from sqlalchemy import create_engine, text

        url = self.source_opts.get("url")
        if not url:
            raise ValueError("sql adapter requires source.url in mapping.yaml")
        spec = self.tables[table]
        query = spec.get("query") or f"SELECT * FROM {table}"
        with create_engine(url).connect() as conn:
            df = pd.read_sql(text(query), conn)
        if nrows is not None:
            df = df.head(nrows)
        return self._with_row_ref(df)


ADAPTERS: dict[str, type[SourceAdapter]] = {"csv": CsvAdapter, "parquet": ParquetAdapter, "sql": SqlAdapter}


def adapter_for_path(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".parquet", ".pq")):
        return "parquet"
    if lower.endswith((".csv", ".tsv", ".txt", ".csv.gz")):
        return "csv"
    raise ValueError(f"Cannot infer adapter for {path}; declare source.adapter in mapping.yaml")
