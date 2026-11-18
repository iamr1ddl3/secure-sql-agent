"""Public "try it yourself" playground: one page over the real QueryService.

Security notes:
  * Visitors never hold a token. The server mints one for a demo identity, and only for the 7 in DEMO_USERS
    (the pydantic Literal rejects anything else before any network call).
  * Live questions go through the same QueryService.handle as POST /v1/query; nothing is forked.
  * The "bypass the AI" panel runs only the fixed statements in RAW_STATEMENTS, chosen by id. Visitors can't send SQL.
  * Live calls are rate limited per IP; the hard cost cap is the OpenRouter key's monthly limit.
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .contracts import QueryRequest, QueryResponse

HERE = Path(__file__).parent / "playground_static"

DEMO_USERS = ("teller.surat", "teller.mumbai", "manager.surat", "manager.mumbai", "hr.officer", "auditor", "intern")
DemoUser = Literal["teller.surat", "teller.mumbai", "manager.surat", "manager.mumbai", "hr.officer", "auditor", "intern"]

# Fixed, reviewed statements. They skip the LLM and the SQL validator on purpose: the point is that Postgres
# alone still refuses. Never add a statement built from visitor input.
RAW_STATEMENTS = {
    "salaries": "select employee_id, effective_from, annual_ctc from bank.salaries order by annual_ctc desc limit 5",
    "national_ids": "select full_name, national_id from bank.customers order by customer_id limit 5",
    "txns_by_branch": "select branch_id, count(*) as txns from bank.transactions group by branch_id order by branch_id",
}
RawId = Literal["salaries", "national_ids", "txns_by_branch"]

MAX_QUESTION = 300


# --- tokens ------------------------------------------------------------------------------------------------------

_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()


def mint_token(user: str, *, supabase_url: str, publishable_key: str, password: str) -> str:
    """Supabase access token for one of the 7 demo users (password grant, cached until ~1 min before expiry)."""
    if user not in DEMO_USERS:
        raise ValueError(f"not a demo user: {user!r}")
    with _tokens_lock:
        hit = _tokens.get(user)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
    r = httpx.post(f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password", headers={"apikey": publishable_key},
                   json={"email": f"{user}@bank.example", "password": password}, timeout=20)
    r.raise_for_status()
    tok = r.json()["access_token"]
    exp = jwt.decode(tok, options={"verify_signature": False}).get("exp", 0)  # only for the cache; the service verifies
    with _tokens_lock:
        _tokens[user] = (tok, float(exp))
    return tok


def _token_for(user: str) -> str:
    from .config import get_settings

    s = get_settings()
    if not (s.supabase_publishable_key and s.demo_user_password):
        raise HTTPException(503, "playground not configured (SUPABASE_PUBLISHABLE_KEY / DEMO_USER_PASSWORD)")
    return mint_token(user, supabase_url=s.supabase_url, publishable_key=s.supabase_publishable_key,
                      password=s.demo_user_password)


# --- rate limit --------------------------------------------------------------------------------------------------

class RateLimiter:
    """Sliding windows per key: at most `per_min` hits in 60 s and `per_day` in 24 h."""
    # ponytail: in-process memory, single worker; one deque (<= per_day entries) per IP seen today. Move to Redis
    # if this ever runs with several workers or replicas.

    def __init__(self, per_min: int = 10, per_day: int = 100, clock=time.monotonic):
        self.per_min, self.per_day, self.clock = per_min, per_day, clock
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= 86400:
                q.popleft()
            if len(q) >= self.per_day or sum(1 for t in q if now - t < 60) >= self.per_min:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # The rightmost X-Forwarded-For entry is the one our proxy (HF Spaces) added; entries to its left are
    # client-supplied and spoofable.
    xff = request.headers.get("x-forwarded-for")
    return xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "unknown")


def _limit(request: Request) -> None:
    if not limiter.allow(client_ip(request)):
        raise HTTPException(429, "Rate limit: 10 live calls per minute, 100 per day. Replay mode has no limit.")


# --- routes ------------------------------------------------------------------------------------------------------

router = APIRouter(prefix="/playground")


def _service():
    from .api import _service  # lazy: api.py imports this module

    return _service()


@router.get("", response_class=HTMLResponse)
def page() -> str:
    return (HERE / "index.html").read_text()


@router.get("/replays")
def replays() -> dict:
    return json.loads((HERE / "replays.json").read_text())


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_user: DemoUser
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


@router.post("/ask", response_model=QueryResponse)
def ask(body: Ask, request: Request) -> QueryResponse:
    svc = _service()
    if svc.pipeline is None:
        raise HTTPException(503, "Live mode is off on this deployment (no model key). Use replay mode.")
    _limit(request)
    return svc.handle(QueryRequest(question=body.question, identity=_token_for(body.as_user), max_rows=50))


class Raw(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_user: DemoUser
    statement_id: RawId


def run_raw(user: str, statement_id: str) -> dict:
    """Run one allow-listed statement as `user`, straight against Postgres (no LLM, no validator)."""
    import psycopg

    from . import db
    from .config import get_settings

    sql = RAW_STATEMENTS[statement_id]
    s = get_settings()
    sub = _service().verifier.verify(_token_for(user)).sub
    with psycopg.connect(s.agent_database_url) as conn:
        try:
            res = db.run_as_user(conn, sub, sql, key_id=s.identity_hmac_key_id, secret=s.identity_hmac_key.encode(),
                                 row_cap=20, statement_timeout_ms=s.statement_timeout_ms)
        except db.PermissionDenied as e:
            return {"sql": sql, "status": "denied", "error": str(e)}
    return {"sql": sql, "status": "ok", "app_role": res.app_role, "columns": [c for c, _ in res.columns],
            "rows": json.loads(json.dumps(res.rows, default=str))}


@router.post("/raw")
def raw(body: Raw, request: Request) -> dict:
    _limit(request)
    return run_raw(body.as_user, body.statement_id)
