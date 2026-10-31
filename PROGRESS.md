# PROGRESS

| Phase | Status | Notes |
|---|---|---|
| 0 – Scaffold, profile, map | IN PROGRESS | Structure + generic ingestion built; waiting on dataset |
| 1 – Domain, graph, detectors | NOT STARTED | |
| 2 – Case engine (Checkpoint A) | NOT STARTED | |
| 3 – Pipeline & API | NOT STARTED | |
| 4 – Frontend (Checkpoint B) | NOT STARTED | |
| 5 – Agents, narrative, trust layer | NOT STARTED | |
| 6 – What-if & next-best action | NOT STARTED | |
| 7 – Real-time replay | NOT STARTED | |
| 8 – Evaluation | NOT STARTED | |
| 9 – Optional intelligence | NOT STARTED | |
| 10 – Finish | NOT STARTED | |

## Known issues
- No dataset provided yet: `config/mapping.yaml`, `config/detectors.yaml`, `config/catalogues.yaml`
  are empty schemas; `docs/dataset_profile.md` not generated.
- Python in this environment is 3.13 (Anaconda); spec targets 3.11; no venv active yet.

## Next step
1. Receive dataset → place under `data/raw/` → `python -m trace.ingestion.profile --source <path>`
   → `docs/dataset_profile.md`.
2. Propose `config/mapping.yaml`, print capability table → CHECKPOINT 0.
