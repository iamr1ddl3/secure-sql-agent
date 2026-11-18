"""Playground trust boundaries: only the 7 demo users get tokens, live calls are rate limited, and the
"bypass the AI" panel runs only allow-listed statements (never visitor SQL). No network or database needed."""
import time
from types import SimpleNamespace

import jwt
import pytest
import sqlglot
from fastapi.testclient import TestClient

from secure_sql_agent import playground as pg
from secure_sql_agent.api import app

SEVEN = {"teller.surat", "teller.mumbai", "manager.surat", "manager.mumbai", "hr.officer", "auditor", "intern"}


@pytest.fixture
def fake_auth(monkeypatch):
    calls = []

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"access_token": jwt.encode({"exp": int(time.time()) + 3600}, "k" * 32, algorithm="HS256")}

    def post(url, headers, json, timeout):
        calls.append(json["email"])
        return Resp()

    monkeypatch.setattr(pg.httpx, "post", post)
    monkeypatch.setattr(pg, "_tokens", {})
    return calls


def mint(user):
    return pg.mint_token(user, supabase_url="https://x.supabase.co", publishable_key="pub", password="pw")


def test_exactly_the_seven_demo_users():
    assert set(pg.DEMO_USERS) == SEVEN
    assert set(pg.DemoUser.__args__) == SEVEN


@pytest.mark.parametrize("user", ["admin", "postgres", "service_role", "teller.surat@bank.example", "TELLER.SURAT", ""])
def test_mint_refuses_non_demo_users_without_calling_auth(fake_auth, user):
    with pytest.raises(ValueError):
        mint(user)
    assert fake_auth == []


def test_mint_demo_user_and_cache(fake_auth):
    assert mint("auditor") == mint("auditor")
    assert fake_auth == ["auditor@bank.example"]  # second call served from cache


def test_endpoints_reject_unknown_user_before_minting(fake_auth):
    c = TestClient(app)
    assert c.post("/playground/ask", json={"as_user": "admin", "question": "hi"}).status_code == 422
    assert c.post("/playground/raw", json={"as_user": "root", "statement_id": "salaries"}).status_code == 422
    assert fake_auth == []


def test_rate_limit_per_minute_and_per_day():
    now = [0.0]
    rl = pg.RateLimiter(per_min=3, per_day=5, clock=lambda: now[0])
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b")  # other IPs unaffected
    now[0] = 61
    assert [rl.allow("a") for _ in range(3)] == [True, True, False]  # day cap (5) reached
    now[0] = 86400 + 1
    assert rl.allow("a")


def test_client_ip_uses_proxy_added_entry():
    r = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, client=None)
    assert pg.client_ip(r) == "1.2.3.4"  # leftmost is client-supplied (spoofable)


def test_live_endpoint_rate_limited(monkeypatch):
    class Svc:
        pipeline = object()
        def handle(self, req): raise AssertionError("must not reach the pipeline")
    monkeypatch.setattr(pg, "_service", lambda: Svc())
    monkeypatch.setattr(pg, "limiter", pg.RateLimiter(per_min=0))
    r = TestClient(app).post("/playground/ask", json={"as_user": "intern", "question": "hi"})
    assert r.status_code == 429


def test_question_length_capped():
    r = TestClient(app).post("/playground/ask", json={"as_user": "intern", "question": "x" * (pg.MAX_QUESTION + 1)})
    assert r.status_code == 422


@pytest.mark.parametrize("body", [
    {"as_user": "intern", "statement_id": "select * from bank.salaries"},
    {"as_user": "intern", "statement_id": "salaries", "sql": "select 1"},
    {"as_user": "intern", "sql": "select * from bank.salaries"},
])
def test_raw_rejects_free_form_sql(body):
    assert TestClient(app).post("/playground/raw", json=body).status_code == 422


def test_raw_allow_list_is_single_read_only_selects():
    assert set(pg.RawId.__args__) == set(pg.RAW_STATEMENTS)
    for sql in pg.RAW_STATEMENTS.values():
        stmts = sqlglot.parse(sql, read="postgres")
        assert len(stmts) == 1 and isinstance(stmts[0], sqlglot.exp.Select), sql


def test_page_and_replays_served():
    c = TestClient(app)
    assert "try to break it" in c.get("/playground").text
    rp = c.get("/playground/replays").json()
    assert rp["questions"] and set(rp["raw"]) == set(pg.RAW_STATEMENTS)
    for q in rp["questions"]:
        assert set(rp["answers"][q]) == SEVEN
