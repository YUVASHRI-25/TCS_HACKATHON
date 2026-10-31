"""Runtime settings from environment / .env. No dataset-specific values live here."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    trace_mapping_path: Path = Path("config/mapping.yaml")
    trace_detectors_path: Path = Path("config/detectors.yaml")
    trace_catalogues_path: Path = Path("config/catalogues.yaml")
    trace_processed_dir: Path = Path("data/processed")

    database_url: str = f"sqlite:///{(REPO_ROOT / 'data/processed/trace.db').as_posix()}"
    graph_backend: Literal["networkx", "neo4j"] = "networkx"
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    llm_provider: Literal["none", "gemini", "anthropic", "openai"] = "none"
    llm_model: str | None = None

    gnn_backend: Literal["pyg", "node2vec"] = "node2vec"

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite(cls, v: str) -> str:
        """Relative SQLite paths resolve against the repo root, not the process cwd."""
        prefix = "sqlite:///"
        if v.startswith(prefix):
            p = Path(v[len(prefix):])
            if not p.is_absolute():
                return prefix + (REPO_ROOT / p).as_posix()
        return v

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else REPO_ROOT / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
