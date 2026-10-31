"""FastAPI app. Decision support only: there are no submit, file or freeze endpoints."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trace.api.routers import cases, system
from trace.infrastructure.container import get_container

log = logging.getLogger(__name__)


def _warm() -> None:
    """Build the in-memory graph once at startup so the first investigator request is not slow."""
    try:
        c = get_container()
        if c.cases.latest_run() is not None:
            _ = c.graph
    except Exception:  # noqa: BLE001 - warming is best-effort; requests build it on demand anyway
        log.exception("graph warm-up failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm, daemon=True).start()
    yield


app = FastAPI(title="TRACE API", version="0.1.0", lifespan=lifespan,
              description="Decision support only. A human investigator makes the final decision.")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(system.router)
app.include_router(cases.router)
