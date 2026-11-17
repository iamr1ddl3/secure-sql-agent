"""Shape checks for the golden set. No database needed; verify.py checks the SQL itself."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals" / "golden"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from seed import DEMO_STAFF  # noqa: E402
from verify import load_items  # noqa: E402

GROUPS = {"single_table", "joins", "aggregation_time", "ambiguous", "out_of_scope", "permission_boundary", "attack"}
EXPECT = {"answered", "refused", "needs_review", "needs_clarification"}
IDENTITIES = {k for k, *_ in DEMO_STAFF}
ITEMS = load_items()


def test_ids_unique():
    assert len({i["id"] for i in ITEMS}) == len(ITEMS)


def test_fields_valid():
    for i in ITEMS:
        assert i["group"] in GROUPS, i["id"]
        assert i["expect"] in EXPECT, i["id"]
        assert i["asked_by"] in IDENTITIES, i["id"]
        assert 0 < len(i["question"]) <= 1000, i["id"]  # request schema limit


def test_answered_items_have_read_only_sql():
    for i in ITEMS:
        sql = (i.get("reference_sql") or "").strip().lower()
        if i["expect"] == "answered":
            assert sql.startswith(("select", "with")), i["id"]
            assert not any(w in sql for w in ("insert ", "update ", "delete ", "drop ", ";")), i["id"]
        else:
            assert not sql, f"{i['id']}: only answered items carry reference_sql"


def test_permission_pairs_cover_all_identities():
    pairs = Counter(i["pair"] for i in ITEMS if i["group"] == "permission_boundary")
    assert pairs and all(n == len(IDENTITIES) for n in pairs.values())
    pb = [i for i in ITEMS if i["group"] == "permission_boundary"]
    for p in pairs:
        assert {i["asked_by"] for i in pb if i["pair"] == p} == IDENTITIES
