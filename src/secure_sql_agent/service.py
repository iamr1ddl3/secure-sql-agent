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


    def decide_review(self, review_id: str, identity: str, approve: bool) -> QueryResponse:
        """A second, verified staff user (approver role, not the requester) approves or rejects a held result."""
        from . import db
        from .review import APPROVER_ROLES

        trace_id = new_trace_id()

        def err(code, msg, status="error"):
            return QueryResponse(status=status, explanation=msg, error=ErrorInfo(code=code, message=msg), trace_id=trace_id)

        if self.pipeline is None or self.pipeline.reviews is None:
            return err("internal", "no review queue configured")
        try:
            ident = self.verifier.verify(identity)
        except InvalidIdentity as e:
            return err("invalid_identity", str(e)[:500])
        rv = self.pipeline.reviews.get(review_id)
        if rv is None or rv["status"] != "pending":
            return err("invalid_request", "unknown or already decided review")
        conn = self.pipeline.conn_factory()
        try:
            role = db.role_of(conn, ident.sub, key_id=self.pipeline.key_id, secret=self.pipeline.secret)
        except db.NotStaffError:
            return err("invalid_identity", "not an active staff user")
        finally:
            if self.pipeline.owns_conn:
                conn.close()
        if role not in APPROVER_ROLES or str(ident.sub) == rv["requester"]:
            return QueryResponse(status="refused", explanation="Only a different manager or auditor can decide this review.",
                                 policy_hits=[PolicyHit(policy_id="review.not_authorised", stage="identity", action="block")], trace_id=trace_id)
        if not self.pipeline.reviews.decide(review_id, ident.sub, approve):
            return err("invalid_request", "unknown or already decided review")
        if not approve:
            return QueryResponse(status="refused", explanation="A reviewer rejected this request.", trace_id=trace_id,
                                 policy_hits=[PolicyHit(policy_id="review.rejected", stage="output_guard", action="block", detail=review_id)])
        return QueryResponse(status="answered", explanation="Approved. The requester can now collect the result; you do not receive the data.",
                             trace_id=trace_id, policy_hits=[PolicyHit(policy_id="review.approved", stage="output_guard", action="review", detail=review_id)])

    def collect_review(self, review_id: str, identity: str) -> QueryResponse:
        """The original requester collects an approved result (re-run as them, once)."""
        trace_id = new_trace_id()
        try:
            ident = self.verifier.verify(identity)
        except InvalidIdentity as e:
            return QueryResponse(status="error", explanation="The identity token could not be verified.", trace_id=trace_id,
                                 error=ErrorInfo(code="invalid_identity", message=str(e)[:500]))
        rv = self.pipeline.reviews.collect(review_id, ident.sub) if self.pipeline and self.pipeline.reviews else None
        if rv is None:
            return QueryResponse(status="error", explanation="Nothing to collect: unknown, not yours, not approved, or already collected.",
                                 error=ErrorInfo(code="invalid_request", message="nothing to collect"), trace_id=trace_id)
        return self.pipeline.run_approved(rv, trace_id)


def build_service() -> QueryService:
    from .config import get_settings

    s = get_settings()
    verifier = IdentityVerifier(issuer=s.jwt_issuer, jwks_url=s.jwks_url, hs256_secret=s.supabase_jwt_secret)
    return QueryService(verifier, build_pipeline() if s.openrouter_api_key else None)


def build_pipeline(conn_factory=None, owns_conn: bool = True, key_id: str | None = None, secret: bytes | None = None,
                   guards: bool = True, semantic: bool = False):
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
    from .review import ReviewStore

    return Pipeline(router=mk("cheap"), sql_llm=mk(s.default_model), reviews=ReviewStore(),
                    conn_factory=conn_factory or (lambda: psycopg.connect(s.agent_database_url)),
                    key_id=key_id or s.identity_hmac_key_id, secret=secret or s.identity_hmac_key.encode(), owns_conn=owns_conn, guards=guards, semantic=semantic,
                    statement_timeout_ms=s.statement_timeout_ms)
