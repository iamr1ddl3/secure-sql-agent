# What did not work

Running log. Becomes the README's "What did not work" section.

- **2026-11-17 · Exposing the HMAC key through a DB function.** First draft had `app.identity_key()`
  callable by the login role so the service could fetch the key. But generated SQL can run
  `set_config('role', 'sql_agent_login', true)` and become the session's login role, so anything that
  role can call, an attacker's SELECT can call. Removed: the service keeps its own copy of the key.
- **2026-11-17 · Kaggle banking dataset.** Looked usable, but had no branch linkage, staff, salaries or PII
  columns, and uniform-random values. See docs/decisions.md D3.
- **Known UX gap (to measure):** RLS hides rows silently, so a Surat teller asking about Mumbai gets
  "0" rather than "you can't see that branch". The router/explainer needs to say so.
