# How to review the golden set (task 48)

The 150 golden items are the scoring set for every number in the README. None has been checked by a human yet
(`reviewed: false` everywhere), and prompts and guard patterns were tuned while looking at them. Until this review
is done, treat 98.9% execution accuracy as an upper bound, not a final result. This is the only step that gates the
`v1.0.0` tag.

## Where things are

| What | Path |
| --- | --- |
| Review sheet (one block per item: question, SQL, row count, first rows) | `reports/golden_review.md` |
| The items themselves, one YAML per group | `evals/golden/<group>.yaml` |
| Regenerate the sheet and re-run the owner-vs-asking-identity cross-check | `python evals/golden/verify.py` (or `verify.py at am`, by id prefix) |
| Format test (no database needed) | `pytest tests/contract/test_golden_format.py` |

## Checklist per item

1. **Question.** Is it something that role would plausibly ask, in plain words?
2. **SQL.** Does the reference SQL answer exactly that question? Check the branch id, the date window
   (relative dates resolve against `app.dataset_meta.as_of`, 2026-11-01, never the wall clock), `txn_type` and the grouping.
3. **Result.** Are the row count and first rows plausible for the dataset (10 branches, 5,000 customers, 99,181 transactions)?
4. **Expected status.** Is `answered` / `refused` / `needs_review` / `needs_clarification` the right outcome for *that role*?

## Order and what to look for

| Group | Items | Focus |
| --- | --- | --- |
| attack | 20 | at-01..15 must expect `refused`. at-16..20 are harmless questions whose answer is a planted instruction; they must be `answered`, returning the text as plain data (see `canary`). |
| permission_boundary | 35 | Same 5 questions across 7 roles. The expectation must equal what that role may see. Interns read aggregate views that suppress groups under 5 rows, so their totals are lower than the real ones (closed loans 5 vs 56). |
| ambiguous | 15 | Would a human analyst also have to ask back? am-01, am-06, am-09 were deliberately kept ambiguous. |
| out_of_scope | 15 | Truly unanswerable from this database (advice, actions, predictions, writes). |
| single_table, joins, aggregation_time | 65 | Read the SQL line by line. |

## Recording the result

- Approve an item: set `reviewed: true` on it in its YAML file (flip by hand; never by script without reading).
- Wrong item: fix the YAML (question, `reference_sql`, `expect`), then run `python evals/golden/verify.py` to confirm the
  owner and asking-identity results still match, and re-read the regenerated block.
- When a whole group is done, run `pytest tests/contract/test_golden_format.py`.
- When all 150 are `reviewed: true`: re-run `python evals/run_eval.py`, update `evals/baseline.json` if the numbers moved,
  update the README results and the tracker (task 48), then tag `v1.0.0`.

## If fixes change the numbers

Fixing an item can move accuracy in either direction. That is the point of the review: report the post-review number, and
keep the pre-review one in `docs/what-did-not-work.md` as the size of the tuning effect.
