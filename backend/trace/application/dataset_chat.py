"""Chat about an uploaded dataset. The profile is computed from the real file rows; the LLM only explains it and may
cite only tables/columns that exist in the profile. No answer is produced when the LLM is unavailable."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel, Field, ValidationError

from trace.application.copilot import BANNED
from trace.infrastructure.container import Container
from trace.intelligence.llm.client import LlmClient, LlmError

MAX_COLS = 40
MAX_HISTORY = 6

SYSTEM = """You are the data-intake assistant of TRACE, a financial-crime investigation tool. An investigator has
uploaded a dataset. Reason ONLY from the JSON profile provided (computed from the real file). Never invent rows,
values, columns or statistics. Say what the data can and cannot support (e.g. missing fields, tiny sample, duplicates,
unusual distributions) and what an investigator should check next. Anomalous is not criminal; never state guilt.
Use "today" to judge whether dates are past or future. Cite the tables/columns you rely on as "table" or "table.column" exactly as in the profile.
Return ONLY JSON: {"answer": str, "findings": [{"text": str, "refs": [str]}], "data_limitations": [str],
"suggested_next_steps": [str]}"""


class Finding(BaseModel):
    text: str
    refs: list[str] = Field(default_factory=list)


class DatasetAnswer(BaseModel):
    answer: str
    findings: list[Finding] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)


class DatasetChatError(RuntimeError):
    pass


def _table_paths(c: Container, d: dict[str, Any]) -> dict[str, Path]:
    mp = Path(d["mapping_path"]) if d.get("mapping_path") else c.settings.path(c.settings.trace_mapping_path)
    raw = yaml.safe_load(mp.read_text(encoding="utf-8"))
    out = {}
    for f in d["files"]:
        spec = raw.get("source", {}).get("tables", {}).get(f["table"])
        if spec and spec.get("path"):
            p = Path(spec["path"])
            out[f["table"]] = p if p.is_absolute() else c.settings.path(p)
    return out


def _profile_table(df: pd.DataFrame) -> dict[str, Any]:
    cols = []
    for name in list(df.columns)[:MAX_COLS]:
        s = df[name]
        info: dict[str, Any] = {"name": str(name), "dtype": str(s.dtype), "nulls": int(s.isna().sum()),
                                "distinct": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            q = s.quantile([0.5, 0.95]).to_dict()
            info.update({"min": float(s.min()), "median": float(q[0.5]), "p95": float(q[0.95]), "max": float(s.max())})
        else:
            if 0 < info["distinct"] <= 12:
                info["value_counts"] = {str(k): int(v) for k, v in s.value_counts().items()}
            if s.dtype == object and s.notna().any():
                t = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
                if t.notna().mean() > 0.9:
                    info["datetime_range"] = [str(t.min()), str(t.max())]
        cols.append(info)
    return {"rows": int(len(df)), "n_columns": int(df.shape[1]), "columns": cols,
            "fully_duplicate_rows": int(df.duplicated().sum()),
            "sample_rows": json.loads(df.head(3).to_json(orient="records", date_format="iso"))}


def build_profile(c: Container, d: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    prof: dict[str, Any] = {"dataset": {"id": d["id"], "name": d["name"], "status": d["status"],
                                        "uploaded_by": d["created_by"], "validation_message": d.get("message")},
                            "tables": {}}
    allowed: set[str] = set()
    if d["status"] == "rejected":
        prof["note"] = "This upload was rejected; its file content was not stored, so only the rejection reason is known."
        return prof, allowed
    for table, path in _table_paths(c, d).items():
        if not path.exists():
            prof["tables"][table] = {"error": f"file not found: {path.name}"}
            continue
        try:
            df = pd.read_csv(path)
        except Exception as e:  # noqa: BLE001 - reported to the investigator
            prof["tables"][table] = {"error": f"unreadable: {e}"}
            continue
        prof["tables"][table] = _profile_table(df)
        allowed.add(table)
        allowed.update(f"{table}.{col}" for col in df.columns)
    return prof, allowed


def ask(c: Container, d: dict[str, Any], question: str, history: list[dict[str, str]], llm: LlmClient,
        user: str) -> dict[str, Any]:
    q = question.strip()
    if not q:
        raise DatasetChatError("question is empty")
    prof, allowed = build_profile(c, d)
    payload = json.dumps({"today": date.today().isoformat(), "question": q, "recent_conversation": history[-MAX_HISTORY:], "profile": prof}, default=str)
    cid = f"DATASET-{d['id']}"
    try:
        obj, raw = llm.chat_json(SYSTEM, payload)
    except LlmError as e:
        c.llm_audit.record(cid, "dataset_chat", llm.model or "unconfigured", q, None, f"error: {e}")
        raise
    try:
        ans = DatasetAnswer.model_validate(obj)
    except ValidationError as e:
        c.llm_audit.record(cid, "dataset_chat", llm.model or "", q, raw, "invalid_schema")
        raise LlmError(f"LLM output failed schema validation: {e.errors()[:2]}") from e
    blob = json.dumps(ans.model_dump()).lower()
    if any(w in blob for w in BANNED):
        c.llm_audit.record(cid, "dataset_chat", llm.model or "", q, raw, "guardrail_refused")
        raise LlmError("LLM output was refused by the guardrail (banned wording). Rephrase and ask again.")
    lower = {a.lower(): a for a in allowed}
    for f in ans.findings:  # tolerate case/whitespace differences only; anything else is rejected
        f.refs = [lower.get(r.strip().lower(), r) for r in f.refs]
    rejected = sorted({r for f in ans.findings for r in f.refs if r not in allowed})
    for f in ans.findings:
        f.refs = [r for r in f.refs if r in allowed]
    c.llm_audit.record(cid, "dataset_chat", llm.model or "", q, raw, "ok")
    c.audit.append("SYSTEM", user, "dataset_chat", {"dataset": d["id"], "question": q, "model": llm.model})
    out = ans.model_dump()
    out.update({"rejected_refs": rejected, "model": llm.model,
                "profile_tables": {t: v.get("rows") for t, v in prof["tables"].items()}})
    return out
