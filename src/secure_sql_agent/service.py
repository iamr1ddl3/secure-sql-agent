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
    def __init__(self, verifier: IdentityVerifier):
        self.verifier = verifier

    def handle(self, req: QueryRequest) -> QueryResponse:
        trace_id = new_trace_id()
        try:
            self.verifier.verify(req.identity)
        except InvalidIdentity as e:
            return QueryResponse(
                status="error", explanation="The identity token could not be verified.",
                policy_hits=[PolicyHit(policy_id="identity.invalid_token", stage="identity", action="block",
                                       detail=str(e)[:500])],
                error=ErrorInfo(code="invalid_identity", message=str(e)[:500]), trace_id=trace_id,
            )
        # TODO(stage 1): input guard, router, schema linking, generation, validator, db.run_as_user, output guard
        return QueryResponse(
            status="error", explanation="The query pipeline is not implemented yet.",
            error=ErrorInfo(code="internal", message="pipeline not implemented"), trace_id=trace_id,
        )


def build_service() -> QueryService:
    from .config import get_settings

    s = get_settings()
    verifier = IdentityVerifier(issuer=s.jwt_issuer, jwks_url=s.jwks_url, hs256_secret=s.supabase_jwt_secret)
    return QueryService(verifier)
