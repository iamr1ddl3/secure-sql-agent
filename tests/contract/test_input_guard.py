"""Input guard against the golden set: no benign item flagged, first three attack types all flagged."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals" / "golden"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify import load_items  # noqa: E402

from secure_sql_agent.input_guard import check  # noqa: E402

ITEMS = load_items()


def test_no_benign_question_is_blocked():
    benign = [i for i in ITEMS if i["group"] != "attack" or i.get("attack_type") == "data_injection"]
    blocked = [(i["id"], check(i["question"]).policy_id) for i in benign if not check(i["question"]).allowed]
    assert not blocked, blocked


def test_direct_sql_and_extraction_attacks_are_blocked():
    atk = [i for i in ITEMS if i["group"] == "attack" and i.get("attack_type") != "data_injection"]
    missed = [i["id"] for i in atk if check(i["question"]).allowed]
    assert not missed, missed


def test_too_long():
    assert check("x" * 1001).policy_id == "input_guard.too_long"
