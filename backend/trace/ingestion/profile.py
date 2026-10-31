"""Dataset profiler. Generic: knows nothing about any particular dataset.

Usage (from backend/):
    python -m trace.ingestion.profile --source ../data/raw/<file-or-dir> --out ../docs/dataset_profile.md
    python -m trace.ingestion.profile --mapping ../config/mapping.yaml --out ../docs/dataset_profile.md

Optional flow hints (needed for account-to-account degree and threshold clustering when no mapping
exists yet): --src-col, --dst-col, --amount-col, --ts-col, --table.

The written profile contains aggregate statistics only. Raw values are shown only for
low-cardinality columns (categorical vocabularies), never for identifier-like columns.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from trace.domain.detectors.population import threshold_clustering

_FILE_EXT = (".csv", ".tsv", ".txt", ".parquet", ".pq", ".csv.gz")
_PCTS = [0.01, 0.05, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.999]
# Column-name hint for possible ground-truth columns. Only flags candidates for human confirmation.
_LABEL_HINT = re.compile(r"(fraud|launder|label|suspicious|is_?sar|target|class|alert)", re.I)
_LOW_CARD = 25


@dataclass
class Hints:
    table: str | None = None
    src: str | None = None
    dst: str | None = None
    amount: str | None = None
    ts: str | None = None


@dataclass
class TableProfile:
    name: str
    path: str
    rows: int
    columns: list[dict[str, Any]] = field(default_factory=list)
    duplicate_rows: int = 0
    candidate_keys: list[str] = field(default_factory=list)
    timestamps: dict[str, dict[str, Any]] = field(default_factory=dict)
    numerics: dict[str, dict[str, Any]] = field(default_factory=dict)
    label_candidates: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------------------------- io

def discover(source: Path) -> dict[str, Path]:
    if source.is_file():
        return {source.name.split(".")[0]: source}
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.name.lower().endswith(_FILE_EXT))
    return {p.relative_to(source).as_posix().split(".")[0]: p for p in files}


def read_any(path: Path, nrows: int | None) -> pd.DataFrame:
    name = path.name.lower()
    if name.endswith((".parquet", ".pq")):
        df = pd.read_parquet(path)
        return df.head(nrows) if nrows else df
    sep = "\t" if name.endswith(".tsv") else None
    if nrows is None and sep is None:
        try:
            return pd.read_csv(path, engine="pyarrow")
        except Exception:  # noqa: BLE001 - fall back to the python parser on any pyarrow failure
            pass
    return pd.read_csv(path, nrows=nrows, sep=sep, engine="python" if sep is None else "c", low_memory=False)


# ------------------------------------------------------------------------------------- profiling

def _infer_kind(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "timestamp"
    if pd.api.types.is_numeric_dtype(s):
        return "number"
    nn = s.dropna().astype(str)
    if nn.empty:
        return "empty"
    sample = nn.sample(min(len(nn), 2000), random_state=0)
    if pd.to_numeric(sample, errors="coerce").notna().mean() >= 0.98:
        return "numeric-string"
    if sample.str.contains(r"[-/:]").mean() > 0.9:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.95:
            return "timestamp-string"
    return "string"


def _as_ts(s: pd.Series) -> pd.Series:
    return s if pd.api.types.is_datetime64_any_dtype(s) else pd.to_datetime(s, errors="coerce", format="mixed")


def _ts_profile(s: pd.Series) -> dict[str, Any]:
    ts = _as_ts(s)
    valid = ts.dropna()
    if valid.empty:
        return {}
    diffs = valid.diff().dropna()
    sorted_diffs = valid.sort_values().diff().dropna()
    biggest = sorted_diffs.nlargest(3)
    tz = getattr(valid.dt, "tz", None)
    return {
        "min": str(valid.min()), "max": str(valid.max()),
        "timezone_in_data": str(tz) if tz else "naive (no tz info)",
        "unparseable": int(s.notna().sum() - len(valid)),
        "in_file_order": bool(valid.is_monotonic_increasing),
        "backwards_steps": int((diffs < pd.Timedelta(0)).sum()),
        "median_gap": str(sorted_diffs.median()) if len(sorted_diffs) else None,
        "largest_gaps": [str(g) for g in biggest],
        "distinct_dates": int(valid.dt.normalize().nunique()),
        "resolution_has_seconds": bool((valid.dt.second != 0).any()),
    }


def _round_share(x: np.ndarray) -> dict[str, float]:
    x = x[np.isfinite(x) & (x > 0)]
    if x.size == 0:
        return {}
    out = {}
    for base in (1, 10, 100, 1000):
        out[f"multiple_of_{base}"] = round(float(np.mean(np.isclose(np.mod(x, base), 0) |
                                                         np.isclose(np.mod(x, base), base))), 4)
    return out


def _num_profile(s: pd.Series) -> dict[str, Any]:
    x = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    fin = x[np.isfinite(x)]
    if fin.size == 0:
        return {}
    return {
        "min": float(fin.min()), "max": float(fin.max()), "mean": float(fin.mean()),
        "zeros": int((fin == 0).sum()), "negatives": int((fin < 0).sum()),
        "percentiles": {f"p{p * 100:g}": float(v) for p, v in zip(_PCTS, np.quantile(fin, _PCTS))},
        "round_number_share": _round_share(fin),
    }


def profile_table(name: str, path: Path, df: pd.DataFrame) -> TableProfile:
    tp = TableProfile(name=name, path=str(path), rows=len(df))
    tp.duplicate_rows = int(df.duplicated().sum())
    for col in df.columns:
        s = df[col]
        kind = _infer_kind(s)
        nunique = int(s.nunique(dropna=True))
        info: dict[str, Any] = {
            "column": col, "dtype": str(s.dtype), "inferred": kind,
            "null_rate": round(float(s.isna().mean()), 4), "distinct": nunique,
        }
        if nunique <= _LOW_CARD and kind in ("string", "boolean", "numeric-string", "number"):
            vc = s.value_counts(dropna=True).head(_LOW_CARD)
            info["values"] = {str(k): int(v) for k, v in vc.items()}
        tp.columns.append(info)
        if nunique == len(df) and s.notna().all():
            tp.candidate_keys.append(col)
        if kind in ("timestamp", "timestamp-string"):
            tp.timestamps[col] = _ts_profile(s)
        if kind in ("number", "numeric-string") and nunique > _LOW_CARD:
            tp.numerics[col] = _num_profile(s)
        if nunique == 2 and (_LABEL_HINT.search(str(col)) or kind == "boolean"):
            tp.label_candidates.append({"column": col, "values": info.get("values", {})})
    return tp


def degree_profile(df: pd.DataFrame, src: str, dst: str) -> dict[str, Any]:
    pairs = df[[src, dst]].dropna().drop_duplicates()
    out_deg = pairs.groupby(src)[dst].nunique()
    in_deg = pairs.groupby(dst)[src].nunique()
    senders, receivers = pd.Index(pairs[src].unique()), pd.Index(pairs[dst].unique())
    accounts = senders.union(receivers)
    self_loops = int((df[src] == df[dst]).sum())

    def pct(s: pd.Series) -> dict[str, float]:
        return {f"p{p * 100:g}": float(v) for p, v in zip(_PCTS, s.quantile(_PCTS))} | {"max": float(s.max())}

    return {
        "distinct_accounts": int(len(accounts)),
        "distinct_pairs": int(len(pairs)),
        "self_transfers": self_loops,
        "out_degree_distinct_counterparties": pct(out_deg),
        "in_degree_distinct_counterparties": pct(in_deg),
        "accounts_only_sending": int(len(accounts.difference(receivers))),
        "accounts_only_receiving": int(len(accounts.difference(senders))),
    }


def referential_gaps(tables: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Columns sharing a name across tables: share of values in A with no match in B."""
    res = []
    names = list(tables)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for col in set(tables[a].columns) & set(tables[b].columns):
                va, vb = set(tables[a][col].dropna().astype(str)), set(tables[b][col].dropna().astype(str))
                if not va or not vb:
                    continue
                res.append({"column": col, "a": a, "b": b,
                            "a_not_in_b": round(len(va - vb) / len(va), 4),
                            "b_not_in_a": round(len(vb - va) / len(vb), 4)})
    return res


# ---------------------------------------------------------------------------------------- report

def _md_table(rows: list[list[Any]], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def render(profiles: list[TableProfile], flow: dict[str, Any], gaps: list[dict[str, Any]],
           hints: Hints) -> str:
    md = ["# Dataset profile", "",
          "Generated by `backend/trace/ingestion/profile.py`. Aggregate statistics only; raw values are "
          "shown only for low-cardinality columns.", ""]
    for tp in profiles:
        md += [f"## Table `{tp.name}`", "", f"- Path: `{tp.path}`", f"- Rows: **{tp.rows:,}**",
               f"- Exact duplicate rows: {tp.duplicate_rows:,}",
               f"- Candidate keys (unique, non-null): {', '.join(tp.candidate_keys) or 'none'}", "",
               "### Columns", ""]
        md.append(_md_table([[c["column"], c["dtype"], c["inferred"], f'{c["null_rate"]:.2%}', f'{c["distinct"]:,}',
                              ", ".join(f"{k} ({v:,})" for k, v in c.get("values", {}).items()) or "-"]
                             for c in tp.columns],
                            ["column", "dtype", "inferred", "null rate", "distinct", "values (low-cardinality only)"]))
        if tp.timestamps:
            md += ["", "### Timestamps", ""]
            for col, t in tp.timestamps.items():
                md.append(f"- `{col}`: {t.get('min')} → {t.get('max')}; tz: {t.get('timezone_in_data')}; "
                          f"in file order: {t.get('in_file_order')} (backwards steps {t.get('backwards_steps')}); "
                          f"unparseable: {t.get('unparseable')}; distinct dates: {t.get('distinct_dates')}; "
                          f"median gap: {t.get('median_gap')}; largest gaps: {', '.join(t.get('largest_gaps', []))}; "
                          f"has seconds: {t.get('resolution_has_seconds')}")
        if tp.numerics:
            md += ["", "### Numeric distributions", ""]
            rows = []
            for col, n in tp.numerics.items():
                p = n["percentiles"]
                rows.append([col, f"{n['min']:,.2f}", *[f"{v:,.2f}" for v in p.values()], f"{n['max']:,.2f}",
                             n["zeros"], n["negatives"],
                             ", ".join(f"{k.split('_')[-1]}:{v:.1%}" for k, v in n["round_number_share"].items())])
            md.append(_md_table(rows, ["column", "min", *[k for k in next(iter(tp.numerics.values()))["percentiles"]],
                                       "max", "zeros", "neg", "round-number share"]))
        md += ["", "### Label / ground-truth candidates", ""]
        if tp.label_candidates:
            for lc in tp.label_candidates:
                md.append(f"- `{lc['column']}`: {lc['values']} (candidate only — confirm meaning before use; "
                          "report-only, never used for tuning)")
        else:
            md.append("- none detected")
        md.append("")

    md += ["## Flow statistics", ""]
    if not flow:
        md.append("Not computed: provide `--src-col/--dst-col/--amount-col/--ts-col` (or a filled mapping) "
                  "to compute account-to-account degree and threshold clustering.")
    else:
        md.append(f"Hints used: table `{hints.table}`, src `{hints.src}`, dst `{hints.dst}`, "
                  f"amount `{hints.amount}`, ts `{hints.ts}`")
        if "degree" in flow:
            d = flow["degree"]
            md += ["", f"- Distinct accounts: {d['distinct_accounts']:,}; distinct pairs: {d['distinct_pairs']:,}; "
                   f"self-transfers: {d['self_transfers']:,}; only-sending: {d['accounts_only_sending']:,}; "
                   f"only-receiving: {d['accounts_only_receiving']:,}", ""]
            md.append(_md_table([["out (distinct payees)", *[f"{v:g}" for v in d["out_degree_distinct_counterparties"].values()]],
                                 ["in (distinct payers)", *[f"{v:g}" for v in d["in_degree_distinct_counterparties"].values()]]],
                                ["degree", *d["out_degree_distinct_counterparties"].keys()]))
        if flow.get("threshold_clustering"):
            md += ["", "### Threshold clustering candidates (count just below vs just above round marks, ±10%)", ""]
            md.append(_md_table([[f"{r['mark']:,g}", r["below"], r["above"], r["ratio_below_above"]]
                                 for r in flow["threshold_clustering"]], ["mark", "below", "above", "below/above"]))
    md += ["", "## Referential overlap (columns sharing a name across tables)", ""]
    md.append(_md_table([[g["column"], g["a"], g["b"], f"{g['a_not_in_b']:.2%}", f"{g['b_not_in_a']:.2%}"] for g in gaps],
                        ["column", "A", "B", "A not in B", "B not in A"]) if gaps else "- single table or no shared column names")
    return "\n".join(md) + "\n"


# ------------------------------------------------------------------------------------------ main

def run(files: dict[str, Path], hints: Hints, nrows: int | None = None) -> tuple[
        list[TableProfile], dict[str, Any], list[dict[str, Any]], dict[str, pd.DataFrame]]:
    if not files:
        raise FileNotFoundError("No csv/parquet files to profile")
    tables = {name: read_any(p, nrows) for name, p in files.items()}
    profiles = [profile_table(n, files[n], df) for n, df in tables.items()]
    flow: dict[str, Any] = {}
    tname = hints.table or (next(iter(tables)) if len(tables) == 1 else None)
    if tname and tname in tables:
        hints.table = tname
        df = tables[tname]
        if hints.src and hints.dst:
            flow["degree"] = degree_profile(df, hints.src, hints.dst)
        if hints.amount:
            flow["threshold_clustering"] = threshold_clustering(
                pd.to_numeric(df[hints.amount], errors="coerce").to_numpy(dtype=float))
    return profiles, flow, referential_gaps(tables), tables


def _from_mapping(path: Path) -> tuple[dict[str, Path], Hints]:
    from trace.ingestion.mapping import load_mapping

    cfg = load_mapping(path)
    repo_root = path.resolve().parent.parent  # mapping lives in <repo>/config/
    files = {}
    for name, spec in cfg.source.tables.items():
        if "path" in spec:
            p = Path(spec["path"])
            files[name] = p if p.is_absolute() else repo_root / p
    txn = cfg.entities.get("Transaction")
    hints = Hints()
    if txn:
        hints.table = txn.table
        col = {f: m.column for f, m in txn.fields.items() if m.column}
        hints.src, hints.dst = col.get("src_account_id"), col.get("dst_account_id")
        hints.amount, hints.ts = col.get("amount"), col.get("ts")
    return files, hints


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, help="data file or directory")
    ap.add_argument("--mapping", type=Path, help="use source + flow hints from a filled mapping.yaml")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--json", type=Path, help="also write machine-readable profile JSON")
    ap.add_argument("--table"), ap.add_argument("--src-col"), ap.add_argument("--dst-col")
    ap.add_argument("--amount-col"), ap.add_argument("--ts-col")
    ap.add_argument("--nrows", type=int, help="profile only the first N rows of each table")
    a = ap.parse_args(argv)

    hints = Hints(a.table, a.src_col, a.dst_col, a.amount_col, a.ts_col)
    files = discover(a.source) if a.source else {}
    if a.mapping:
        mfiles, mhints = _from_mapping(a.mapping)
        files = files or mfiles
        hints = Hints(*(x or y for x, y in zip(vars(hints).values(), vars(mhints).values())))
    if not files:
        print("No source: pass --source or a mapping with source.tables filled in.", file=sys.stderr)
        return 2

    profiles, flow, gaps, _ = run(files, hints, a.nrows)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(profiles, flow, gaps, hints), encoding="utf-8")
    if a.json:
        a.json.write_text(json.dumps({"tables": [vars(p) for p in profiles], "flow": flow, "referential": gaps},
                                     default=str, indent=2), encoding="utf-8")
    for tp in profiles:
        print(f"{tp.name}: {tp.rows:,} rows, {len(tp.columns)} cols, keys={tp.candidate_keys}, "
              f"labels={[c['column'] for c in tp.label_candidates]}")
    print(f"Profile written to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
