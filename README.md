# TRACE – Transaction Relationship Analysis & Crime Exploration

AI Financial Crime Network Investigator. **Decision support only. A human investigator makes the final decision.**

Status: scaffold (Phase 0). See `PROGRESS.md`. Full README is written in Phase 10.

```
make install     # backend (editable) + frontend deps
make profile     # profile the dataset declared in config/mapping.yaml -> docs/dataset_profile.md
make pipeline    # ingest -> validate -> resolve -> graph -> detect -> cases -> persist
make api         # FastAPI on :8000 (Swagger at /docs)
make frontend    # Vite dev server on :5173
make test
```
