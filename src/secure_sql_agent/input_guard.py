"""Input guard: cheap deterministic screen on the question before any model sees it.

Three checks, all pattern-based (no model call, so zero cost and ~0 ms): SQL pasted into the question, prompt-injection
phrasing, and system-prompt extraction. A hit means a refusal. The service takes natural-language questions only, so
pasted SQL is refused rather than executed. This is a first filter, not the security boundary: the database enforces
access whatever the text says. Patterns are tuned against the golden set: no benign item may be flagged
(false-block rate), every attack item in the first three attack types should be.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_QUESTION_CHARS = 1000

_R = lambda p: re.compile(p, re.IGNORECASE | re.DOTALL)  # noqa: E731
RULES: list[tuple[str, re.Pattern]] = [
    ("input_guard.sql_in_question", _R(
        r"\b(select\s.+?\sfrom\s|insert\s+into\b|update\s+\w+(\.\w+)?\s+set\b|delete\s+from\b|drop\s+(table|schema|database)\b"
        r"|alter\s+table\b|truncate\s+table\b|set\s+(local\s+)?role\b|set_config\s*\(|union\s+select\b|pg_sleep\s*\()"
        r"|;\s*(--|drop|select|delete|update|insert)")),
    ("input_guard.prompt_injection", _R(
        r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)"
        r"|disregard\s+(all\s+|any\s+)?(your|the|previous)\s+(rules|instructions|guidelines)"
        r"|(system|admin|developer)\s+override|(admin|developer|debug|god)\s+mode|you\s+are\s+now\b"
        r"|pretend\s+(you|to\s+be)\b|no\s+restrictions|without\s+(any\s+)?restrictions"
        r"|switch\s+to\s+(the\s+)?\w+\s+role|i\s+am\s+the\s+(ceo|cfo|admin|administrator|auditor|owner)\b"
        r"|i\s+authori[sz]e\s+you|the\s+current\s+user\s+is\s+an?\s+\w+")),
    ("input_guard.prompt_extraction", _R(
        r"(system|hidden|initial|original|secret)\s+(prompt|rules|instructions)"
        r"|repeat\s+(everything|all|the\s+text)\s+(above|before)|your\s+(instructions|guardrails|rules)\b"
        r"|guardrails\s+(were|are)\s+you|print\s+your\s+(prompt|instructions)|verbatim")),
]


@dataclass
class Verdict:
    allowed: bool
    policy_id: str | None = None
    detail: str | None = None


def check(question: str) -> Verdict:
    if len(question) > MAX_QUESTION_CHARS:
        return Verdict(False, "input_guard.too_long", f"question longer than {MAX_QUESTION_CHARS} characters")
    for policy_id, rx in RULES:
        if rx.search(question):
            return Verdict(False, policy_id, "question matched a blocked pattern")
    return Verdict(True)
