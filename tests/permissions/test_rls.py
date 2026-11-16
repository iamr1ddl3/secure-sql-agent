"""Permission tests: what each role can see, measured against the database itself.

A "leak" is any row returned that the role's ground-truth scope does not contain.
The CI gate requires leaked_rows_total == 0 (written to reports/permission_leaks.json).

These tests call db.run_as_user directly with hand-written SQL: they assume the input
guard, router and SQL validator have ALL been bypassed, and check that the database
alone still holds the line.
"""
from __future__ import annotations

import json
import uuid

import psycopg
import pytest
from psycopg import sql as pgsql

from secure_sql_agent.db import (PG_ROLE_FOR_APP_ROLE, NotStaffError, PermissionDenied, bind_identity,
                                 run_as_user)

from .conftest import KEY_ID, record_leak

CAP = 1_000_000

TABLES = {  # table -> (key expression, ground-truth filter for "own branch")
    "branches": ("branch_id::text", "branch_id = %(b)s"),
    "customers": ("customer_id::text", "branch_id = %(b)s"),
    "accounts": ("account_id::text", "branch_id = %(b)s"),
    "transactions": ("txn_id::text", "branch_id = %(b)s"),
    "loans": ("loan_id::text", "branch_id = %(b)s"),
    "employees": ("employee_id::text", "branch_id = %(b)s"),
    "salaries": ("employee_id || '/' || effective_from",
                 "employee_id in (select employee_id from bank.employees where branch_id = %(b)s)"),
}

# role -> table -> "all" | "branch" | "deny"
SCOPE = {
    "teller": dict(branches="all", customers="branch", accounts="branch", transactions="branch",
                   loans="deny", employees="deny", salaries="deny"),
    "branch_manager": dict(branches="all", customers="branch", accounts="branch", transactions="branch",
                           loans="branch", employees="branch", salaries="branch"),
    "hr": dict(branches="all", customers="deny", accounts="deny", transactions="deny",
               loans="deny", employees="all", salaries="all"),
    "auditor": {t: "all" for t in TABLES},
    "intern": dict(branches="all", customers="deny", accounts="deny", transactions="deny",
                   loans="deny", employees="deny", salaries="deny"),
}

DEMO_USERS = ["teller.surat", "manager.surat", "teller.mumbai", "manager.mumbai", "hr.officer", "auditor", "intern"]


def _run(agent, secret, sub, sql):
    return run_as_user(agent, sub, sql, key_id=KEY_ID, secret=secret, row_cap=CAP)


def _expected(admin, table, scope, branch):
    key, flt = TABLES[table]
    q = f"select {key} from bank.{table}" + (f" where {flt}" if scope == "branch" else "")
    return {r[0] for r in admin.execute(q, {"b": branch})}


@pytest.mark.parametrize("table", list(TABLES))
@pytest.mark.parametrize("user", DEMO_USERS)
def test_table_scope(admin, agent, secret, users, user, table):
    sub, app_role, branch = users[user]
    scope = SCOPE[app_role][table]
    sql = f"select {TABLES[table][0]} from bank.{table}"
    if scope == "deny":
        with pytest.raises(PermissionDenied):
            _run(agent, secret, sub, sql)
        return
    got = {r[0] for r in _run(agent, secret, sub, sql).rows}
    expected = _expected(admin, table, scope, branch)
    leaked = got - expected
    record_leak(f"scope:{table}", user, len(leaked))
    assert not leaked, f"{user} saw {len(leaked)} rows outside scope in {table}"
    assert got == expected, f"{user} is missing {len(expected - got)} rows it should see in {table}"


@pytest.mark.parametrize("table,column", [
    ("customers", "national_id"), ("customers", "phone"),
    ("accounts", "account_number"), ("employees", "phone"),
])
def test_auditor_cannot_read_raw_pii(agent, secret, users, table, column):
    with pytest.raises(PermissionDenied):
        _run(agent, secret, users["auditor"][0], f"select {column} from bank.{table} limit 1")


def test_auditor_reads_masked_pii(agent, secret, users):
    res = _run(agent, secret, users["auditor"][0],
               "select national_id_masked, phone_masked from bank.customers limit 20")
    assert res.rows and all(r[0].startswith("XXXXXXXX") and r[1].startswith("XXXXXX") for r in res.rows)


def test_intern_gets_aggregates_only(agent, secret, users):
    sub = users["intern"][0]
    for view, count_col in [("branch_monthly_flows", "txn_count"), ("branch_customer_counts", "customer_count"),
                            ("loan_portfolio_summary", "loan_count"), ("headcount_by_branch", "headcount")]:
        res = _run(agent, secret, sub, f"select {count_col} from analytics.{view}")
        assert res.rows, view
        small = [r for r in res.rows if r[0] < 5]
        record_leak(f"small_group:{view}", "intern", len(small))
        assert not small, f"{view} exposes groups smaller than 5"


@pytest.mark.parametrize("user", ["teller.surat", "manager.surat", "hr.officer"])
def test_non_analytics_roles_cannot_read_analytics(agent, secret, users, user):
    with pytest.raises(PermissionDenied):
        _run(agent, secret, users[user][0], "select * from analytics.branch_monthly_flows")


def test_unknown_identity_is_rejected(agent, secret):
    with pytest.raises(NotStaffError):
        _run(agent, secret, uuid.uuid4(), "select 1")


# ---------------------------------------------------------------------------
# Attacks. Worst case: the attacker controls MULTIPLE raw statements inside the
# user's transaction (far more than the validator will ever allow).
# ---------------------------------------------------------------------------

def _attack(agent, secret, sub, app_role, statements, bind=True):
    """Run statements after the service's normal setup. Returns rows of the last statement."""
    with agent.transaction() as tx, agent.cursor() as cur:
        try:
            cur.execute("set transaction read only")
            if bind:
                bind_identity(cur, sub, KEY_ID, secret)
            cur.execute(pgsql.SQL("set local role {}").format(pgsql.Identifier(PG_ROLE_FOR_APP_ROLE[app_role])))
            for s in statements:
                cur.execute(s)
            return cur.fetchall() if cur.description else []
        finally:
            tx  # transaction always rolled back/committed by context; read only either way


def _count_or_denied(agent, secret, sub, role, stmts):
    try:
        rows = _attack(agent, secret, sub, role, stmts)
    except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction):
        return 0
    return rows[0][0] if rows and isinstance(rows[0][0], int) else len(rows)


def test_attack_forged_claims_for_another_user(agent, secret, users):
    """Teller overwrites request.jwt.claims with the Mumbai manager's id (no valid signature)."""
    teller, mumbai_mgr = users["teller.surat"], users["manager.mumbai"]
    forged = json.dumps({"sub": str(mumbai_mgr[0]), "app_key": KEY_ID, "app_sig": "00" * 32})
    n = _count_or_denied(agent, secret, teller[0], "teller", [
        f"select set_config('request.jwt.claims', '{forged}', true)",
        "select count(*) from bank.customers",
    ])
    record_leak("attack:forged_claims", "teller.surat", n)
    assert n == 0


def test_attack_replayed_signature_with_new_sub(agent, secret, users):
    """Teller keeps its own valid signature but swaps the sub to HR."""
    teller, hr = users["teller.surat"], users["hr.officer"]
    with agent.transaction(), agent.cursor() as cur:
        cur.execute("set transaction read only")
        bind_identity(cur, teller[0], KEY_ID, secret)
        cur.execute("select current_setting('request.jwt.claims')")
        claims = json.loads(cur.fetchone()[0])
        claims["sub"] = str(hr[0])
        cur.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
        cur.execute("select * from app.whoami()")
        assert cur.fetchone() is None, "tampered claims must not resolve to any staff user"
    record_leak("attack:replayed_signature", "teller.surat", 0)


@pytest.mark.parametrize("user,target_role,table", [
    ("teller.surat", "bank_hr", "salaries"),
    ("teller.surat", "bank_auditor", "customers"),
    ("intern", "bank_auditor", "transactions"),
    ("hr.officer", "bank_branch_manager", "customers"),
])
def test_attack_switch_postgres_role(agent, secret, users, user, target_role, table):
    sub, app_role, _ = users[user]
    n = _count_or_denied(agent, secret, sub, app_role, [
        f"select set_config('role', '{target_role}', true)",
        f"select count(*) from bank.{table}",
    ])
    record_leak(f"attack:role_switch:{target_role}:{table}", user, n)
    assert n == 0


@pytest.mark.parametrize("table", ["app.identity_keys", "app.staff_users", "bank.salaries"])
def test_attack_reset_to_login_role(agent, secret, users, table):
    sub, app_role, _ = users["teller.surat"]
    n = _count_or_denied(agent, secret, sub, app_role, ["reset role", f"select count(*) from {table}"])
    record_leak(f"attack:reset_role:{table}", "teller.surat", n)
    assert n == 0


def test_attack_no_identity_bound(agent, secret, users):
    """Login role sets the auditor role itself but never binds a signed identity."""
    with agent.transaction(), agent.cursor() as cur:
        cur.execute("set local role bank_auditor")
        cur.execute("select count(*) from bank.customers")
        unbound = cur.fetchone()[0]
    record_leak("attack:no_identity", "unbound", unbound)
    assert unbound == 0


def test_attack_write_is_blocked(agent, secret, users):
    sub, app_role, _ = users["manager.surat"]
    with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
        _attack(agent, secret, sub, app_role, ["update bank.accounts set balance = 0"])
