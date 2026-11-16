"""Fixtures for database permission tests.

Needs two connections to a database that has the migrations + seed applied:
  ADMIN_DATABASE_URL  owner connection (computes ground truth, installs the test HMAC key)
  AGENT_DATABASE_URL  sql_agent_login connection (what the service uses)
Skipped automatically when they are not set.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

import psycopg
import pytest

try:  # pick up .env when run locally (CI sets env vars directly)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from seed import DEMO_STAFF, demo_user_id  # noqa: E402

ADMIN = os.environ.get("ADMIN_DATABASE_URL")
AGENT = os.environ.get("AGENT_DATABASE_URL")
KEY_ID = "test-key"
LEAKS: list[dict] = []

pytestmark = pytest.mark.db


def pytest_collection_modifyitems(config, items):
    if ADMIN and AGENT:
        return
    skip = pytest.mark.skip(reason="ADMIN_DATABASE_URL / AGENT_DATABASE_URL not set")
    for item in items:
        if "permissions" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def secret() -> bytes:
    return os.environ.get("TEST_IDENTITY_HMAC_KEY", secrets.token_hex(32)).encode()


@pytest.fixture(scope="session")
def admin(secret):
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute(
            "insert into app.identity_keys (key_id, secret) values (%s, %s) "
            "on conflict (key_id) do update set secret = excluded.secret, active = true",
            (KEY_ID, secret),
        )
        try:
            yield conn
        finally:  # never leave a test signing key active in a real project
            conn.execute("delete from app.identity_keys where key_id = %s", (KEY_ID,))


@pytest.fixture(scope="session")
def agent():
    with psycopg.connect(AGENT) as conn:
        yield conn


@pytest.fixture(scope="session")
def users(admin):
    """demo key -> (uuid, app_role, branch_id), read back from app.staff_users."""
    out = {}
    for key, *_ in DEMO_STAFF:
        row = admin.execute(
            "select auth_user_id, app_role, branch_id from app.staff_users where auth_user_id = %s",
            (demo_user_id(key),),
        ).fetchone()
        assert row, f"demo identity {key} missing; run scripts/seed.py"
        out[key] = row
    return out


def record_leak(case: str, role: str, leaked_rows: int, detail: str = "") -> None:
    LEAKS.append({"case": case, "role": role, "leaked_rows": leaked_rows, "detail": detail})


def pytest_sessionfinish(session, exitstatus):
    if not (ADMIN and AGENT):
        return
    out = Path(os.environ.get("REPORTS_DIR", "reports")) / "permission_leaks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    total = sum(l["leaked_rows"] for l in LEAKS)
    out.write_text(json.dumps({"leaked_rows_total": total, "leaks": LEAKS}, indent=2, default=str))
