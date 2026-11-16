# Golden set (stage 1)

~150 hand-checked questions, versioned here. Each item: `id`, `group`, `asked_by` (demo identity),
`question`, `reference_sql` (run by the owner role to get the expected result), and `expect`
(`answered` | `refused` | `needs_review` | `clarify`).

Groups: single_table, joins, aggregation_time, ambiguous, out_of_scope, permission_boundary
(same question per role, expected result differs), attack (direct injection, injection in data
values, SQL in the question, system-prompt extraction).

Scoring is **execution accuracy**: compare result sets, not SQL text.
Relative dates ("last month") resolve against `app.dataset_meta.as_of` (2026-11-01 by default),
never the wall clock, so expectations never drift.

Rule: drafts may be LLM-assisted, but every item is checked by a human before it lands here.
