"""Pydantic mirror of interface/query_bank_data.v1.schema.json.

The JSON Schema is the source of truth (Project 2 tests against it).
tests/contract/ checks that these models and the schema agree.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1"

Status = Literal["answered", "refused", "needs_review", "needs_clarification", "error"]
Stage = Literal["identity", "input_guard", "router", "validator", "database", "output_guard"]
Action = Literal["block", "mask", "flag", "review", "cap"]
ErrorCode = Literal[
    "invalid_identity", "invalid_request", "generation_failed", "db_timeout", "db_error", "internal"
]


class DelegationHop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str = Field(max_length=128)
    agent_version: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, max_length=128)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    identity: str = Field(min_length=20)
    # Informational only. Never used for authorization.
    on_behalf_of_chain: list[DelegationHop] | None = Field(default=None, max_length=8)
    max_rows: int = Field(default=100, ge=1, le=1000)


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str
    masked: bool


class Confidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    router: float | None = Field(default=None, ge=0, le=1)
    validator: float | None = Field(default=None, ge=0, le=1)


class PolicyHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str
    stage: Stage
    action: Action
    detail: str | None = Field(default=None, max_length=500)


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ErrorCode
    message: str = Field(max_length=500)


class QueryResponse(BaseModel):
    # Clients must tolerate extra fields (additive changes are non-breaking).
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1"] = SCHEMA_VERSION
    status: Status
    columns: list[Column] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False
    sql: str | None = None
    explanation: str = Field(max_length=500)
    confidence: Confidence = Field(default_factory=Confidence)
    policy_hits: list[PolicyHit] = Field(default_factory=list)
    review_id: str | None = None
    error: ErrorInfo | None = None
    trace_id: str = Field(min_length=1)
