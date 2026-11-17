"""The ontology (ontology/bank.yaml) and the deployed database must agree on who may read what."""
import subprocess
import sys
from pathlib import Path

import pytest

from secure_sql_agent import ontology

from .conftest import ADMIN  # noqa: F401  (module import also applies the db marker and skip rules)

PG_ROLE = {"teller": "bank_teller", "branch_manager": "bank_branch_manager", "hr": "bank_hr", "auditor": "bank_auditor",
           "intern": "bank_intern"}


def test_column_grants_match_ontology(admin):
    o = ontology.load()
    bad = []
    for role, pg in PG_ROLE.items():
        perms = o["permissions"][role]
        for ent, e in o["entities"].items():
            deny = set(perms.get(ent, {}).get("deny_columns", []))
            for c in e["columns"]:
                want = ent in perms and c["name"] not in deny
                got = admin.execute("select has_column_privilege(%s, %s, %s, 'select')", (pg, e["table"], c["name"])).fetchone()[0]
                if want != got:
                    bad.append((role, e["table"], c["name"], "ontology says", want, "db says", got))
    assert not bad, bad


def test_policy_exists_exactly_where_ontology_grants_rows(admin):
    o = ontology.load()
    bad = []
    for role, pg in PG_ROLE.items():
        for ent, e in o["entities"].items():
            if e.get("kind") == "view":
                continue
            schema, table = e["table"].split(".")
            has = admin.execute("select count(*) from pg_policies where schemaname = %s and tablename = %s and cmd = 'SELECT' "
                                "and %s = any(roles)", (schema, table, pg)).fetchone()[0] > 0
            if has != (ent in o["permissions"][role]):
                bad.append((role, e["table"], "policy in db" if has else "no policy in db"))
    assert not bad, bad


def test_generated_sql_is_current():
    root = Path(__file__).resolve().parents[2]
    assert subprocess.run([sys.executable, str(root / "scripts" / "gen_from_ontology.py"), "--check"]).returncode == 0
