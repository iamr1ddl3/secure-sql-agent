"""The one entry point both transports call. Security lives here, not in the transports.

Stage 1 flow (see build plan): input guard -> router -> schema linking -> SQL generation
-> SQL validator -> execute as user -> output guard -> answer.
Only identity verification is wired so far; the rest lands stage by stage, each behind an eval.
"""
from __future__ import annotations

import uuid

from .contracts import ErrorInfo, PolicyHit, QueryRequest, QueryResponse
from .identity import IdentityVerifier, InvalidIdentity


def new_trace_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"


class QueryService:
    def __init__(self, verifier: IdentityVerifier, pipeline=None):
        self.verifier = verifier
        self.pipeline = pipeline  # None = stub (identity checked, nothing answered)

    def handle(self, req: QueryRequest) -> QueryResponse:
        trace_id = new_trace_id()
        try:
            ident = self.verifier.verify(req.identity)
        except InvalidIdentity as e:
            return QueryResponse(
                status="error", explanation="The identity token could not be verified.",
                policy_hits=[PolicyHit(policy_id="identity.invalid_token", stage="identity", action="block",
                                       detail=str(e)[:500])],
                error=ErrorInfo(code="invalid_identity", message=str(e)[:500]), trace_id=trace_id,
            )
        if self.pipeline is not None:
            return self.pipeline.run(req.question, ident.sub, req.max_rows, trace_id)
        return QueryResponse(
            status="error", explanation="The query pipeline is not implemented yet.",
            error=ErrorInfo(code="internal", message="pipeline not implemented"), trace_id=trace_id,
        )


def build_service() -> QueryService:
    from .config import get_settings

    s = get_settings()
    verifier = IdentityVerifier(issuer=s.jwt_issuer, jwks_url=s.jwks_url, hs256_secret=s.supabase_jwt_secret)
    return QueryService(verifier, build_pipeline() if s.openrouter_api_key else None)


def build_pipeline(conn_factory=None, owns_conn: bool = True, key_id: str | None = None, secret: bytes | None = None,
                   guards: bool = True):
    """Pipeline from settings + config/models.yaml (router = `cheap`, SQL = `default_model`). Needs OPENROUTER_API_KEY."""
    import psycopg

    from .config import get_settings
    from .llm import LLM, load_model_ids
    from .pipeline import Pipeline

    s = get_settings()
    cfg = load_model_ids(s.models_file)
    d = cfg.get("defaults", {})
    mk = lambda name: LLM(cfg["models"][name]["id"], s.openrouter_api_key, s.openrouter_base_url,  # noqa: E731
                          d.get("temperature", 0), d.get("max_tokens", 1200))
    return Pipeline(router=mk("cheap"), sql_llm=mk(s.default_model),
                    conn_factory=conn_factory or (lambda: psycopg.connect(s.agent_database_url)),
                    key_id=key_id or s.identity_hmac_key_id, secret=secret or s.identity_hmac_key.encode(), owns_conn=owns_conn, guards=guards,
                    statement_timeout_ms=s.statement_timeout_ms)
