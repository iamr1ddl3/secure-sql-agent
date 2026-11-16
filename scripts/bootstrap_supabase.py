"""One-time setup of the hosted Supabase project after the migrations are applied.

    python scripts/bootstrap_supabase.py

Reads .env, then:
  1. sets the sql_agent_login password (AGENT_DB_PASSWORD),
  2. installs the identity HMAC key (IDENTITY_HMAC_KEY),
  3. loads the synthetic dataset (scripts/seed.py --truncate),
  4. creates the demo Supabase Auth users (if SUPABASE_SECRET_KEY is set),
  5. runs the contract + permission test suite against Supabase.
Safe to re-run.
"""
import os
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

missing = [k for k in ("POOLER_HOST", "DB_OWNER_PASSWORD", "AGENT_DB_PASSWORD", "IDENTITY_HMAC_KEY")
           if not os.environ.get(k)]
if missing:
    raise SystemExit(f"Fill these in .env first: {', '.join(missing)}")


def step(title: str, cmd: list[str]) -> None:
    print(f"\n== {title}")
    subprocess.run(cmd, cwd=ROOT, env=os.environ, check=True)


print("== 1. sql_agent_login password")
with psycopg.connect(os.environ["ADMIN_DATABASE_URL"], autocommit=True) as conn:
    conn.execute(sql.SQL("alter role sql_agent_login password {}").format(
        sql.Literal(os.environ["AGENT_DB_PASSWORD"])))
with psycopg.connect(os.environ["AGENT_DATABASE_URL"]) as conn:
    print("   agent login ok:", conn.execute("select current_user").fetchone()[0])

step("2. identity key", [sys.executable, "scripts/setup_identity_key.py"])
step("3. synthetic data", [sys.executable, "scripts/seed.py", "--truncate"])
if os.environ.get("SUPABASE_SECRET_KEY"):
    step("4. demo auth users", [sys.executable, "scripts/provision_auth_users.py"])
else:
    print("\n== 4. demo auth users: skipped (set SUPABASE_SECRET_KEY to create them)")
step("5. tests against Supabase", [sys.executable, "-m", "pytest", "-q"])
print("\nDone. Leak report: reports/permission_leaks.json")
