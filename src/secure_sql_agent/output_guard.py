"""Output guard: last check on rows before they leave the service.

The database already withholds raw PII from roles without a grant (auditor sees *_masked columns only). This stage is the
belt-and-braces layer: it flags masked columns for the response and, for roles that may NOT see raw identifiers,
masks anything shaped like one that still shows up in a text cell (for example inside a free-text description).
Tellers and managers legitimately see their own branch's identifiers, so nothing is masked for them.
"""
from __future__ import annotations

import re

from .contracts import Column, PolicyHit

NO_RAW_PII = {"auditor", "intern", "hr"}  # roles that must never receive a raw national ID / phone / account number
ROW_CAP_MAX = 1000
_PATTERNS = [
    ("phone", re.compile(r"\+\d{2}[ -]?\d{10}(?!\d)"), "XXXXXX"),  # +91 first: it is also 12 digits
    ("national_id", re.compile(r"(?<!\d)\d{12}(?!\d)"), "XXXXXXXX"),
    ("account_number", re.compile(r"(?<!\d)\d{13,14}(?!\d)"), "XXXXXXXXXX"),
    ("phone", re.compile(r"(?<!\d)\d{10}(?!\d)"), "XXXXXX"),
]


def _mask_text(s: str, hits: set[str]) -> str:
    for name, rx, fill in _PATTERNS:
        def sub(m, name=name, fill=fill):
            hits.add(name)
            return fill + m.group(0)[-4:]
        s = rx.sub(sub, s)
    return s


def guard(app_role: str, columns: list[tuple[str, str]], rows: list[tuple], max_rows: int):
    """Return (Column list, rows as lists, truncated_by_cap, policy hits)."""
    cap = min(max_rows, ROW_CAP_MAX)
    cols = [Column(name=n, type=t, masked=n.endswith("_masked")) for n, t in columns]
    hits: set[str] = set()
    out = []
    for r in rows[:cap]:
        out.append([_mask_text(v, hits) if app_role in NO_RAW_PII and isinstance(v, str) else v for v in r])
    policy = [PolicyHit(policy_id=f"output_guard.mask_{h}", stage="output_guard", action="mask",
                        detail=f"masked {h}-shaped value in a text cell") for h in sorted(hits)]
    if len(rows) > cap:
        policy.append(PolicyHit(policy_id="output_guard.row_cap", stage="output_guard", action="cap",
                                detail=f"result capped at {cap} rows"))
    return cols, out, len(rows) > cap, policy
