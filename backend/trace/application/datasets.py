"""Dataset upload and analysis runs.

An upload is accepted when every file matches a table of the configured mapping (by file name, or
uniquely by its columns) and contains every column that table's mapping uses. Accepted files get their
own mapping (the configured one, with those tables pointed at the uploaded files); tables not uploaded
keep their configured source. Files in an unknown format are rejected with the columns expected, never
guessed. Runs execute the normal pipeline in a background thread, one at a time.
"""

from __future__ import annotations

import io
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from trace.application.accounts import SYSTEM
from trace.infrastructure.container import Container, get_container
from trace.ingestion.mapping import MappingConfig, load_mapping

log = logging.getLogger(__name__)
MAX_BYTES = 200 * 1024 * 1024
_run_lock = threading.Lock()


class DatasetError(ValueError):
    pass


def table_columns(cfg: MappingConfig) -> dict[str, set[str]]:
    """Columns each configured source table must contain (those the mapping reads directly)."""
    need: dict[str, set[str]] = {t: set() for t in cfg.source.tables}
    for em in cfg.entities.values():
        if em.table:
            need[em.table] |= {fm.column for fm in em.fields.values() if fm.column}
    return need


def ensure_configured_dataset(c: Container) -> None:
    if c.datasets.list():
        return
    cfg = load_mapping(c.settings.path(c.settings.trace_mapping_path))
    files = [{"table": t, "file": spec.get("path"), "rows": None} for t, spec in cfg.source.tables.items()]
    d = c.datasets.create("Configured dataset (config/mapping.yaml)", "system", "ready", files, None,
                          "Source declared in config/mapping.yaml")
    if c.cases.latest_run() is not None:
        c.datasets.set_active(d["id"])


def upload(c: Container, name: str, files: list[tuple[str, bytes]], user: str) -> dict[str, Any]:
    if not files:
        raise DatasetError("no files received")
    cfg = load_mapping(c.settings.path(c.settings.trace_mapping_path))
    need = table_columns(cfg)
    matched: dict[str, tuple[str, bytes, int, list[str]]] = {}
    problems: list[str] = []
    for fname, data in files:
        if not fname.lower().endswith(".csv"):
            problems.append(f"{fname}: only .csv files are accepted")
            continue
        if len(data) > MAX_BYTES:
            problems.append(f"{fname}: larger than {MAX_BYTES // 1024 // 1024} MB")
            continue
        try:
            head = pd.read_csv(io.BytesIO(data), nrows=0)
            rows = sum(1 for _ in io.BytesIO(data)) - 1
        except Exception as e:  # noqa: BLE001 - report any parse failure to the uploader
            problems.append(f"{fname}: not a readable CSV ({e})")
            continue
        cols = {str(x) for x in head.columns}
        stem = Path(fname).stem.lower()
        if stem in need:
            table = stem
        else:
            cands = [t for t, req in need.items() if req and req <= cols]
            if len(cands) != 1:
                problems.append(f"{fname}: does not match a configured table "
                                f"({'ambiguous: ' + ', '.join(cands) if cands else 'no table has all its columns'}). "
                                f"Name the file after its table, e.g. transactions.csv")
                continue
            table = cands[0]
        missing = sorted(need[table] - cols)
        if missing:
            problems.append(f"{fname} -> {table}: missing required columns {missing}; expected at least "
                            f"{sorted(need[table])}")
            continue
        matched[table] = (fname, data, rows, sorted(cols))

    file_rows = [{"table": t, "file": f, "rows": r} for t, (f, _, r, _) in matched.items()]
    if problems or not matched:
        d = c.datasets.create(name or "Upload", user, "rejected", file_rows, None,
                              "; ".join(problems) or "no file matched a configured table")
        c.audit.append(SYSTEM, user, "upload_rejected", {"dataset": d["id"], "problems": problems})
        return d

    uploads = c.settings.path(c.settings.trace_processed_dir).parent / "uploads"
    folder = uploads / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{secrets.token_hex(3)}"
    folder.mkdir(parents=True, exist_ok=True)
    raw = yaml.safe_load(c.settings.path(c.settings.trace_mapping_path).read_text(encoding="utf-8"))
    for table, (_, data, _, _) in matched.items():
        target = folder / f"{table}.csv"
        target.write_bytes(data)
        raw["source"]["tables"][table]["path"] = target.as_posix()
    mpath = folder / "mapping.yaml"
    mpath.write_text("# Generated for an uploaded dataset: configured mapping with uploaded tables substituted.\n"
                     + yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    kept = sorted(set(need) - set(matched))
    msg = f"{len(matched)} table(s) uploaded; " + (f"configured source kept for: {', '.join(kept)}" if kept else "all tables uploaded")
    d = c.datasets.create(name or "Upload", user, "ready", file_rows, mpath.as_posix(), msg)
    c.audit.append(SYSTEM, user, "upload_dataset", {"dataset": d["id"], "tables": sorted(matched)})
    return d


def start_run(c: Container, dataset_id: int, user: str) -> int:
    d = c.datasets.get(dataset_id)
    if d is None:
        raise DatasetError("dataset not found")
    if d["status"] == "rejected":
        raise DatasetError("this upload was rejected; fix the files and upload again")
    if not _run_lock.acquire(blocking=False):
        raise DatasetError("an analysis run is already in progress")
    rid = c.datasets.start_run(dataset_id, user)
    c.audit.append(SYSTEM, user, "start_analysis", {"dataset": dataset_id, "run": rid})
    threading.Thread(target=_run, args=(dataset_id, rid, user, d["mapping_path"]), daemon=True).start()
    return rid


def _run(dataset_id: int, rid: int, user: str, mapping_path: str | None) -> None:
    from trace.application.run_pipeline import run as run_pipeline

    base = get_container()
    try:
        settings = base.settings.model_copy(update={"trace_mapping_path": Path(mapping_path)}) if mapping_path else base.settings
        summary = run_pipeline(Container(settings=settings))
        base.datasets.finish_run(rid, "succeeded", summary)
        base.datasets.set_active(dataset_id)
        base.audit.append(SYSTEM, user, "analysis_succeeded", {"dataset": dataset_id, "run": rid,
                                                                "tiers": summary.get("tiers")})
    except Exception as e:  # noqa: BLE001 - surface every failure in the run history
        log.exception("analysis run failed")
        base.datasets.finish_run(rid, "failed", error=f"{type(e).__name__}: {e}")
        base.audit.append(SYSTEM, user, "analysis_failed", {"dataset": dataset_id, "run": rid, "error": str(e)})
    finally:
        base.reset_cache()
        _run_lock.release()
