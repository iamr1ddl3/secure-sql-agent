"""Pipeline graph behaviour that needs no database: model replies that are prose are a refusal, not an error."""
import uuid
from types import SimpleNamespace

from secure_sql_agent.pipeline import Pipeline, Usage


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, system, user, max_tokens=None, name="llm-call"):
        return SimpleNamespace(text=self.text, cost_usd=0.001, prompt_tokens=10, completion_tokens=5, latency_ms=1)


def pipe(text):
    return Pipeline(router=None, sql_llm=FakeLLM(text), conn_factory=lambda: None, key_id="k", secret=b"s")


def state(role="hr"):
    return {"question": "q", "role": role, "sub": uuid.uuid4(), "max_rows": 10, "attempt": 0, "hits": [], "usage": Usage(), "conn": None}


def test_prose_reply_is_declined_not_error():
    out = pipe("Customer tables are not available to HR.")._generate(state())
    assert out["error_kind"] == "generation.declined" and out["hits"][0].policy_id == "generation.declined"


def test_fenced_sql_is_extracted():
    out = pipe("```sql\nSELECT 1 FROM bank.branches;\n```")._generate(state())
    assert out["sql"] == "SELECT 1 FROM bank.branches" and out["error"] is None
