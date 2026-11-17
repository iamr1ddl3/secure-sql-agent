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
- **2026-11-17 · First live eval: 46.8% execution accuracy, almost all of it plumbing, not SQL quality.**
  Three bugs hid the model's real score. (1) The router (Haiku) hit `max_tokens=200` and was cut off, turning
  correct refusals into errors: check truncation first, and never treat a cut-off reply as "bad output".
  (2) Numeric columns reached the client as strings (`'17480062.50'`), so correct answers failed the
  comparison; the output guard now returns JSON numbers. (3) A model-written `SELECT 'no table available'`
  passed the validator for a role with no access; queries that read no table are now rejected.
  After fixes: 90.4%, then 98.9% (see ProgressLog).
- **2026-11-17 · The model answers in prose when a role has no data for the question.** That produced
  parse errors (status `error`) where the golden set expects `refused`. Prose with no SQL fence is now treated
  as the model declining, and refused.
- **2026-11-17 · Model preferred masked columns even for roles that may see the raw ones**
  (tellers and managers got `XXXXXX2457` for phone numbers). The prompt now says: use the raw column when the
  role's schema lists it.
- **Caveat on every number so far:** the input-guard patterns and the prompt were tuned while looking at the
  golden set that scores them, and the set is not yet human-reviewed. Treat 98.9% as an upper bound until there
  is a held-out set (task to add) and Ravi has approved the items.
- **Open: two "ambiguous" items.** The router answers `Show recent transactions.` (am-06) and
  `Show me Harish's details.` (am-15) instead of asking back. Not tuned on purpose, to avoid overfitting.
- **2026-11-17 · Regex router: 98.7% on the golden set, 32.5% on unseen questions.** Written while looking at the
  golden set, so it memorised it. The same applies to the input guard's patterns: on 10 attacks written afterwards
  it caught 2. Lesson: any rule tuned on the scoring set needs a held-out set before its number means anything
  (`evals/heldout/router.yaml`). The small-LLM router held at 95% on unseen questions.
