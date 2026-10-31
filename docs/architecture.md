# TRACE architecture

Layered; dependencies point inward toward the domain. The domain (L4) has no framework imports and
talks to storage only through the ports in `data_access/ports.py`; `infrastructure/container.py`
injects the concrete adapters.

| Layer | Package | Responsibility |
|---|---|---|
| L1 Presentation | `frontend/` | React analyst console, built only against the running API, generated TS types |
| L2 API | `backend/trace/api` | FastAPI routers, Pydantic schemas, SSE |
| L3 Application | `backend/trace/application` | Use cases: run pipeline, review case, what-if, investigate |
| L4 Domain | `backend/trace/domain` | Canonical model, findings, detectors, catalogues, scoring, counterfactuals, what-if math, guardrails |
| L5 Intelligence | `backend/trace/intelligence` | Entity resolution, graph analytics, ML, LangGraph agents, LLM provider, pseudonymiser, verifier, RAG |
| L6 Data access | `backend/trace/data_access` | Repository ports + adapters: SQLAlchemy, NetworkX (opt. Neo4j), FAISS, hash-chained audit |
| L7 Ingestion | `backend/trace/ingestion` | Source adapters, mapping config, normalise, validate, profile, capability registry |
| L8 Infrastructure | `backend/trace/infrastructure` | Settings, logging, DB engine, DI container |

```
            +-----------------------------+
            |  L1 frontend (React/Vite)   |
            +--------------+--------------+
                           | HTTP / SSE (OpenAPI-generated types)
            +--------------v--------------+
            |  L2 api (FastAPI)           |
            +--------------+--------------+
            |  L3 application (use cases) |
            +---+---------------------+---+
                |                     |
   +------------v-----+     +---------v-----------+
   | L5 intelligence  |---->|  L4 domain (pure)   |<---- L7 ingestion (adapters -> canonical model)
   +------------+-----+     +---------^-----------+
                |                     | ports.py
            +---v---------------------+---+
            |  L6 data_access adapters    |
            +-----------------------------+
            |  L8 infrastructure (DI)     |
            +-----------------------------+
```

## Repo layout

```
trace/
  CLAUDE.md PROGRESS.md README.md Makefile docker-compose.yml .env.example
  config/{mapping.yaml, detectors.yaml, catalogues.yaml}
  docs/{challenge.md, architecture.md, dataset_profile.md}
  data/{raw/, processed/}   (gitignored except .gitkeep)
  scripts/{run_pipeline.py, replay_stream.py, export_types.sh}
  backend/pyproject.toml
  backend/trace/{api/{main.py,routers/,schemas/}, application/, domain/{model,detectors,catalogues,scoring,whatif,guardrails},
                 intelligence/{resolution,graph_analytics,ml,agents,llm,rag}, data_access/{ports.py,relational,graph,vector,audit},
                 ingestion/{adapters,mapping.py,normalise.py,validate.py,profile.py,capabilities.py}, infrastructure/, eval/}
  backend/tests/{domain,ingestion,integration}
  frontend/{package.json,vite.config.ts,tailwind.config.ts,src/{api(GENERATED),store,hooks,pages,
            components/{layout,graph,evidence,hypotheses,score,narrative,whatif,agent,review,ui},lib,styles}}
```

## Data flow

`source files -> adapter (csv|parquet|sql) -> mapping.yaml -> canonical frames -> normalise -> validate
(report + quarantine, never silent drops) -> capability registry (ENABLED/DISABLED per detector)
-> resolution -> graph -> detectors -> case engine -> repositories -> API -> UI`

## Configuration contract

- `config/mapping.yaml` – how dataset columns map onto the canonical model; every field is
  `direct | derived | absent`. Written after profiling the dataset (Checkpoint 0).
- `config/detectors.yaml` – thresholds (each with its percentile derivation), weights, tiers. Thresholds
  are written by the pipeline from the data's own distributions.
- `config/catalogues.yaml` – typologies, alternatives, next-step actions, what-if facts, effort table.
