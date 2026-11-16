"""The service must refuse anything that is not a valid end-user token, and its
responses must always satisfy the frozen contract."""
import json
import time
import uuid
from pathlib import Path

import jwt
import pytest
from jsonschema import Draft202012Validator

from secure_sql_agent.contracts import QueryRequest
from secure_sql_agent.identity import IdentityVerifier
from secure_sql_agent.service import QueryService

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "interface/query_bank_data.v1.schema.json").read_text())
RESP = Draft202012Validator({**SCHEMA, "$ref": "#/$defs/QueryResponse"})

ISS = "https://example.supabase.co/auth/v1"
SECRET = "test-secret-" + "x" * 40


def token(**over):
    claims = {"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISS, "role": "authenticated",
              "exp": int(time.time()) + 300}
    claims.update(over)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, SECRET, algorithm="HS256")


@pytest.fixture
def svc():
    return QueryService(IdentityVerifier(issuer=ISS, hs256_secret=SECRET))


@pytest.mark.parametrize("bad", [
    {"role": "service_role"}, {"role": "anon"}, {"exp": int(time.time()) - 3600},
    {"aud": "something-else"}, {"iss": "https://evil.example/auth/v1"}, {"sub": "not-a-uuid"},
])
def test_rejects_non_user_tokens(svc, bad):
    res = svc.handle(QueryRequest(question="total deposits", identity=token(**bad)))
    assert res.status == "error" and res.error.code == "invalid_identity"
    RESP.validate(res.model_dump(mode="json"))


def test_rejects_wrong_signature(svc):
    forged = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISS,
                         "exp": int(time.time()) + 60}, "another-secret-" + "y" * 40, algorithm="HS256")
    res = svc.handle(QueryRequest(question="q", identity=forged))
    assert res.error.code == "invalid_identity"


def test_rejects_alg_none(svc):
    unsigned = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISS,
                           "exp": int(time.time()) + 60}, key=None, algorithm="none")
    res = svc.handle(QueryRequest(question="q", identity=unsigned))
    assert res.error.code == "invalid_identity"


def test_valid_token_passes_identity_stage(svc):
    res = svc.handle(QueryRequest(question="q", identity=token()))
    assert not any(h.stage == "identity" for h in res.policy_hits)
    RESP.validate(res.model_dump(mode="json"))
