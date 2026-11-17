import uuid

from secure_sql_agent.review import BULK_PII_ROWS, ReviewStore, needs_review


def test_policy_only_bulk_raw_pii():
    assert needs_review(["full_name", "phone"], BULK_PII_ROWS + 1)
    assert not needs_review(["full_name", "phone"], BULK_PII_ROWS)  # small lookups are fine
    assert not needs_review(["full_name", "phone_masked"], 500)  # masked is not raw
    assert not needs_review(["balance"], 500)


def test_store_roundtrip_and_single_decision(tmp_path):
    s = ReviewStore(tmp_path / "q.db")
    rid = s.create(uuid.uuid4(), "teller", "export phones", "select phone from bank.customers", 100)
    assert [r["id"] for r in s.pending()] == [rid]
    assert s.decide(rid, uuid.uuid4(), True) is True
    assert s.decide(rid, uuid.uuid4(), False) is False  # cannot be decided twice
    assert s.get(rid)["status"] == "approved" and not s.pending()
    assert s.decide("rv_nope", uuid.uuid4(), True) is False


def test_only_the_requester_collects_an_approved_review_once(tmp_path):
    s = ReviewStore(tmp_path / "q.db")
    me, approver = uuid.uuid4(), uuid.uuid4()
    rid = s.create(me, "teller", "q", "select 1", 10)
    assert s.collect(rid, me) is None              # not approved yet
    s.decide(rid, approver, True)
    assert s.collect(rid, approver) is None        # the approver never gets the data
    assert s.collect(rid, me)["sql"] == "select 1"
    assert s.collect(rid, me) is None              # once only
