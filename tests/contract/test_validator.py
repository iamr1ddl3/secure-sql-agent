"""SQL validator: every golden reference query must pass for its role; hostile SQL must not."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals" / "golden"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from seed import DEMO_STAFF  # noqa: E402
from verify import load_items  # noqa: E402

from secure_sql_agent.validator import ValidationError, validate  # noqa: E402

ROLE = {k: role for k, role, *_ in DEMO_STAFF}
ANSWERED = [i for i in load_items() if i["expect"] == "answered"]


@pytest.mark.parametrize("item", ANSWERED, ids=lambda i: i["id"])
def test_reference_sql_is_accepted(item):
    validate(item["reference_sql"], ROLE[item["asked_by"]])


def bad(sql, role, policy):
    with pytest.raises(ValidationError) as e:
        validate(sql, role)
    assert e.value.policy_id == policy, e.value.detail


def test_not_select_and_stacked():
    bad("DROP TABLE bank.customers", "teller", "validator.not_select")
    bad("delete from bank.customers", "teller", "validator.not_select")
    bad("select customer_id from bank.customers; drop table bank.customers", "teller", "validator.multiple_statements")
    bad("set role bank_auditor", "manager", "validator.unknown_role")
    bad("set role bank_auditor", "branch_manager", "validator.not_select")
    bad("select customer_id into bank.x from bank.customers", "teller", "validator.not_select")
    bad("select customer_id from bank.customers for update", "teller", "validator.not_select")


def test_tables_by_role():
    bad("select annual_ctc from bank.salaries", "teller", "validator.forbidden_table")
    bad("select loan_id from bank.loans", "teller", "validator.forbidden_table")
    bad("select customer_id from bank.customers", "hr", "validator.forbidden_table")
    bad("select full_name from bank.employees", "intern", "validator.forbidden_table")
    bad("select * from app.staff_users", "auditor", "validator.select_star")
    bad("select auth_user_id from app.staff_users", "auditor", "validator.forbidden_table")
    bad("select table_name from information_schema.tables", "auditor", "validator.forbidden_table")
    bad("select relname from pg_catalog.pg_class", "auditor", "validator.forbidden_table")
    bad("select customer_id from customers", "teller", "validator.forbidden_table")  # unqualified
    validate("select loan_count from analytics.loan_portfolio_summary", "intern")


def test_functions_and_constructs():
    bad("select pg_sleep(10)", "teller", "validator.forbidden_function")
    bad("select set_config('role', 'bank_hr', true)", "teller", "validator.forbidden_function")
    bad("select pg_read_file('/etc/passwd')", "auditor", "validator.forbidden_function")
    bad("select customer_id from bank.customers where branch_id = (select app.current_branch())", "teller",
        "validator.forbidden_construct")  # schema-qualified function call parses as a Dot
    bad("select current_setting('request.jwt.claims')", "teller", "validator.forbidden_function")


def test_star_and_pii():
    bad("select * from bank.customers", "teller", "validator.select_star")
    bad("select c.* from bank.customers c", "teller", "validator.select_star")
    validate("select count(*) from bank.customers", "teller")
    bad("select national_id from bank.customers", "auditor", "validator.pii_column")
    bad("select c.phone from bank.customers c", "auditor", "validator.pii_column")
    validate("select national_id_masked from bank.customers", "auditor")
    validate("select national_id from bank.customers", "teller")  # tellers may see their own branch's IDs


def test_cte_names_allowed_and_output_is_normalized():
    v = validate("with t as (select branch_id from bank.branches) select branch_id from t -- hi", "teller")
    assert "--" not in v.sql and v.tables == ["bank.branches"]


def test_size_and_garbage():
    bad("", "teller", "validator.size")
    bad("select 1" + " " * 5000, "teller", "validator.size")
    bad("select from from", "teller", "validator.parse_error")


def test_query_without_a_table_is_refused():
    bad("select 'no customer table available' as customer_count", "hr", "validator.no_table")
    bad("select 1", "teller", "validator.no_table")
    validate("select b.name from bank.branches b, lateral (select 1 as x) l", "teller")
