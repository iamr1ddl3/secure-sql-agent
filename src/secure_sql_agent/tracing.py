"""Langfuse tracing. Off (no-op) unless both keys are set, and it never raises into a request.

What goes into a trace: the question, role, generated SQL, router label, policy hits, status, row counts, token usage and
cost. What never does: result rows (they can hold PII the database only released to that user), keys, or the identity token.
Everything is also passed through `mask` before it leaves the process.
"""
from __future__ import annotations

import re
from contextlib import contextmanager

_client = None

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS = re.compile(r"\d{9,}")  # phone, national id, account numbers


def mask(*, data, **_):
    if isinstance(data, str):
        return _LONG_DIGITS.sub("[number]", _EMAIL.sub("[email]", data))
    if isinstance(data, dict):
        return {k: mask(data=v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask(data=v) for v in data]
    return data


class _Noop:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def update(self, **_):
        pass


def init(settings) -> bool:
    """Create the client once from Settings (which reads .env). Returns whether tracing is on."""
    global _client
    if _client is not None:
        return True
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return False
    from langfuse import Langfuse

    _client = Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
                       host=settings.langfuse_host, mask=mask)
    return True


def enabled() -> bool:
    return _client is not None


def observation(name: str, as_type: str = "span", **kw):
    """Context manager for one observation; no-op when tracing is off."""
    return _client.start_as_current_observation(name=name, as_type=as_type, **kw) if _client else _Noop()


@contextmanager
def request(trace_id: str, *, input, user_id: str):
    """Root span for one request plus trace-level attributes. The API's `trace_id` seeds the Langfuse trace id, so a
    response's trace_id can be found in Langfuse via `Langfuse.create_trace_id(seed=trace_id)`."""
    if not _client:
        yield _Noop()
        return
    from langfuse import propagate_attributes

    with _client.start_as_current_observation(
            name="answer-question", as_type="span", input=input, metadata={"api_trace_id": trace_id},
            trace_context={"trace_id": _client.create_trace_id(seed=trace_id)}) as root, \
            propagate_attributes(user_id=user_id, trace_name="answer-question", tags=["sql-agent"]):
        yield root


def flush() -> None:
    if _client:
        _client.flush()
