# PROGRESS

| Phase | Status | Notes |
|---|---|---|
| 0 – Scaffold, profile, map | BUILT, waiting on dataset | Profiler, mapping, normalise, validate, capabilities done; needs the dataset for Checkpoint 0 |
| 1 – Domain, graph, detectors | BUILT (dataset-independent) | 13 detectors + entity resolution + sanctions match + IsolationForest; graph; thresholds derived from data |
| 2 – Case engine (Checkpoint A) | BUILT, waiting on dataset | Grouping, evidence IDs, hypotheses, alternatives, scoring, counterfactuals, next steps, exposure |
| 3 – Pipeline & API | BUILT | `make pipeline`; 19 endpoints incl. review, audit (hash chain), dossier PDF, what-if |
| 4 – Frontend (Checkpoint B) | NOT STARTED | Spec: build only against a backend serving real data |
| 5 – Agents, narrative, trust layer | NOT STARTED | llm_audit table + endpoint exist |
| 6 – What-if & next-best action | BACKEND BUILT | Pure recompute, /whatif, /adjudicate, /next-best-actions; effort minutes not yet supplied |
| 7 – Real-time replay | NOT STARTED | |
| 8 – Evaluation | PARTIAL | /api/metrics: 5 measures computable now; baselines need the dataset |
| 9 – Optional intelligence | NOT STARTED | |
| 10 – Finish | NOT STARTED | |

## Verified (without the real dataset)
- 36 tests pass (unit tests on hand-built inputs + end-to-end pipeline/API on a hand-built CSV inside tests/),
  stable under 6 different PYTHONHASHSEED values. ruff clean.
- With no mapping, every endpoint returns a real empty state; `make pipeline` exits 2 with a clear message.

## Known issues / decisions for the user
- `config/detectors.yaml`: values marked `confirm` (window sizes, percentiles, forward ratio) and two weights not in
  the spec (`fan_out` 15, `burst_velocity` 10; penalty `SHARED_BUSINESS` 10) need confirmation.
- `config/catalogues.yaml`: `whatif_facts.*.effort_minutes` are null (next-best actions rank by shift only until set);
  `alternative_params.business_type_values` empty (supplier/shared-business alternatives show "cannot evaluate").
- `prior_escalation.escalated_outcomes` empty until the dataset's alert vocabulary is known.
- Python is the shared Anaconda 3.13 env. Installing sse-starlette upgraded starlette, which required FastAPI 0.162;
  pip reported opentelemetry version conflicts in that shared env. A dedicated venv is recommended.
- The package is named `trace` (collides with stdlib `trace`); run via `make`/`scripts`/from `backend/`.
- Performance on multi-million-row data not yet measured (detectors are vectorised; cycle enumeration is capped).

## Next step
1. Receive dataset → profile → propose mapping → CHECKPOINT 0.
2. Run pipeline → cases table + score distribution (+ label report if labels exist) → CHECKPOINT A.
