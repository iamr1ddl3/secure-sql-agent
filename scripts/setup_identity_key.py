"""Install (or rotate) the HMAC key used to bind user identity to a DB transaction.

    python scripts/setup_identity_key.py --dsn "$ADMIN_DATABASE_URL"

Reads IDENTITY_HMAC_KEY_ID / IDENTITY_HMAC_KEY from the environment (same values the service uses).
Generate a key with:  python -c "import secrets; print(secrets.token_hex(32))"
"""
import argparse
import os

import psycopg

p = argparse.ArgumentParser()
p.add_argument("--dsn", default=os.environ.get("ADMIN_DATABASE_URL"))
args = p.parse_args()
key_id = os.environ.get("IDENTITY_HMAC_KEY_ID", "k1")
key = os.environ["IDENTITY_HMAC_KEY"]
if len(key) < 32:
    raise SystemExit("IDENTITY_HMAC_KEY must be at least 32 characters")
with psycopg.connect(args.dsn, autocommit=True) as conn:
    conn.execute(
        "insert into app.identity_keys (key_id, secret) values (%s, %s) "
        "on conflict (key_id) do update set secret = excluded.secret, active = true",
        (key_id, key.encode()),
    )
    conn.execute("update app.identity_keys set active = false where key_id <> %s", (key_id,))
print(f"identity key {key_id!r} installed; other keys deactivated")
