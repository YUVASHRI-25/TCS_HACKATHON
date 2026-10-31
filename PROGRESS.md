# PROGRESS

| Phase | Status | Notes |
|---|---|---|
| 0 – Scaffold, profile, map | DONE | SIFTLINE profiled (`docs/dataset_profile.md`), `config/mapping.yaml` written; 14 capabilities enabled, 2 disabled with reasons |
| 1 – Domain, graph, detectors | DONE | 13 detectors + screening + IsolationForest; currency-aware; temporal cycle search |
| 2 – Case engine (Checkpoint A) | DONE, results reviewed | 21 cases (HIGH 10 / MEDIUM 4 / LOW 7); label report at chance level (see below) |
| 3 – Pipeline & API | DONE | `make pipeline` ≈ 4 s on SIFTLINE; 19 endpoints |
| 4 – Frontend (Checkpoint B) | DONE — awaiting review | Types generated from /openapi.json; tsc strict + eslint clean; browser QA: 0 console errors, all tabs render |
| 5 – Agents, narrative, trust layer | NOT STARTED | Template narrative with citations in the UI; llm_audit table exists |
| 6 – What-if & next-best action | DONE (backend + UI) | effort minutes still unset |
| 7 – Real-time replay | NOT STARTED | UI shows a real "not available" state |
| 8 – Evaluation | PARTIAL | Success measures + member-level label report; baselines not built |
| 9 – Optional intelligence | NOT STARTED | |
| 10 – Finish | NOT STARTED | |

## Dataset facts (SIFTLINE v1.0, synthetic)
- 25,000 transactions among 800 accounts / 500 customers, 2024-01-01 → 2025-09-16, 5 currencies; every account
  sends in all 5 currencies, so amounts are only compared within a currency (no FX rates in the data).
- Dense, near-uniform transfer graph (24.5k distinct pairs; 19–52 counterparties per account); categorical
  fields are near-uniform (e.g. statuses ~1/3 each). Behaviour looks randomly generated.
- `suspicious_ring_members` (120 rows) is mapped to `LabelledMember` and used for reporting only.
- Label report: member precision 0.137 vs base rate 0.149 (lift 0.92); 82% of networks contain a labelled member
  vs 74% expected by chance. TRACE's surfaced networks are NOT enriched for the labelled ring members on this data.
  Reported as measured; nothing was tuned toward the labels.

## Decisions taken that need confirmation
- Timezone declared UTC (dataset undocumented) — display only.
- Transactions of every status (COMPLETED / PENDING / REVERSED) are analysed; REVERSED could be excluded.
- Device sharing reads `shared_devices` only (logins put 4–27 customers on every device); IP sharing reads logins.
- Vocabulary: escalated = `ESCALATED`; exact screening = `EXACT`; business = `BUSINESS`; family = `FAMILY`;
  business relationships = `EMPLOYEE`, `BUSINESS_ASSOCIATE`; office network = `CORPORATE`.
- Percentiles/params marked `confirm` in `config/detectors.yaml`; weights fan_out 15, burst 10, SHARED_BUSINESS 10 not in spec.
- Entity resolution: names are unique synthetic strings and phones/emails are unique, so it finds nothing (correct).

## Known issues
- Python env is the shared Anaconda 3.13 (FastAPI upgraded to 0.162 there; opentelemetry conflicts reported by pip).
- Graph minimap not implemented (fit-to-view control instead).
- Frontend bundle is 1.3 MB (one chunk); code-splitting not done.
- A relative DATABASE_URL in .env used to resolve against the process cwd; now anchored to the repo root.
- Package name `trace` collides with stdlib; run via `make` / `scripts` / from `backend/`.

## Next step
CHECKPOINT B review. Then Phase 5 (agents + cited narrative + verifier + pseudonymisation).

## Final-review pass
- Real LLM copilot (`POST /api/cases/{id}/copilot`): structured context, Pydantic-validated JSON, citations checked against
  case IDs, banned-word guardrail, explicit 503 when the LLM is unavailable, every call in `llm_audit` + audit chain.
- Admin: `/api/admin/system-health` (DB round-trip, graph, live LLM ping, failure counters), `/api/admin/cases`; UI page "System health".
- White enterprise theme; uploads that are rejected now return 422.
- Not done: dedicated versioned "revised narrative" store (previous versions live in the hash-chained audit log; original score is never overwritten).
