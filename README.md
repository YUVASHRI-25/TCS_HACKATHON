# TRACE – Transaction Relationship Analysis & Crime Exploration

**An AI Financial Crime Network Investigator.** TRACE finds suspicious *networks* of customers, accounts,
merchants, devices, IP addresses and beneficiaries in real transaction data. For each one it explains why it
looks suspicious, what evidence supports it, what legitimate explanation might exist, and what an
investigator should check next.

> **Decision support only. A human investigator makes the final decision.**
> TRACE never declares guilt, freezes accounts or files reports.

Hackathon: Challenge 07, Theme 2 – AI for Business. Full brief: [`docs/challenge.md`](docs/challenge.md).

---

## Contents

1. [What TRACE is (and is not)](#1-what-trace-is-and-is-not)
2. [Current status](#2-current-status)
3. [Architecture – MVC view](#3-architecture--mvc-view)
4. [Repository layout](#4-repository-layout)
5. [Data flow](#5-data-flow)
6. [Configuration](#6-configuration)
7. [Getting started](#7-getting-started)
8. [Commands](#8-commands)
9. [Guardrails](#9-guardrails)
10. [Non-negotiable engineering rules](#10-non-negotiable-engineering-rules)
11. [Technology stack](#11-technology-stack)
12. [Testing](#12-testing)
13. [Limitations and what the metrics do and do not prove](#13-limitations-and-what-the-metrics-do-and-do-not-prove)
14. [Roadmap](#14-roadmap)
15. [Production path](#15-production-path)

---

## 1. What TRACE is (and is not)

**It is** an investigation console. For every flagged network it follows a fixed reasoning chain:

```
Network -> Pattern -> Hypothesis -> Evidence -> Alternatives -> Risk -> Human Investigation
```

and answers four questions:

| # | Question | How TRACE answers it |
|---|---|---|
| 1 | Why is it suspicious? | Deterministic detector findings (pass-through, cycles, fan-in/out, structuring, ...) |
| 2 | What evidence supports it? | Evidence items `E01, E02, ...`, each resolving to the raw source rows |
| 3 | What legitimate explanation might exist? | Alternatives catalogue (family, payroll, supplier trade, ...) with a fit score, or "cannot evaluate" when the data can't tell |
| 4 | What should an investigator examine next? | Next-step actions from a fixed, non-punitive catalogue |

**It is not** a fraud classifier. It does not output a "probability of fraud". It outputs an explainable
**priority score** (0–100) and a tier (HIGH / MEDIUM / LOW) that tell an investigator where to look first.

---

## 2. Current status

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffold, dataset profiling, mapping, validation, capability registry | **Built; waiting on the dataset** (Checkpoint 0) |
| 1 | Canonical tables, graph, entity resolution, detectors | Not started |
| 2 | Case engine: hypotheses, alternatives, scoring, counterfactuals (Checkpoint A) | Not started |
| 3 | One-command pipeline + FastAPI | Not started (only `/api/health` and `/api/capabilities` exist) |
| 4 | React analyst console (Checkpoint B) | Not started (shell shows the guardrail banner only) |
| 5 | LangGraph agents, cited narrative, verifier, pseudonymisation | Not started |
| 6 | What-if simulation and next-best action | Not started |
| 7 | Real-time replay of the dataset | Not started |
| 8 | Evaluation and success-measure scoreboard | Not started |
| 9 | Optional ML / RAG tiers | Not started |
| 10 | Final polish and fresh-clone test | Not started |

Live progress, known issues and the next step are in [`PROGRESS.md`](PROGRESS.md).

---

## 3. Architecture – MVC view

TRACE is built as a **layered architecture** where every dependency points inward toward a pure domain
core. Seen through the **Model–View–Controller** lens, the layers group like this:

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  VIEW                                                                    │
 │  L1 Presentation  frontend/  React + TypeScript analyst console          │
 │  (dashboard, case queue, graph, evidence, score, narrative, audit)       │
 └───────────────────────────────┬──────────────────────────────────────────┘
                                 │ HTTP / SSE  (TS types generated from OpenAPI)
 ┌───────────────────────────────▼──────────────────────────────────────────┐
 │  CONTROLLER                                                              │
 │  L2 API          backend/trace/api          FastAPI routers, Pydantic,   │
 │                                             SSE streaming                │
 │  L3 Application  backend/trace/application  use cases: run pipeline,     │
 │                                             review case, what-if,        │
 │                                             investigate                  │
 └───────────────────────────────┬──────────────────────────────────────────┘
                                 │
 ┌───────────────────────────────▼──────────────────────────────────────────┐
 │  MODEL                                                                   │
 │  L4 Domain        trace/domain        canonical model, findings,         │
 │                                       detectors, catalogues, scoring,    │
 │                                       counterfactuals, guardrails        │
 │                                       (pure Python, no frameworks)       │
 │  L5 Intelligence  trace/intelligence  entity resolution, graph analytics,│
 │                                       ML, agents, LLM, verifier          │
 │  L6 Data access   trace/data_access   repository ports + adapters        │
 │                                       (SQLAlchemy, NetworkX, FAISS,      │
 │                                       hash-chained audit)                │
 │  L7 Ingestion     trace/ingestion     adapters, mapping, normalise,      │
 │                                       validate, profile, capabilities    │
 └──────────────────────────────────────────────────────────────────────────┘
   L8 Infrastructure  trace/infrastructure  settings, logging, DB engine,
                                            dependency-injection container
                                            (wires Model adapters into the
                                            Controller)
```

### Model

The Model is everything that knows about data and rules. It never knows how it is displayed.

| Part | Package | Responsibility |
|---|---|---|
| Domain core | `backend/trace/domain/` | Canonical entities (`model/canonical.py`), detector field requirements (`detectors/requirements.py`), and later the detectors, catalogues, scoring, what-if math and guardrails. **No framework imports.** |
| Intelligence | `backend/trace/intelligence/` | Entity resolution (possible-same-entity links, never merges), graph analytics, capped ML signals, LLM agents restricted to catalogues and existing evidence IDs. |
| Data access | `backend/trace/data_access/` | `ports.py` defines the repository interfaces (`CanonicalStore`, `CaseRepository`, `GraphStore`, `AuditStore`). The domain depends only on these interfaces; concrete adapters live in `relational/`, `graph/`, `vector/`, `audit/`. |
| Ingestion | `backend/trace/ingestion/` | Turns any raw dataset into canonical entities using `config/mapping.yaml`, records every parse failure, and works out which detectors the data can support. |

### View

The View is the React console in `frontend/`. Its rules:

- It is built **only against the running backend**. There is no mock client and there is no fixture data.
- API types in `frontend/src/api/` are **generated** from the backend's `/openapi.json`
  (`scripts/export_types.sh`), never hand-written.
- Every number on screen comes from the pipeline. Empty and error states are real.
- A permanent banner reads: *"Decision support only. A human investigator makes the final decision."*
- There are no submit, file or freeze buttons anywhere.

Planned component groups: `layout`, `graph` (Cytoscape network), `evidence`, `hypotheses`, `score`
(waterfall + counterfactuals), `narrative` (citation chips), `whatif`, `agent` (live agent trace), `review`, `ui`.

### Controller

The Controller takes requests from the View, calls the right use case, and returns Pydantic-validated
responses.

| Part | Package | Responsibility |
|---|---|---|
| API routers | `backend/trace/api/` | HTTP endpoints, request/response schemas, SSE streams. Thin: no business logic. |
| Use cases | `backend/trace/application/` | Orchestration, e.g. `run_pipeline.py`: ingest → validate → resolve → graph → detect → cases → persist. |

The **dependency-injection container** (`backend/trace/infrastructure/container.py`) binds the Model's
repository ports to concrete adapters, so the Controller never constructs storage directly and the
domain can be tested without a database.

### Why layered-MVC rather than classic MVC

Classic MVC often lets the Model talk directly to a database or framework. TRACE's Model is split so
that the **domain core is pure Python**: detection, scoring and tiers are deterministic and unit-testable
on tiny hand-built inputs, and storage can change (SQLite → Postgres, NetworkX → Neo4j) without touching
any rule.

---

## 4. Repository layout

```
TRACE/
├── CLAUDE.md                  Project rules (non-negotiable) and working conventions
├── PROGRESS.md                Phase status, known issues, next step
├── README.md                  This file
├── Makefile                   install | profile | pipeline | api | frontend | test | lint | types | up
├── docker-compose.yml         Optional: neo4j, postgres, backend, frontend
├── .env.example               Runtime settings template
├── config/
│   ├── mapping.yaml           Dataset columns -> canonical model (direct | derived | absent)
│   ├── detectors.yaml         Thresholds (with derivation), weights, penalties, tiers
│   └── catalogues.yaml        Typologies, alternatives, next steps, what-if facts
├── docs/
│   ├── challenge.md           Hackathon brief
│   ├── architecture.md        Layer diagram and contracts
│   └── dataset_profile.md     Generated by the profiler
├── data/
│   ├── raw/                   Source dataset (gitignored)
│   └── processed/             Pipeline outputs (gitignored)
├── scripts/
│   ├── run_pipeline.py        Entry point for `make pipeline`
│   ├── replay_stream.py       Real-time replay (Phase 7)
│   └── export_types.sh        Generate TS types from /openapi.json
├── backend/
│   ├── pyproject.toml
│   ├── trace/
│   │   ├── api/               CONTROLLER  main.py, routers/, schemas/
│   │   ├── application/       CONTROLLER  use cases (run_pipeline.py)
│   │   ├── domain/            MODEL       model/, detectors/, catalogues/, scoring/, whatif/, guardrails/
│   │   ├── intelligence/      MODEL       resolution/, graph_analytics/, ml/, agents/, llm/, rag/
│   │   ├── data_access/       MODEL       ports.py, relational/, graph/, vector/, audit/
│   │   ├── ingestion/         MODEL       adapters/, mapping.py, normalise.py, validate.py, profile.py, capabilities.py
│   │   ├── infrastructure/    WIRING      settings.py, logging.py, container.py
│   │   └── eval/              Success-measure evaluation (Phase 8)
│   └── tests/                 domain/, ingestion/, integration/  (fixtures live only here)
└── frontend/                  VIEW
    ├── package.json, vite.config.ts, tailwind.config.ts, tsconfig.json
    └── src/
        ├── api/               GENERATED types only
        ├── store/ hooks/ pages/ lib/ styles/
        └── components/        layout, graph, evidence, hypotheses, score, narrative, whatif, agent, review, ui
```

---

## 5. Data flow

```
 source files (csv | parquet | sql)
        │  ingestion/adapters        raw rows, untouched, each tagged with _source_row
        ▼
 config/mapping.yaml -> ingestion/mapping.py     canonical frames; derived data tagged derived=true
        ▼
 ingestion/normalise.py      UTC timestamps (timezone must be declared), numbers, booleans, currency codes;
        │                    every unparseable value is recorded, never zeroed
        ▼
 ingestion/validate.py       keys, duplicates, required fields, FK integrity, time ordering
        │                    -> validation_report.json + quarantine_<Entity>.csv (reason per row)
        ▼
 ingestion/capabilities.py   each detector ENABLED / DISABLED("Not evaluated: <reason>")
        ▼
 resolution -> graph -> detectors -> case engine -> repositories -> API -> console   (Phases 1–4)
```

Every node, edge, finding and evidence item keeps a reference back to its raw source record, so any
claim on screen can be traced to the rows it came from.

---

## 6. Configuration

All dataset-specific knowledge lives in `config/`, never in code. The files are **empty templates** until
the dataset is profiled.

### `config/mapping.yaml`

Maps dataset columns onto the canonical model (Customer, Account, Transaction, Merchant, Device, IP,
Location, Beneficiary, Complaint, Alert, WatchlistEntry). Every field is one of:

| Status | Meaning |
|---|---|
| `direct` | Copied from a source column |
| `derived` | Built by a named, documented derivation (`concat_columns`, `row_number`, `same_as`) or from distinct values of other fields (`derived_from`). Always tagged as derived. |
| `absent` | Not in the data. Never imputed. Detectors needing it are disabled. |

Naive timestamps require `source.timezone`; TRACE refuses to guess one.

### `config/detectors.yaml`

Detector thresholds, each stored with **how it was derived from the dataset's own distribution**
(e.g. a percentile of a named column), plus signal weights, alternative penalties, the ML cap, the
minimum number of independent deterministic finding types per case, and tier cut-offs.

### `config/catalogues.yaml`

The fixed lists the engine and LLM agents may choose from: typologies, alternative explanations,
next-step actions, and what-if facts with effort estimates (labelled as assumptions).

### `.env`

Copy `.env.example` to `.env`. Key settings:

| Variable | Default | Options |
|---|---|---|
| `DATABASE_URL` | SQLite in `data/processed/` | any SQLAlchemy URL (Postgres optional) |
| `GRAPH_BACKEND` | `networkx` | `networkx`, `neo4j` |
| `LLM_PROVIDER` | `none` | `none`, `gemini`, `anthropic`, `openai` |
| `GNN_BACKEND` | `node2vec` | `node2vec`, `pyg` |

With the defaults TRACE needs **zero external services**.

---

## 7. Getting started

Prerequisites: Python 3.11+, Node 20+, `make` (on Windows use Git Bash, or run the commands from the
Makefile directly).

```bash
# 1. Install
cp .env.example .env
make install                    # pip install -e backend[dev] + npm install

# 2. Put the dataset in data/raw/ and profile it
cd backend
python -m trace.ingestion.profile --source ../data/raw/<file-or-folder> --out ../docs/dataset_profile.md
# optional flow hints until the mapping exists:
#   --table <t> --src-col <c> --dst-col <c> --amount-col <c> --ts-col <c>

# 3. Fill config/mapping.yaml from the profile, then
cd ..
make pipeline                   # writes data/processed/*.parquet, validation_report.json, capabilities.json

# 4. Run
make api                        # http://127.0.0.1:8000/docs
make frontend                   # http://127.0.0.1:5173
```

> **Note on the package name.** The backend package is called `trace`, which is also the name of a
> Python standard-library module. Run backend commands from inside `backend/` or through `make` /
> `scripts/`, which put `backend/` first on the import path.

---

## 8. Commands

| Command | What it does |
|---|---|
| `make install` | Install backend (editable, with dev extras) and frontend dependencies |
| `make profile` | Profile the dataset declared in `config/mapping.yaml` → `docs/dataset_profile.md` |
| `make pipeline` | Run the full pipeline; exits with a clear message if the mapping is not configured |
| `make api` | Start FastAPI with reload on port 8000 |
| `make frontend` | Start the Vite dev server on port 5173 |
| `make test` | Run the backend test suite |
| `make lint` | Run ruff on backend code and tests |
| `make types` | Regenerate frontend TS types from the running API |
| `make up` | Start the optional Docker stack |

API endpoints available now:

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Status, whether the mapping is configured, LLM provider, graph backend |
| `GET /api/capabilities` | Every detector/resolver/model with ENABLED/DISABLED and the reason |

The full endpoint list (cases, graph, evidence, review, audit, dossier, what-if, investigate, stream,
metrics) arrives in Phases 3–8.

---

## 9. Guardrails

- **No autonomous decisions.** Language is always "requires human investigation" or "potential match
  requiring human review".
- **Human review queue.** HIGH-tier cases go to a queue; reviewers can confirm for investigation, reject
  as a false positive, or request more information, always with notes.
- **Tamper-evident audit.** Every human action is appended to a hash-chained log
  (`hash = sha256(prev_hash + payload)`), and the chain is re-verified when read.
- **Banned words** in all generated text: *guilty, criminal, fraudster, confirmed fraud, launderer*.
- **No submit/file/freeze actions** anywhere. Any regulatory-style report is a watermarked DRAFT with no
  submission integration.
- **Privacy.** Before any LLM call, names, phones, emails, addresses and account numbers are replaced
  with stable tokens; every outbound prompt is stored for inspection.

---

## 10. Non-negotiable engineering rules

Full text in [`CLAUDE.md`](CLAUDE.md). In short:

1. **No mock data, no simulator.** Every number comes from the real dataset.
2. **Deterministic core.** Detection, evidence, scoring and tiers are plain Python. LLMs only pick from
   catalogues and write narrative; they never set a number. Everything runs with `LLM_PROVIDER=none`.
3. **Guardrails** as above.
4. **Traceability.** Every claim cites evidence IDs that resolve to raw rows. Shared device/IP/address
   creates a "possible related" link, never a merge.
5. **Never fabricate.** Missing fields disable detectors; missing facts become next-step actions.
6. **ML is capped** at 20 points combined, is tagged `source="model"`, and can never open a case alone.
7. **Honest numbers.** Priority score, not probability. Thresholds come from data percentiles; no
   tuning on labels that are also reported.
8. **Never leave the repo broken.** Every phase ends with passing tests and a commit.

---

## 11. Technology stack

| Area | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (SQLite / Postgres) |
| Data | pandas, pyarrow |
| Graph | NetworkX + python-louvain (optional Neo4j for persistence) |
| Resolution | rapidfuzz (+ sentence embeddings if names exist) |
| ML | scikit-learn IsolationForest; optional LightGBM + SHAP (only if labels exist), GraphSAGE / Node2Vec |
| Agents | LangGraph, pluggable LLM (Gemini / Anthropic / OpenAI / none), strict JSON-schema outputs |
| Reports | reportlab (dossier PDF) |
| Frontend | React 18, TypeScript (strict), Vite, Tailwind, shadcn/ui, TanStack Query, Zustand |
| Visuals | Cytoscape.js (fcose), Recharts (+ Sankey) |
| Quality | pytest, ruff, eslint |

---

## 12. Testing

```bash
make test        # or: cd backend && python -m pytest -q
```

Current suite (`backend/tests/ingestion/`) uses tiny hand-built inputs and covers: mapping validation,
derived-entity tagging and source references, refusal of naive timestamps without a declared timezone,
parse-failure recording, quarantine with a reason per row, capability enable/disable reasons, candidate
key and label detection, degree statistics, and threshold-clustering detection.

Fixtures live only under `backend/tests/` and are never imported by application code.

---

## 13. Limitations and what the metrics do and do not prove

- TRACE's output is only as good as the dataset. Detectors the data cannot support are switched off and
  shown as "Not evaluated", not approximated.
- A priority score ranks where to look first. **It is not a probability of fraud** and is not evidence of
  wrongdoing.
- If the dataset contains labels, they are used only to **report** how many labelled accounts fall
  inside surfaced networks. They are never used to tune thresholds.
- Analyst-time savings (Phase 8) are computed from configurable assumptions and are labelled
  "Assumptions, not measurements".

This section will be expanded with dataset-specific facts once the dataset is profiled.

---

## 14. Roadmap

See [§2 Current status](#2-current-status) for phase order. If time runs short the priority is:
Phases 0–4 (complete working product) > 5 > 6 > 8 > 7 > 9 > 10.

---

## 15. Production path

- **Graph:** move persistence to Neo4j (`GRAPH_BACKEND=neo4j`); each detector keeps its Cypher text.
- **Storage:** Postgres via `DATABASE_URL`.
- **Streaming:** the Phase 7 replay adapter uses the same code path as a live stream adapter.
- **Case management:** integrate through the review/audit API; TRACE never submits anything itself.
