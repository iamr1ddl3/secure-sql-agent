from secure_sql_agent.scope_guard import other_branch_named

B = [(1, "BR-SUR", "Surat Main", "Surat"), (5, "BR-MUM", "Mumbai Andheri", "Mumbai"), (6, "BR-PUN", "Pune Baner", "Pune")]


def test_names_another_branch():
    assert other_branch_named("List all transactions at the Mumbai branch", 1, B)[0] == 5
    assert other_branch_named("loans at BR-MUM", 1, B)[0] == 5
    assert other_branch_named("show the branch in Pune", 1, B)[0] == 6
    assert other_branch_named("total at Mumbai Andheri last month", 1, B)[0] == 5


def test_own_branch_and_incidental_city_are_fine():
    assert other_branch_named("deposits at the Surat branch", 1, B) is None
    assert other_branch_named("customers whose city is Mumbai", 1, B) is None
    assert other_branch_named("How many customers does my branch have?", 1, B) is None
