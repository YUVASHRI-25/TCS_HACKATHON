# TRACE – Transaction Relationship Analysis & Crime Exploration

AI Financial Crime Network Investigator (Challenge 07, Theme 2: AI for Business).
Decision support only. A human investigator makes the final decision.

## NON-NEGOTIABLE RULES

1. **NO MOCK DATA, NO SIMULATOR.** No hand-written API payloads, no hardcoded cases/scores/graphs/
   narratives/metrics anywhere in backend or frontend. Every number on screen is computed from the
   real dataset by the pipeline. Empty and error states are real empty/error states. Test fixtures
   live ONLY in `backend/tests/` (small slices sampled from the real dataset, or tiny hand-built
   inputs for pure domain unit tests) and are never imported by app code.
2. **DETERMINISTIC CORE.** Detection, evidence, scoring, counterfactuals and tiers are deterministic
   Python. LLM agents may only (a) choose from fixed catalogues (typologies, alternatives, next-step
   actions) and (b) write narrative text from structured JSON. They never set or change a number and
   may cite only evidence IDs that exist. The whole system runs with `LLM_PROVIDER=none` using
   template fallbacks.
3. **GUARDRAILS.** The system never declares guilt, freezes accounts or files reports. Language is
   "requires human investigation" / "potential match requiring human review". HIGH-tier cases go to a
   human review queue. Every human action is written to a hash-chained append-only audit log. No
   submit/file/freeze buttons anywhere. Banned words in any generated text: guilty, criminal,
   fraudster, confirmed fraud, launderer.
4. **TRACEABILITY.** Every claim cites evidence IDs (E01...) that resolve to raw source rows. Shared
   device/IP/address NEVER merges people: it creates a "possible related" link with a stored confidence.
5. **NEVER FABRICATE.** Never impute, invent or fill in missing fields. Each detector declares required
   fields; if the dataset lacks them the detector is DISABLED and the UI shows "Not evaluated: <reason>".
   Derived entities are tagged `derived=true` and shown as derived. A fact the data cannot provide
   becomes a next-step action, never an assumption.
6. **ML IS CAPPED.** ML/probabilistic outputs are signals worth at most 20 points combined, appear as
   their own evidence items tagged `source="model"`, and can never open a case alone. A case needs >=2
   independent DETERMINISTIC finding types (configurable; if this yields too few cases, REPORT it, do
   not silently lower it).
7. **HONEST NUMBERS.** "Priority score", never "probability of fraud". Detector thresholds are derived
   from the dataset's own distributions (percentiles), stored in `config/detectors.yaml` with the
   derivation noted. Never tune against a label set that is also reported on. State plainly in UI and
   README what the data is and what metrics do and do not prove.
8. If a dependency install fails for >10 minutes, use the documented fallback and move on. Never leave
   the repo broken: every phase ends with passing tests and a commit.

## Working conventions

- Layered architecture, dependencies point inward to the domain (see `docs/architecture.md`).
  `backend/trace/domain` has NO framework imports (no FastAPI, SQLAlchemy, LLM SDKs, no file/DB I/O).
  Computation libraries (numpy, pandas, networkx) are allowed for vectorised detectors.
  The domain talks only to repository interfaces in `data_access/ports.py`;
  `infrastructure/container.py` injects implementations.
- Derived outlier thresholds are strict: a value must EXCEED the configured percentile of its population.
- Networks are joined only through transactions cited by findings, never by ordinary history.
- No dataset-specific column names, thresholds or values in code. Everything dataset-specific lives
  in `config/*.yaml`; thresholds are produced by the pipeline from the data's own distributions.
- Frontend TS API types are GENERATED (`scripts/export_types.sh`), never hand-written; no mock client.
- Update `PROGRESS.md` (phase, status, known issues, next step) and commit after every phase.
- Checkpoints: STOP after Phase 0, Phase 2 (A) and Phase 4 (B) for user review.
