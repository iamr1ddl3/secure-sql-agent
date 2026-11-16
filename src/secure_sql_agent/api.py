"""FastAPI transport: POST /v1/query. No security logic here; see service.py."""
from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI

from . import __version__
from .contracts import QueryRequest, QueryResponse
from .service import QueryService, build_service

app = FastAPI(title="Secure SQL Agent", version=__version__)


@lru_cache
def _service() -> QueryService:
    return build_service()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "version": __version__}


@app.post("/v1/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    return _service().handle(req)
