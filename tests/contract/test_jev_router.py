"""JevRouter against a fake decisions endpoint: maps the Choice answer to a label, records cost, fails closed on junk."""
import httpx
import pytest

from secure_sql_agent.llm import LLMError
from secure_sql_agent.pipeline import Usage
from secure_sql_agent.routers import JevRouter


def router(handler):
    return JevRouter("k", client=httpx.Client(transport=httpx.MockTransport(handler)))


def ok(label):
    return lambda req: httpx.Response(200, json={"answers": {"route": {"type": "choice", "choice": label}},
                                                 "usage": {"input_tokens": 400, "output_tokens": 50, "cost": 0.00002}})


def test_maps_choice_to_label_and_records_cost():
    u = Usage()
    assert router(ok("ambiguous")).route("Show me the top ones", "teller", u)[0] == "ambiguous"
    assert u.cost_usd == 0.00002 and u.prompt_tokens == 400 and u.llm_calls == 1


def test_request_pins_model_and_lists_role_tables():
    seen = {}

    def h(req):
        seen.update(__import__("json").loads(req.content))
        return ok("answerable")(req)

    router(h).route("How many customers?", "teller", Usage())
    assert seen["model"] == "typesafe/jev-1.13" and "bank.customers" in seen["state"]["tables"]


@pytest.mark.parametrize("resp", [httpx.Response(500), httpx.Response(200, json={"answers": {}}), ok("maybe")(None)])
def test_junk_or_error_raises(resp):
    with pytest.raises(LLMError):
        router(lambda req: resp).route("q", "teller", Usage())
