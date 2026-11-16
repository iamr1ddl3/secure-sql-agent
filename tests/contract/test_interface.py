"""Contract tests: the frozen JSON Schema, its examples and the Pydantic models must agree."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from secure_sql_agent.contracts import QueryRequest, QueryResponse

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "interface/query_bank_data.v1.schema.json").read_text())
EXAMPLES = sorted((ROOT / "interface/examples").glob("*.json"))


def _validator(defname: str) -> Draft202012Validator:
    return Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{defname}"})


REQ = _validator("QueryRequest")
RESP = _validator("QueryResponse")


def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_examples_match_schema_and_models(path):
    data = json.loads(path.read_text())
    if path.name.startswith("request."):
        REQ.validate(data)
        QueryRequest.model_validate(data)
    else:
        RESP.validate(data)
        model = QueryResponse.model_validate(data)
        # Round trip through the model must still satisfy the schema.
        RESP.validate(model.model_dump(mode="json"))


def test_every_status_has_an_example():
    statuses = {
        json.loads(p.read_text())["status"] for p in EXAMPLES if p.name.startswith("response.")
    }
    assert statuses == {"answered", "refused", "needs_review", "error"}


def test_request_rejects_unknown_fields():
    bad = {"question": "x", "identity": "a" * 30, "role": "auditor"}
    assert list(REQ.iter_errors(bad)), "schema must reject unknown request fields"
    with pytest.raises(Exception):
        QueryRequest.model_validate(bad)


def test_response_tolerates_additive_fields():
    data = json.loads((ROOT / "interface/examples/response.answered.json").read_text())
    data["some_future_field"] = 1
    RESP.validate(data)
    QueryResponse.model_validate(data)


def test_required_fields_match_between_schema_and_model():
    schema_req = set(SCHEMA["$defs"]["QueryRequest"]["properties"])
    assert schema_req == set(QueryRequest.model_fields)
    schema_resp = set(SCHEMA["$defs"]["QueryResponse"]["properties"])
    assert schema_resp == set(QueryResponse.model_fields)
