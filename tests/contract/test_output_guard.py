from secure_sql_agent.output_guard import guard


def test_masks_identifier_shapes_for_auditor_only():
    rows = [("note 123456789012 call +919876543210",), ("acct 01996675185035",)]
    _, out, _, hits = guard("auditor", [("description", "text")], rows, 100)
    assert "123456789012" not in out[0][0] and out[0][0].count("9012") == 1
    assert "9876543210" not in out[0][0] and "01996675185035" not in out[1][0]
    assert {h.policy_id for h in hits} == {"output_guard.mask_national_id", "output_guard.mask_phone",
                                           "output_guard.mask_account_number"}
    _, teller_out, _, teller_hits = guard("teller", [("description", "text")], rows, 100)
    assert teller_out == [list(r) for r in rows] and not teller_hits


def test_numbers_and_masked_flag_untouched():
    cols, out, _, hits = guard("auditor", [("national_id_masked", "text"), ("balance", "numeric")],
                               [("XXXXXXXX8512", 1234567890123.0)], 10)
    assert cols[0].masked and not cols[1].masked and out == [["XXXXXXXX8512", 1234567890123.0]] and not hits


def test_row_cap():
    cols, out, truncated, hits = guard("teller", [("x", "int4")], [(i,) for i in range(5)], 3)
    assert len(out) == 3 and truncated and hits[0].policy_id == "output_guard.row_cap"
    _, out, truncated, _ = guard("teller", [("x", "int4")], [(i,) for i in range(2000)], 5000)
    assert len(out) == 1000 and truncated
