"""Execute already-validated SQL as the end user.

This is the only module that touches the bank database. Per transaction it:
  1. starts a READ ONLY transaction on the low-privilege login role (sql_agent_login),
  2. binds the verified user id with an HMAC tied to this backend + transaction,
  3. asks the database which business role that user has (app.whoami, from app.staff_users),
  4. SET LOCAL ROLE to that business role, so grants + RLS apply,
  5. runs the SQL with a statement timeout and fetches at most cap+1 rows.

The LLM never sees credentials, and nothing here takes a role from the prompt, the router
or the caller: the role comes from the database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql as pgsql

PG_ROLE_FOR_APP_ROLE = {
    "teller": "bank_teller",
    "branch_manager": "bank_branch_manager",
    "hr": "bank_hr",
    "auditor": "bank_auditor",
    "intern": "bank_intern",
}


class NotStaffError(Exception):
    """The verified identity is not an active staff user."""


class PermissionDenied(Exception):
    """Postgres refused the query (missing grant on table/column/schema)."""


class QueryTimeout(Exception):
    pass


@dataclass
class QueryResult:
    app_role: str
    columns: list[tuple[str, str]]  # (name, postgres type name)
    rows: list[tuple[Any, ...]]
    truncated: bool
    notes: list[str] = field(default_factory=list)


def sign_binding(secret: bytes, sub: uuid.UUID, backend_pid: int, txn_ts_us: int) -> str:
    msg = f"{sub}:{backend_pid}:{txn_ts_us}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def bind_identity(cur: psycopg.Cursor, sub: uuid.UUID, key_id: str, secret: bytes) -> None:
    cur.execute("select backend_pid, txn_ts_us from app.txn_binding()")
    pid, ts = cur.fetchone()
    claims = {"sub": str(sub), "role": "authenticated", "app_key": key_id,
              "app_sig": sign_binding(secret, sub, pid, ts)}
    cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


def run_as_user(
    conn: psycopg.Connection,
    sub: uuid.UUID,
    validated_sql: str,
    *,
    key_id: str,
    secret: bytes,
    row_cap: int,
    statement_timeout_ms: int = 5000,
) -> QueryResult:
    """Run one validated SELECT as `sub`. Caller must pass SQL from the validator only."""
    if conn.autocommit:
        raise RuntimeError("connection must not be in autocommit mode")
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("set transaction read only")  # must be the first statement
        bind_identity(cur, sub, key_id, secret)
        cur.execute("select app_role from app.whoami()")
        row = cur.fetchone()
        if row is None:
            raise NotStaffError(str(sub))
        app_role = row[0]
        cur.execute(pgsql.SQL("set local role {}").format(pgsql.Identifier(PG_ROLE_FOR_APP_ROLE[app_role])))
        cur.execute(pgsql.SQL("set local statement_timeout = {}").format(pgsql.Literal(statement_timeout_ms)))
        try:
            cur.execute(validated_sql)
        except psycopg.errors.InsufficientPrivilege as e:
            raise PermissionDenied(str(e).splitlines()[0]) from e
        except psycopg.errors.QueryCanceled as e:
            raise QueryTimeout(str(e).splitlines()[0]) from e
        if cur.description is None:
            raise PermissionDenied("statement returned no result set")
        cols = [(d.name, _type_name(conn, d.type_code)) for d in cur.description]
        rows = cur.fetchmany(row_cap + 1)
        return QueryResult(app_role, cols, rows[:row_cap], truncated=len(rows) > row_cap)


def _type_name(conn: psycopg.Connection, oid: int) -> str:
    info = conn.adapters.types.get(oid)
    return info.name if info else str(oid)
