"""End-to-end: tiny hand-built CSV -> full pipeline -> API. Fixture data lives only in this test."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from trace.api.main import app
from trace.application.run_pipeline import run
from trace.domain.guardrails.policy import banned_terms_in
from trace.infrastructure.container import Container, get_container
from trace.infrastructure.settings import REPO_ROOT, Settings


def _dataset(path):
    rng = np.random.default_rng(7)
    base = pd.Timestamp("2024-01-01")
    rows = []
    # background: 60 accounts, 600 transfers over 90 days, own device each
    for i in range(600):
        a, b = rng.choice(60, 2, replace=False)
        rows.append({"id": f"bg{i}", "when": base + pd.Timedelta(minutes=int(rng.integers(0, 90 * 1440))),
                     "from": f"BG{a}", "to": f"BG{b}", "amt": round(float(rng.uniform(50, 5000)), 2), "dev": f"DEV{a}"})
    # pattern: 25 payers -> M1 (fan-in), each forwarded within seconds along M1 -> M2 -> M3, shared device
    t = base + pd.Timedelta(days=40)
    for i in range(25):
        ts = t + pd.Timedelta(minutes=10 * i)
        rows.append({"id": f"in{i}", "when": ts, "from": f"P{i}", "to": "M1", "amt": 900.0, "dev": f"PDEV{i}"})
        rows.append({"id": f"f1_{i}", "when": ts + pd.Timedelta(seconds=30), "from": "M1", "to": "M2", "amt": 880.0, "dev": "SHARED"})
        rows.append({"id": f"f2_{i}", "when": ts + pd.Timedelta(seconds=60), "from": "M2", "to": "M3", "amt": 860.0, "dev": "SHARED"})
    df = pd.DataFrame(rows).sort_values("when")
    df["when"] = df["when"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(path, index=False)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("trace")
    _dataset(d / "tx.csv")
    mapping = {"source": {"adapter": "csv", "timezone": "UTC", "tables": {"tx": {"path": str(d / "tx.csv")}}},
               "entities": {
                   "Transaction": {"table": "tx", "fields": {
                       "txn_id": {"status": "direct", "column": "id"}, "ts": {"status": "direct", "column": "when"},
                       "src_account_id": {"status": "direct", "column": "from"},
                       "dst_account_id": {"status": "direct", "column": "to"},
                       "amount": {"status": "direct", "column": "amt"}, "device_id": {"status": "direct", "column": "dev"}}},
                   "Account": {"derived_from": ["Transaction.src_account_id", "Transaction.dst_account_id"],
                               "fields": {"account_id": {"status": "derived", "derivation": "same_as",
                                                         "params": {"column": "account_id"}}}}}}
    (d / "config").mkdir()
    (d / "config" / "mapping.yaml").write_text(yaml.safe_dump(mapping), encoding="utf-8")
    shutil.copy(REPO_ROOT / "config" / "detectors.yaml", d / "config" / "detectors.yaml")
    shutil.copy(REPO_ROOT / "config" / "catalogues.yaml", d / "config" / "catalogues.yaml")
    s = Settings(trace_mapping_path=d / "config" / "mapping.yaml", trace_detectors_path=d / "config" / "detectors.yaml",
                 trace_catalogues_path=d / "config" / "catalogues.yaml", trace_processed_dir=d / "processed",
                 database_url=f"sqlite:///{(d / 'trace.db').as_posix()}")
    c = Container(settings=s)
    result = run(c)
    app.dependency_overrides[get_container] = lambda: c
    yield c, result, TestClient(app), d
    app.dependency_overrides.clear()


def test_pipeline_surfaces_the_pattern_network(env):
    c, result, _, d = env
    rows = c.cases.all_rows()
    assert rows, result
    members = [{e["raw_id"] for e in c.cases.get(r["id"])["entities"] if e["role"] == "member"} for r in rows]
    assert any({"M1", "M2"} <= m for m in members)
    thresholds = yaml.safe_load((d / "config" / "detectors.thresholds.yaml").read_text(encoding="utf-8"))
    assert all("derivation" in v for det in thresholds.values() for v in det.values())


def test_every_case_obeys_guardrails_and_traceability(env):
    c, _, _, _ = env
    for r in c.cases.all_rows():
        case = c.cases.get(r["id"])
        ev_ids = {e["id"] for e in case["evidence"]}
        cited = {e for q in case["key_questions"]["why_suspicious"] for e in q["evidence_ids"]}
        cited |= {e for h in case["hypotheses"] for e in h["evidence_for"] + h["evidence_against"]}
        cited |= {e for s in case["score_breakdown"]["signals"] for e in s["evidence_ids"]}
        assert cited <= ev_ids
        assert len(case["key_questions"]["why_suspicious"]) >= 2
        assert case["score_breakdown"]["ml_capped_total"] <= 20
        assert all(e["source"] in ("deterministic", "model") for e in case["evidence"])
        text = json.dumps(case)
        assert banned_terms_in(text) == []
        assert "requires human investigation" in case["guardrail_notice"].lower()
        if case["tier"] == "HIGH":
            assert case["status"] == "pending_review"


def test_api_endpoints_return_real_pipeline_data(env):
    c, _, client, _ = env
    assert client.get("/api/health").json()["pipeline_run"] is True
    dash = client.get("/api/dashboard").json()
    assert dash["kpis"]["cases"] == len(c.cases.all_rows())
    caps = {x["id"]: x for x in client.get("/api/capabilities").json()}
    assert caps["new_account_large_inflow"]["enabled"] is False and caps["shared_device"]["enabled"] is True
    cases = client.get("/api/cases").json()
    cid = cases[0]["id"]
    case = client.get(f"/api/cases/{cid}").json()
    g = client.get(f"/api/cases/{cid}/graph").json()
    assert g["nodes"] and any(e["suspicious"] for e in g["edges"])
    assert client.get(f"/api/cases/{cid}/flow").json()["links"]
    det_ev = next(e for e in case["evidence"] if e["source"] == "deterministic" and e["txn_ids"])
    ev = client.get(f"/api/cases/{cid}/evidence/{det_ev['id']}").json()
    assert ev["raw_rows"] and ev["cypher_used"]
    assert client.get(f"/api/cases/{cid}/evidence/E999").status_code == 404
    assert client.get("/api/metrics").json()["computed"] is True
    assert client.get("/api/entities/search", params={"q": "M1"}).json()
    assert client.get("/api/entities/account:M1/neighbors", params={"hops": 1}).json()["nodes"]


def test_review_requires_notes_and_writes_verified_audit_chain(env):
    c, _, client, _ = env
    cid = client.get("/api/cases").json()[0]["id"]
    assert client.post(f"/api/cases/{cid}/review", json={"action": "request_more_info", "reviewer": "r", "notes": ""}).status_code == 422
    assert client.post(f"/api/cases/{cid}/review", json={"action": "freeze_account", "reviewer": "r", "notes": "x"}).status_code == 422
    r = client.post(f"/api/cases/{cid}/review", json={"action": "request_more_info", "reviewer": "analyst-1", "notes": "need KYC"})
    assert r.status_code == 200 and r.json()["case"]["status"] == "more_info_requested"
    audit = client.get(f"/api/cases/{cid}/audit").json()
    assert audit["chain_valid"] and audit["entries"][-1]["action"] == "request_more_info"
    # tampering with a stored entry breaks verification
    from sqlalchemy import update
    from trace.data_access.relational.store import audit_log
    with c.engine.begin() as conn:
        conn.execute(update(audit_log).where(audit_log.c.seq == audit["entries"][-1]["seq"]).values(payload='{"notes":"edited"}'))
    assert client.get(f"/api/cases/{cid}/audit").json()["chain_valid"] is False


def test_whatif_is_not_recorded_and_dossier_builds(env):
    c, _, client, _ = env
    cid = client.get("/api/cases").json()[0]["id"]
    before = client.get(f"/api/cases/{cid}").json()
    w = client.post(f"/api/cases/{cid}/whatif", json={"adjudications": {"device_ownership_confirmed_shared": "confirmed"}}).json()
    assert w["recorded"] is False and w["label"] == "Simulation - not recorded"
    assert client.get(f"/api/cases/{cid}").json()["priority_score"] == before["priority_score"]
    assert isinstance(client.get(f"/api/cases/{cid}/next-best-actions").json(), list)
    pdf = client.get(f"/api/cases/{cid}/dossier.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_pipeline_rerun_is_idempotent_and_keeps_review_history(env):
    c, _, client, _ = env
    ids_before = [r["id"] for r in c.cases.all_rows()]
    statuses = {r["id"]: r["status"] for r in c.cases.all_rows()}
    run(c)
    assert [r["id"] for r in c.cases.all_rows()] == ids_before
    assert {r["id"]: r["status"] for r in c.cases.all_rows()} == statuses
