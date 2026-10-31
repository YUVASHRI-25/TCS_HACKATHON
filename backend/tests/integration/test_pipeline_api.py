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
    anon = TestClient(app)
    assert anon.get("/api/auth/setup").json()["needs_setup"] is True
    assert anon.post("/api/auth/setup", json={"username": "admin", "password": "admin-pass-1"}).status_code == 200
    tok = anon.post("/api/auth/login", json={"username": "admin", "password": "admin-pass-1"}).json()["token"]
    client = TestClient(app, headers={"Authorization": f"Bearer {tok}"})
    yield c, result, client, d
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
        assert case["status"] == "open"


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


def test_status_workflow_requires_notes_and_writes_verified_audit_chain(env):
    c, _, client, _ = env
    cid = client.get("/api/cases").json()[0]["id"]
    rv = lambda body: client.post(f"/api/cases/{cid}/review", json=body)  # noqa: E731
    assert rv({"action": "start_review", "notes": ""}).status_code == 422
    assert rv({"action": "freeze_account", "notes": "x"}).status_code == 422
    assert rv({"action": "reopen", "notes": "x"}).status_code == 422          # already open
    r = rv({"action": "start_review", "notes": "taking this one"})
    assert r.status_code == 200 and r.json()["case"]["status"] == "under_review"
    assert r.json()["audit_entry"]["actor"] == "admin"                        # reviewer = signed-in user
    assert rv({"action": "escalate", "notes": "needs senior review"}).json()["case"]["status"] == "escalated"
    assert rv({"action": "resolve", "notes": "done"}).status_code == 422      # outcome required
    r = rv({"action": "resolve", "notes": "documents explain flows", "resolution": "no_further_action"})
    assert r.json()["case"]["status"] == "resolved"
    audit = client.get(f"/api/cases/{cid}/audit").json()
    assert audit["chain_valid"] and [e["action"] for e in audit["entries"]][-3:] == ["start_review", "escalate", "resolve"]
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


def test_requests_without_sign_in_are_refused(env):
    anon = TestClient(app)
    assert anon.get("/api/health").status_code == 200
    for u in ("/api/cases", "/api/dashboard", "/api/metrics", "/api/datasets", "/api/admin/users"):
        assert anon.get(u).status_code == 401
    assert anon.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    assert anon.post("/api/auth/setup", json={"username": "x", "password": "another-pass"}).status_code == 422


def test_admin_manages_users_and_roles_are_enforced(env):
    _, _, client, _ = env
    r = client.post("/api/admin/users", json={"username": "ivy", "role": "investigator", "password": "ivy-pass-12"})
    assert r.status_code == 200
    assert client.post("/api/admin/users", json={"username": "ivy", "role": "investigator", "password": "ivy-pass-12"}).status_code == 422
    tok = TestClient(app).post("/api/auth/login", json={"username": "ivy", "password": "ivy-pass-12"}).json()["token"]
    ivy = TestClient(app, headers={"Authorization": f"Bearer {tok}"})
    assert ivy.get("/api/cases").status_code == 200
    assert ivy.get("/api/admin/users").status_code == 403
    assert ivy.put("/api/admin/settings", json={}).status_code == 403
    uid = r.json()["id"]
    assert client.patch(f"/api/admin/users/{uid}", json={"active": False}).json()["active"] is False
    assert ivy.get("/api/cases").status_code == 401              # sessions dropped on deactivation
    acts = [e["action"] for e in client.get("/api/admin/activity").json()["entries"]]
    assert {"create_user", "update_user", "login"} <= set(acts)


def test_admin_settings_change_percentiles_not_values(env):
    c, _, client, d = env
    view = client.get("/api/admin/settings").json()
    assert view["detectors"]["fan_in"]["derive"]["min_counterparties"]["percentile"] == 99
    assert client.put("/api/admin/settings", json={"detectors": {"fan_in": {"derive": {"min_counterparties": {"percentile": 150}}}}}).status_code == 422
    assert client.put("/api/admin/settings", json={"weights": {"not_a_signal": 3}}).status_code == 422
    assert client.put("/api/admin/settings", json={"weights": {"fan_in": "x"}}).status_code == 422
    assert client.put("/api/admin/settings", json={"tiers": {"high": 30}}).status_code == 422   # below medium
    r = client.put("/api/admin/settings", json={"detectors": {"fan_in": {"derive": {"min_counterparties": {"percentile": 95}}}},
                                               "weights": {"fan_in": 12}}).json()
    assert len(r["changes"]) == 2
    assert client.get("/api/admin/settings").json()["weights"]["fan_in"] == 12
    assert (d / "config" / "detectors.overrides.yaml").exists()
    client.put("/api/admin/settings", json={"detectors": {"fan_in": {"derive": {"min_counterparties": {"percentile": 99}}}},
                                           "weights": {"fan_in": 15}})


def test_upload_accepts_known_format_and_rejects_unknown(env):
    c, _, client, d = env
    good = (d / "tx.csv").read_bytes()
    r = client.post("/api/datasets/upload", data={"name": "re-upload"}, files=[("files", ("tx.csv", good, "text/csv"))])
    assert r.status_code == 200 and r.json()["status"] == "ready"
    bad = b"foo,bar\n1,2\n"
    r = client.post("/api/datasets/upload", data={"name": "bad"}, files=[("files", ("other.csv", bad, "text/csv"))])
    assert r.status_code == 422 and "does not match" in r.json()["detail"]


def test_investigator_creates_case_from_chosen_accounts(env):
    c, _, client, _ = env
    r = client.post("/api/cases", json={"accounts": ["M1", "M2"], "title": "follow-up", "notes": "linked to alert"})
    assert r.status_code == 200, r.text
    case = r.json()
    assert case["id"].startswith("M-") and case["origin"] == "investigator" and case["created_by"] == "admin"
    assert {e["raw_id"] for e in case["entities"] if e["role"] == "member"} == {"M1", "M2"}
    assert client.post("/api/cases", json={"accounts": ["NOPE"], "notes": "x"}).status_code == 422
    listed = {x["id"]: x for x in client.get("/api/cases").json()}
    assert listed[case["id"]]["origin"] == "investigator"


def test_pipeline_rerun_is_idempotent_and_keeps_review_history(env):
    c, _, client, _ = env
    ids_before = sorted(r["id"] for r in c.cases.all_rows())
    statuses = {r["id"]: r["status"] for r in c.cases.all_rows()}
    run(c)
    assert sorted(r["id"] for r in c.cases.all_rows()) == ids_before   # investigator cases survive too
    assert {r["id"]: r["status"] for r in c.cases.all_rows()} == statuses
