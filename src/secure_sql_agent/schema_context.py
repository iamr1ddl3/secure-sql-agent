"""Role-aware schema text for the model: only tables and columns the caller's role may use.

Mirrors the grants in supabase/migrations (validator.TABLES / DENIED_COLUMNS are the shared source for what is
visible). Enum values are spelled out because that is where text-to-SQL goes wrong most often.
"""
from __future__ import annotations

from .validator import DENIED_COLUMNS, TABLES

DOCS: dict[str, tuple[str, list[str]]] = {
    "bank.branches": ("bank branches", ["branch_id smallint", "branch_code text", "name text", "city text", "state text", "opened_on date"]),
    "bank.customers": ("customers; branch_id -> bank.branches", [
        "customer_id bigint", "branch_id smallint", "full_name text", "date_of_birth date", "national_id text (PII)", "phone text (PII)",
        "email text", "city text", "segment text: retail|priority|sme", "kyc_status text: verified|pending|expired",
        "created_at timestamptz", "national_id_masked text", "phone_masked text"]),
    "bank.accounts": ("accounts; customer_id -> bank.customers, branch_id -> bank.branches", [
        "account_id bigint", "customer_id bigint", "branch_id smallint", "account_number text (PII)",
        "account_type text: savings|current|fixed_deposit", "status text: active|dormant|closed", "balance numeric",
        "currency char(3)", "opened_on date", "closed_on date", "last_activity_at timestamptz", "account_number_masked text"]),
    "bank.transactions": ("transactions; account_id -> bank.accounts; amount is always positive, the sign comes from txn_type", [
        "txn_id bigint", "account_id bigint", "branch_id smallint", "txn_at timestamptz",
        "txn_type text: deposit|withdrawal|transfer_in|transfer_out|fee|interest",
        "channel text: branch|atm|upi|netbanking|neft|imps|system", "amount numeric", "balance_after numeric", "description text"]),
    "bank.loans": ("loans; customer_id -> bank.customers", [
        "loan_id bigint", "customer_id bigint", "branch_id smallint", "loan_type text: home|personal|auto|business|gold",
        "principal numeric", "interest_rate numeric", "disbursed_on date", "tenure_months int", "outstanding numeric",
        "days_past_due int", "status text: current|overdue|npa|closed"]),
    "bank.employees": ("employees; branch_id is NULL for head office", [
        "employee_id int", "branch_id smallint", "full_name text", "job_title text",
        "department text: branch_ops|hr|audit|risk|it|executive|internship", "email text", "phone text (PII)", "hired_on date",
        "status text: active|left", "phone_masked text"]),
    "bank.salaries": ("salary history, several rows per employee; the CURRENT salary is the row with the latest effective_from", [
        "employee_id int", "effective_from date", "annual_ctc numeric", "currency char(3)"]),
    "analytics.branch_monthly_flows": ("aggregate view; groups under 5 rows are suppressed, so totals can be lower than the real ones", [
        "branch_id smallint", "branch_name text", "city text", "month date", "txn_count bigint", "inflow_total numeric", "outflow_total numeric"]),
    "analytics.branch_customer_counts": ("aggregate view; small groups suppressed", [
        "branch_id smallint", "branch_name text", "segment text", "customer_count bigint"]),
    "analytics.loan_portfolio_summary": ("aggregate view; small groups suppressed", [
        "branch_id smallint", "branch_name text", "loan_type text", "status text", "loan_count bigint", "outstanding_total numeric"]),
    "analytics.headcount_by_branch": ("aggregate view of ACTIVE staff; small groups suppressed", [
        "branch_id smallint", "branch_name text", "department text", "headcount bigint"]),
}


def schema_for(app_role: str) -> str:
    hidden = DENIED_COLUMNS.get(app_role, set())
    lines = []
    for table in sorted(TABLES[app_role]):
        note, cols = DOCS[table]
        keep = [c for c in cols if c.split()[0] not in hidden]
        lines.append(f"{table} -- {note}\n  ({', '.join(keep)})")
    return "\n".join(lines)
