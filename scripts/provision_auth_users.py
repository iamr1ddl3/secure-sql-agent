"""Create a Supabase Auth user for each demo staff identity, using the SAME uuid that
scripts/seed.py wrote to app.staff_users, so tokens map straight onto roles.

    python scripts/provision_auth_users.py            # create users
    python scripts/provision_auth_users.py --token teller.surat   # print an access token

Needs SUPABASE_URL, SUPABASE_SECRET_KEY (admin; used ONLY by this script, never by the agent),
SUPABASE_PUBLISHABLE_KEY and DEMO_USER_PASSWORD.
"""
import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from seed import DEMO_STAFF, demo_user_id  # noqa: E402

URL = os.environ["SUPABASE_URL"].rstrip("/")
PASSWORD = os.environ["DEMO_USER_PASSWORD"]


def email(key: str) -> str:
    return f"{key}@bank.example"


def create_all() -> None:
    secret = os.environ["SUPABASE_SECRET_KEY"]
    headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}
    for key, role, *_ in DEMO_STAFF:
        body = {"id": str(demo_user_id(key)), "email": email(key), "password": PASSWORD,
                "email_confirm": True, "app_metadata": {"demo": True}}
        r = httpx.post(f"{URL}/auth/v1/admin/users", json=body, headers=headers, timeout=20)
        if r.status_code in (200, 201):
            print(f"created {email(key):40s} {role}")
        elif r.status_code == 422 and "already" in r.text:
            print(f"exists  {email(key):40s} {role}")
        else:
            raise SystemExit(f"{key}: {r.status_code} {r.text}")


def token(key: str) -> str:
    pub = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    r = httpx.post(f"{URL}/auth/v1/token?grant_type=password", headers={"apikey": pub},
                   json={"email": email(key), "password": PASSWORD}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--token", metavar="DEMO_KEY", help="print an access token for this demo user")
    a = p.parse_args()
    print(token(a.token)) if a.token else create_all()
