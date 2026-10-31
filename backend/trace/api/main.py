"""FastAPI app. Decision support only: there are no submit, file or freeze endpoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trace.api.routers import cases, system

app = FastAPI(title="TRACE API", version="0.1.0",
              description="Decision support only. A human investigator makes the final decision.")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(system.router)
app.include_router(cases.router)
