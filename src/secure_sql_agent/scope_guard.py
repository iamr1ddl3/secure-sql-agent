"""Say "you can't see that branch" instead of returning a silent 0.

Row-level security hides other branches' rows without any error, so a Surat teller asking about "the Mumbai branch"
would get an empty or zero answer that looks real. Tellers and managers are limited to their own branch, so a question
that names ANOTHER branch (code, full name, or "<city> branch") is refused up front with a clear message.
Narrow on purpose: a bare city name is not enough, since customers can live in any city.
"""
from __future__ import annotations

import re


def other_branch_named(question: str, own_branch_id: int, branches: list[tuple]) -> tuple | None:
    """branches: (branch_id, branch_code, name, city). Returns the other branch the question names, or None."""
    q = question.lower()
    for bid, code, name, city in branches:
        if bid == own_branch_id:
            continue
        if code.lower() in q or name.lower() in q or re.search(rf"\b{re.escape(city.lower())}\s+branch\b", q) \
                or re.search(rf"\bbranch\s+(in|at|of)\s+{re.escape(city.lower())}\b", q):
            return (bid, code, name, city)
    return None
