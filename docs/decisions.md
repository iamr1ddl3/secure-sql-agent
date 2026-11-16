# Decision log

## D1 · 2026-11-17 · Hosted Supabase for the bank database
Dev and demo run on a hosted Supabase project. CI applies the *same* migration files to an
ephemeral `postgres:16`, so permission tests need no secrets and run on every PR.
Migrations avoid Supabase-only objects (`auth.uid()`), so both targets behave the same.

## D2 · 2026-11-17 · All models via OpenRouter
Every model (Claude and challengers) is called through OpenRouter's OpenAI-compatible API, so
latency and cost per 1,000 queries are measured the same way. Model ids are pinned in
`config/models.yaml` and recorded in every eval report.

## D3 · 2026-11-17 · Generated dataset, not the Kaggle "banking_dataset"
The Kaggle dataset was evaluated and rejected for Project 1:
- no link from customers/accounts/transactions to branches, so branch-scoped RLS (the teller and
  manager cases) cannot be expressed;
- no employees or salaries, so the HR and "intern asks for the CEO's salary" cases are impossible;
- no PII-style columns (national id, phone, full account number), so masking cannot be shown;
- loans have no status or days past due ("loans over 90 days overdue" is unanswerable);
- values are uniform random: amounts uniform on 1–10,000 USD, ~143k transactions in every year
  2019–2025, ~25k distinct random cities for 50k customers, so every aggregate looks the same.
`scripts/seed.py` generates a documented synthetic Indian bank (INR, Gujarat-heavy branch network)
with these relationships, realistic skew, and a fixed seed and as-of date.

## D4 · 2026-11-17 · Identity bound per transaction with an HMAC
`request.jwt.claims` alone is forgeable from inside SQL (`set_config`). Claims carry an HMAC over
(sub, backend pid, transaction start) that only `app.current_sub()` can verify. A bad signature
resolves to no user, so every policy returns zero rows. See migration `..._identity.sql`.

## D5 · 2026-11-17 · One Postgres role per business role, plus RLS
`sql_agent_login` (NOINHERIT, no grants) must `SET LOCAL ROLE bank_<role>`; the role comes from
`app.staff_users`, never from the prompt or the caller. Grants are the table/column allowlist
(auditor gets only masked PII columns; intern gets only aggregate views); RLS filters rows.
Every policy checks both the Postgres role and the verified app role, so role switching inside a
query gains nothing.

## Open
- [ ] Repo names (P1/P2)
- [ ] Ontology storage (plan: YAML first)
- [ ] Jev access: OpenRouter or TypeSafe console
- [ ] Start date → gate calendar dates
- [ ] Confirm exact OpenRouter model ids in `config/models.yaml`
