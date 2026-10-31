"""Pipeline use case: ingest -> validate -> (resolve -> graph -> detect -> cases -> persist).

Stages after validation are added in Phases 1-3. Idempotent: outputs are fully rewritten each run.
"""

from __future__ import annotations

import json
import logging

from trace.infrastructure.settings import REPO_ROOT, Settings, get_settings
from trace.ingestion import capabilities as caps
from trace.ingestion.mapping import apply_mapping, build_adapter, load_mapping
from trace.ingestion.normalise import normalise
from trace.ingestion.validate import validate

log = logging.getLogger(__name__)


class MappingNotConfigured(RuntimeError):
    pass


def run(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    cfg = load_mapping(s.path(s.trace_mapping_path))
    if cfg.is_empty:
        raise MappingNotConfigured(
            f"{s.trace_mapping_path} has no source tables/entities yet. Profile the dataset and fill the mapping first.")

    out_dir = s.path(s.trace_processed_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = build_adapter(cfg, REPO_ROOT).load_all()
    log.info("loaded raw tables: %s", {k: len(v) for k, v in raw.items()})
    frames = apply_mapping(cfg, raw)
    frames, issues = normalise(frames, cfg.source.timezone)
    frames, report = validate(frames, issues)

    cap_rows = caps.capability_table(cfg)
    (out_dir / "validation_report.json").write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    (out_dir / "capabilities.json").write_text(json.dumps([c.to_dict() for c in cap_rows], indent=2),
                                               encoding="utf-8")
    for entity, q in report.quarantined.items():
        q.to_csv(out_dir / f"quarantine_{entity}.csv", index=False)
    for entity, df in frames.items():
        df.to_parquet(out_dir / f"{entity}.parquet", index=False)

    return {"row_counts": report.row_counts, "validation_ok": report.ok,
            "capabilities": {c.id: c.enabled for c in cap_rows}}
