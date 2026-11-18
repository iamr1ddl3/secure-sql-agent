"""FastAPI transport: POST /v1/query. No security logic here; see service.py."""
from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__, playground
from .contracts import QueryRequest, QueryResponse
from .service import QueryService, build_service

app = FastAPI(title="Secure SQL Agent", version=__version__)
app.include_router(playground.router)


@lru_cache
def _service() -> QueryService:
    return build_service()


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/playground")  # a Space opens at /


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "version": __version__}


@app.post("/v1/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    return _service().handle(req)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(min_length=20)
    approve: bool


@app.post("/v1/reviews/{review_id}/decision", response_model=QueryResponse)
def decide(review_id: str, body: Decision) -> QueryResponse:
    return _service().decide_review(review_id, body.identity, body.approve)


class Collect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str = Field(min_length=20)


@app.post("/v1/reviews/{review_id}/collect", response_model=QueryResponse)
def collect(review_id: str, body: Collect) -> QueryResponse:
    return _service().collect_review(review_id, body.identity)
