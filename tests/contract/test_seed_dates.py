"""The synthetic bank has no row dated before the thing it depends on (branch, customer, account)."""
import datetime as dt
import random
import sys
from pathlib import Path

from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import seed  # noqa: E402


def test_no_row_predates_what_it_depends_on():
    rng, fake = random.Random(42), Faker("en_IN")
    fake.seed_instance(42)
    c = seed.Ctx(rng, fake, dt.date(2026, 11, 1))
    employees, _, staff = seed.gen_employees(c)
    customers, accounts = seed.gen_customers_accounts(c, 1000)
    txns = seed.gen_transactions(c, accounts, 10_000)
    loans = seed.gen_loans(c, customers)

    opened = {b[0]: dt.date.fromisoformat(b[5]) for b in seed.BRANCHES}
    created = {cu[0]: cu[-1].date() for cu in customers}
    acct_opened = {a["account_id"]: a["opened_on"] for a in accounts}

    assert all(e[7] >= opened[e[1]] for e in employees if e[1] is not None)
    assert all(cu[-1].date() >= opened[cu[1]] for cu in customers)
    assert all(a["opened_on"] >= max(opened[a["branch_id"]], created[a["customer_id"]]) for a in accounts)
    assert all(l[6] >= max(opened[l[2]], created[l[1]]) for l in loans)
    assert all(t[3].date() >= acct_opened[t[1]] for t in txns)

    # one manager per branch: the demo login reuses the branch's manager row
    managers = [e[1] for e in employees if e[3] == "Branch Manager" and e[8] == "active"]
    assert sorted(managers) == sorted(opened)
    assert len({s[1] for s in staff}) == len(staff)
