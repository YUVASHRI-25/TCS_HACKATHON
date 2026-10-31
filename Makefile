PY ?= python
BACKEND := backend

.PHONY: install profile pipeline api frontend test lint types up

install:
	cd $(BACKEND) && $(PY) -m pip install -e ".[dev]"
	cd frontend && npm install

profile:
	cd $(BACKEND) && $(PY) -m trace.ingestion.profile --mapping ../config/mapping.yaml --out ../docs/dataset_profile.md

pipeline:
	$(PY) scripts/run_pipeline.py

api:
	cd $(BACKEND) && $(PY) -m uvicorn trace.api.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd $(BACKEND) && $(PY) -m pytest -q

lint:
	cd $(BACKEND) && $(PY) -m ruff check trace tests

types:
	bash scripts/export_types.sh

up:
	docker compose up --build
