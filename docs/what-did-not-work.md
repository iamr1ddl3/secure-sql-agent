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

- **2026-11-18 · Langfuse returned 401 although the keys were valid.** The project lives in the US region and the code
  defaulted to the EU host. A key pair is only valid on the region that created it, so every region must be tried
  (`GET /api/public/projects` with basic auth) before blaming the keys. `.env.example` now says `LANGFUSE_HOST` must match.
- **2026-11-18 · "Jev" on OpenRouter was not the decision model.** `typesafe/jev-router` is an auto-router that forwards the
  request to another model (a probe was served by `openai/gpt-6-luna`). The typed Choice/Noul/Score model is
  `typesafe/jev-1.13` on `POST /api/alpha/decisions`. Benchmarking the router id would have scored a different model under
  Jev's name.
- **2026-11-18 · Jev lost the router comparison: 85.0% held-out vs 95.0% for the small LLM, 82.7% vs 97.3% on the golden set.**
  It sent 23 of 150 answerable questions back as "ambiguous" (over-asking, which users feel as false blocks). It is about
  40% faster and 3.5x cheaper, so it stays a documented alternative, not the default. One run each.
- **2026-11-18 · The Claude Code Langfuse plugin was sending every chat session to the app's Langfuse project.** Session
  traces (messages, tool inputs) mixed with app traces. Plugin config removed and the 8 session traces deleted; use a separate
  Langfuse project if session tracing is wanted again. App traces never include result rows.
- **2026-11-19 · The seed gave Surat and Mumbai two active Branch Managers each.** The demo logins `manager.surat` and
  `manager.mumbai` were added as extra employee rows on top of each branch's generated manager. The golden-set review caught it
  (jn-11 returned 12 managers for 10 branches). Fix: the demo login now takes over the branch's existing manager row. `add()` still
  runs so the random stream, and every customer, account, transaction and loan, stays identical; only 2 employees and their
  4 salary rows go (142 to 140 employees).
- **2026-11-19 · Rows were dated before the branch or customer they belong to.** 735 customers, 221 accounts, 13 loans and
  33 employees predated their branch's opening date, and 377 loans were disbursed before the customer existed. Branch opening
  dates were labels no generator read, and loan dates were drawn from a fixed 2016 floor. Fix: branches now open 1996–2004
  (same order), before the 2005 hiring floor, and each loan date starts at the customer's creation date. Customers, accounts,
  transactions and employees are unchanged; only loan dates and outstanding amounts moved (no counts). Guarded by
  `tests/contract/test_seed_dates.py`.
- **2026-11-19 · The golden set had 4 wrong references, and the review moved the headline number both ways.** pb-24..27
  ("average current salary of our employees") averaged staff who had left; a leaver has no current salary, and the agent kept
  (correctly) filtering to active staff, so it failed those items every run. Fixed to active only. Execution accuracy:
  96.8% pre-review (tuned while looking at the set), 94.7% after the seed fixes with the wrong references, **97.9%** after the
  reference fix. One run each; ag-23, pb-15 and pb-26 failed in the 94.7% run and passed on replay, so swings of ~2 points
  between runs are normal. Remaining misses: ag-25 (extra column, scorer is strict), am-06 and am-15 (guessed instead of
  asking back), ag-03 (this run only). Pre-review report kept at `docs/results/golden_prereview_haiku.json`.
- **2026-11-19 · Second pass on the remaining failures: one undefined convention, one strict scorer, two router misses.**
  ag-03 ("last 7 days") failed 1 run in 3: the prompt defined "last month" but not "last N days", so the model guessed whether
  today counts. The prompt now defines it. ag-25 returned the right month plus its total and failed only because the scorer wanted
  exactly the reference columns; the scorer now accepts extra columns (rows must still match exactly). am-06 ("Show recent
  transactions") and am-15 ("Show me Harish's details") were answered instead of asked back; am-15 returned date of birth and
  contact details for 6 customers when the teller meant one. The router now asks back for unfiltered lists and first-name-only
  lookups. All four were found on the scored set; the held-out router set was the check against over-asking (95.0/97.5% before,
  97.5/97.5% after, no answerable question sent back). Result: execution accuracy 97.9% (unchanged), item pass 97.3% → 98.0%.
  New in this run: pb-22 and pb-26 (passed 3 of 3 on replay, noise) and pb-24, which fails 3 of 3: for the Surat manager the agent
  averages staff who have left, for HR it filters to active. Left open rather than tuned.
