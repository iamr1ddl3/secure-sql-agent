"""Tracing: masking, no-op when off, and (with an in-memory exporter, no network) the span tree for one request."""
import uuid
from types import SimpleNamespace

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from secure_sql_agent import tracing
from secure_sql_agent.llm import LLM
from secure_sql_agent.pipeline import Pipeline, Usage


def test_mask_hides_emails_and_long_numbers():
    out = tracing.mask(data={"q": "mail a@b.com about 123456789012", "n": [1, "ok"]})
    assert out == {"q": "mail [email] about [number]", "n": [1, "ok"]}


def test_noop_when_off():
    assert not tracing.enabled()
    with tracing.request("tr_x", input={}, user_id="u") as root:
        root.update(output={})
    with tracing.observation("x", "generation", model="m") as o:
        o.update(output="y")


def test_request_trace_has_nested_observations_and_no_rows(monkeypatch):
    from langfuse import Langfuse

    exp = InMemorySpanExporter()
    monkeypatch.setattr(tracing, "_client", Langfuse(public_key="pk-lf-test", secret_key="sk-lf-test", host="http://localhost:1",
                                                     span_exporter=exp, mask=tracing.mask))
    llm = LLM("m", "k")
    llm._complete = lambda messages, max_tokens: SimpleNamespace(text="```sql\nSELECT 1 FROM bank.branches\n```", cost_usd=0.001,
                                                                 prompt_tokens=10, completion_tokens=5, latency_ms=1)
    p = Pipeline(router=None, sql_llm=llm, conn_factory=lambda: None, key_id="k", secret=b"s")
    st = {"question": "q about 123456789012", "role": "hr", "sub": uuid.uuid4(), "max_rows": 10, "attempt": 0, "hits": [],
          "usage": Usage(), "conn": None}
    with tracing.request("tr_abc", input={"question": st["question"]}, user_id="u1"):
        st.update(p._generate(st))
        p._validate(st)
    tracing._client.flush()
    spans = {s.name: s for s in exp.get_finished_spans()}
    assert {"answer-question", "generate-sql", "validate-sql"} <= spans.keys()
    root = spans["answer-question"]
    assert spans["generate-sql"].parent.span_id == root.context.span_id == spans["validate-sql"].parent.span_id
    attrs = spans["generate-sql"].attributes
    assert attrs["langfuse.observation.type"] == "generation" and attrs["langfuse.observation.model.name"] == "m"
    assert "123456789012" not in str(dict(root.attributes))  # masked before export
