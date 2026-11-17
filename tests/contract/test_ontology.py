"""The ontology must reproduce the hand-written stage-1 allowlists and schema text exactly (fixtures taken before the
refactor), so moving to a single source changed no behaviour."""
import json
from pathlib import Path

import pytest

from secure_sql_agent import ontology
from secure_sql_agent.validator import DENIED_COLUMNS, TABLES

FIX = Path(__file__).resolve().parents[1] / "fixtures"
V1 = json.loads((FIX / "access_v1.json").read_text())


def test_allowlists_match_stage1():
    assert {k: sorted(v) for k, v in TABLES.items()} == V1["tables"]
    assert {k: sorted(v) for k, v in DENIED_COLUMNS.items()} == V1["denied"]


@pytest.mark.parametrize("role", list(V1["tables"]))
def test_baseline_schema_text_unchanged(role):
    assert ontology.schema_for(role) == (FIX / f"schema_{role}.txt").read_text()


def test_semantic_text_adds_vocabulary_without_leaking_hidden_columns():
    t = ontology.schema_for("auditor", semantic=True)
    assert "also called: client" in t and "Business terms:" in t and "rows: all branches" in t
    assert " phone text" not in t and "national_id text" not in t  # still withheld
    assert "rows: your own branch only" in ontology.schema_for("teller", semantic=True)
    assert "bank.salaries" not in ontology.schema_for("teller", semantic=True)
